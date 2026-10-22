# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
import csv, io, re, subprocess, statistics
from PIL import Image, ImageOps, ImageStat
from .runtime import resources, child_environment
from .render import text, RuledRows
from .scanlayout import best_ruled_grid, remove_color_stamps, cell_content
from .ocrselect import words as reading_words, box, confidence as word_confidence, mean_confidence, numeric, verified_orientation, prefer_arabic, collapse_line, merge_sparse, reread_numeric_columns
from .ocrtable import remove_pixel_separators, refine_latin_tables
from .ocrclean import good_words, looks_unreadable, descreen, accept_smoothed, smoothed_lines
from . import ocrengine


class ScanText(str):
    """OCR text plus table structure established from pixels or repeated word positions."""
    def __new__(cls,value,parts):
        obj=super().__new__(cls,value);obj.parts=parts;return obj


_FOREIGN=re.compile(r'[\u0370-\u03ff\u0400-\u04ff\u0590-\u05ff\u3040-\u30ff\u4e00-\u9fff]')
_DIGITS=re.compile(r'[0-9\u0660-\u0669]+')

def choose_engine_cell(engine_words,tesseract_words):
    """Cleanup22: a ruled-table cell keeps the ONNX engine reading unless it is empty, contains letters
    of another script (a misread unit such as "3\u03c1"), Latin letters where Tesseract read Arabic, or lost digit groups Tesseract found (Latin
    numbers inside Arabic text). Number cells always prefer the engine when it read a number."""
    if not engine_words:return False
    etext=' '.join(w['text'].strip() for w in engine_words);ttext=' '.join(w['text'].strip() for w in tesseract_words)
    if _FOREIGN.search(etext):return False
    if numeric(etext):return True
    latin=lambda t:len(re.findall('[A-Za-z]',t));arabic=lambda t:len(re.findall(r'[\u0621-\u064a]',t))
    # Arabic text read as Latin letters by the English recogniser ("3e" for a unit, "aiell" for a header)
    if latin(etext)>latin(ttext) and arabic(ttext)>latin(ttext):return False
    if ttext and numeric(ttext):return False
    return len(_DIGITS.findall(etext))>=len(_DIGITS.findall(ttext))

def _grid_transcription(image,grid,run,language,glyph_source=None,engine_reader=None):
    rows=[];confidence=[];spans=[];rowspans=dict(grid.get('rowspans',{}));readings=[]
    numeric_refinements=0;offsets={};items_split=0;engine_cells=set()
    for r,row in enumerate(grid['rows']):
        cells=['']*grid['columns']
        for first,last,box in row:
            if box[2]<=box[0] or box[3]<=box[1]:continue
            sub=image.crop(box)
            try:found=cell_content(sub,True)
            except TypeError:
                crop=cell_content(sub);found=None if crop is None else (crop,None)
            if found is None:continue
            crop,shift=found
            if shift is not None:offsets[r,first]=box[1]+shift[1]-12
            padded=ImageOps.expand(crop,border=12,fill='white')
            result=run(_png(padded),['-l',language,'--psm','6','tsv'])
            if result.returncode:raise RuntimeError('Cell OCR failed')
            words=list(csv.DictReader(io.StringIO(result.stdout.decode('utf-8','replace')),delimiter='\t',quoting=csv.QUOTE_NONE))
            engine_words=None
            if engine_reader is not None:
                try:engine_words=[w for w in engine_reader(padded.convert('RGB')) if w.get('text','').strip()]
                except Exception:engine_words=None
            if choose_engine_cell(engine_words,[w for w in words if w.get('text','').strip()]):
                words=engine_words;engine_cells.add((r,first))
            else:
                from .scannumbers import refine_numeric_words
                numeric_refinements+=refine_numeric_words(padded,[w for w in words if w.get('text','').strip()],run,_png,language)
            cells[first]=' '.join(w.get('text','').strip() for w in words if w.get('text','').strip())
            readings.append([r,first,box,[w for w in words if w.get('text','').strip()]])
        rows.append(cells)
        spans.append([(first,last) for first,last,_ in row])
    value=' '.join(c for row in rows for c in row)
    if not value.strip():raise RuntimeError('Grid OCR returned no text')
    arabic=len(re.findall(r'[\u0621-\u064a]',value));latin=len(re.findall('[A-Za-z]',value))
    refined=disagreements=digit_refinements=percent_refinements=glyph_resolution=0
    if language.startswith('ara') and arabic>latin:
        from .scanglyphs import refine_digits,refine_percent
        glyph_image,glyph_grid,glyph_readings=image,grid,readings
        if glyph_source and grid['columns']>=8 and len(grid['rows'])>=8:
            # Keep the original cell ownership and body OCR. Use original PDF
            # pixels at higher resolution only when both grid detections agree.
            try:
                high_image,_=remove_color_stamps(glyph_source())
                high_image,high_grid=best_ruled_grid(high_image)
                def ownership(g):
                    return sorted((r,a,b,g.get('rowspans',{}).get((r,a),1))
                                  for r,row in enumerate(g['rows']) for a,b,_ in row)
                if high_grid and high_grid['columns']==grid['columns'] and ownership(high_grid)==ownership(grid):
                    bounds={(r,a):bb for r,row in enumerate(high_grid['rows']) for a,b,bb in row}
                    glyph_image,glyph_grid=high_image,high_grid
                    glyph_readings=[(r,a,bounds[r,a],ws) for r,a,bb,ws in readings]
                    glyph_resolution=300
            except (OSError,ValueError,KeyError,RuntimeError):pass
        glyph_readings=[g for g in glyph_readings if (g[0],g[1]) not in engine_cells]
        digit_refinements=refine_digits(glyph_image,glyph_grid,rows,glyph_readings,run,_png,language,cell_content)
        percent_refinements=refine_percent(glyph_image,rows,glyph_readings,run,_png,cell_content)
    # A weak word cell on an Arabic-dominant table gets its own clean alternate.
    # Keep numbers, leading zeroes and signs unless the two readings agree.
    if '+' in language and language.startswith('ara') and arabic>latin:
        for reading in readings:
            r,first,bounds,primary=reading;old=rows[r][first]
            if (r,first) in engine_cells:continue
            if not old or numeric(old) or mean_confidence(primary)>=70:continue
            if not any(c.isalpha() for c in old):continue
            crop=cell_content(image.crop(bounds))
            if crop is None:continue
            binary=ImageOps.grayscale(crop).point(lambda p:0 if p<160 else 255)
            result=run(_png(ImageOps.expand(binary,border=12,fill='white')),
                       ['-l',language.split('+')[0],'--psm','6','tsv'])
            alternate=reading_words(result);accept,reason=prefer_arabic(primary,alternate)
            if accept:
                rows[r][first]=' '.join(w['text'].strip() for w in alternate)
                reading[3]=alternate;refined+=1
            elif alternate and reason=='numbers':disagreements+=1
    for _,_,_,words in readings:
        for word in words:
            try:confidence.append(float(word['conf']))
            except (KeyError,ValueError):pass
    try:
        from .boqrows import split_item_rows
        rows,spans,rowspans,items_split=split_item_rows(rows,spans,rowspans,readings,offsets,grid['columns'],image,language.startswith('ara') and (not latin or arabic>latin))
    except (KeyError,ValueError,IndexError,TypeError):pass
    if language.startswith('ara') and (not latin or arabic>latin):
        mirrored=[];mirrored_rowspans={}
        for r,(row,row_spans) in enumerate(zip(rows,spans)):
            cells=['']*grid['columns']
            for first,last in row_spans:
                cells[grid['columns']-last]=row[first]
                if (r,first) in rowspans:mirrored_rowspans[r,grid['columns']-last]=rowspans[r,first]
            mirrored.append(cells)
        rows=mirrored
        rowspans=mirrored_rowspans
        spans=[sorted((grid['columns']-last,grid['columns']-first) for first,last in row) for row in spans]
    result=RuledRows(rows,spans,rowspans)
    result.ocr_review={'arabic_refinements':refined,'number_disagreements':disagreements,
                      'digit_refinements':digit_refinements,'percent_refinements':percent_refinements,
                      'glyph_resolution':glyph_resolution,'numeric_refinements':numeric_refinements,'item_rows_split':items_split,'engine_cells':len(engine_cells)}
    return result,confidence

def preflight(settings=None):
    root = resources()/'tesseract'
    langs=['ara','eng','osd']+(['ara_best','eng_best'] if (settings or {}).get('quality')=='high' else [])
    for rel in ['tesseract.exe']+[f'tessdata/{l}.traineddata' for l in langs]:
        if not (root/rel).is_file():
            raise RuntimeError('Missing bundled OCR resource: '+rel+'. Extract the complete portable ZIP again.')
    return root

def ocr_language(settings):
    # High accuracy uses the larger "best" models (ara_best/eng_best), about 2.5x slower.
    language=settings['language']
    return '+'.join(l+'_best' for l in language.split('+')) if settings.get('quality')=='high' else language

def quick_mode(settings):
    return settings.get('quality')=='quick' or bool(settings.get('quick'))

def deskew(image):
    # Projection profile deskew, bounded thumbnail; no remote model or GPU.
    small=ImageOps.grayscale(image); small.thumbnail((900,900))
    bw=small.point(lambda p: 0 if p<170 else 255)
    def score(angle):
        rotated=bw.rotate(angle, expand=False, fillcolor=255)
        profile=rotated.resize((1,rotated.height),Image.Resampling.BOX)
        values=list(profile.tobytes())  # 8-bit grayscale; same values as getdata()
        return sum((values[i]-values[i-1])**2 for i in range(1,len(values)))
    best=max(range(-6,7),key=score)
    if best and score(best)>score(0)*1.12:
        return image.rotate(best,expand=True,fillcolor='white'),best
    return image,0

def _tesseract(root, data, args, work, threads):
    env=child_environment(work)
    if threads: env.update({'OMP_THREAD_LIMIT':str(threads),'OMP_NUM_THREADS':str(threads)})
    return subprocess.run([str(root/'tesseract.exe'),'stdin','stdout','--tessdata-dir','tessdata']+args,input=data,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=str(root),creationflags=0x08000000,env=env)

def _png(image):
    stream=io.BytesIO(); image.save(stream,format='PNG',dpi=(300,300)); return stream.getvalue()

POOR_SCAN_NOTICE=('> Poor-quality scan: the text below was read from a smoothed copy of the page and is approximate. '
                  'Check every word and number against the page image.')
UNREADABLE_NOTICE='> Unreadable scan: no reliable text could be read from this page. See the page image.'

def _tsv_rows(result):
    return list(csv.DictReader(io.StringIO(result.stdout.decode('utf-8','replace')),delimiter='\t',quoting=csv.QUOTE_NONE))

def _unreadable_scan(data,rows,run,settings,glyph_source,label):
    """Cleanup11: None when the page is not noise. Otherwise a smoothed reading under a warning notice, or
    only a notice when even the smoothed copy is unreadable (Geotechnical Report scans)."""
    language=ocr_language(settings)
    sparse=run(data,['-l',language,'--psm','11','tsv'])
    sparse_rows=_tsv_rows(sparse) if sparse.returncode==0 else []
    if not looks_unreadable(rows,sparse_rows): return None
    smoothed_rows=[]
    try:
        if glyph_source is not None:
            source,_=remove_color_stamps(glyph_source()); dpi=300
        else:
            source=Image.open(io.BytesIO(data)).convert('RGB'); dpi=max(100,min(600,round(300*max(source.size)/3508)))
        alt=run(_png(descreen(source,dpi)),['-l',language,'--psm','3','tsv'])
        if alt.returncode==0: smoothed_rows=_tsv_rows(alt)
    except Exception:
        smoothed_rows=[]
    if accept_smoothed(smoothed_rows,sparse_rows):
        lines=smoothed_lines(smoothed_rows)
        if lines:
            body='\n'.join(text(v) for v in lines)
            kept=[float(r['conf']) for r in smoothed_rows if r.get('text','').strip() and float(r['conf'])>=25]
            confidence=sum(kept)/len(kept) if kept else None
            return (ScanText(POOR_SCAN_NOTICE+'\n'+body,[('text',POOR_SCAN_NOTICE),('text',body)]),
                    [label+': poor-quality scan read from a smoothed copy; the text is approximate. Check every word and number against the page image.'],
                    confidence)
    return (ScanText(UNREADABLE_NOTICE,[('text',UNREADABLE_NOTICE)]),
            [label+': unreadable scan; OCR found no reliable text, so none was exported. Review the retained page image.'],None)

def review_engine(grid_rows):
    return getattr(grid_rows,'ocr_review',{}).get('engine_cells',0)

def transcribe(data,settings,work,label,rendered=False,threads=None,glyph_source=None):
    """Thread-safe OCR of PNG bytes. Returns (text, warnings, mean confidence or None).
    rendered=True skips deskew; a confident OSD reading can still correct a
    sideways raster. Low-confidence orientation guesses never rotate the image.
    Quick mode skips the second, sparse-text pass; High accuracy uses the *_best models."""
    root=preflight(settings); warnings=[];glyph_rotation=0
    # Windows Tesseract's narrow filename API cannot open every Arabic/Unicode path,
    # so image bytes are piped and the language folder is resolved next to the executable.
    run=lambda d,args:_tesseract(root,d,args,work,threads)
    # Rendered PDF images normally already have the page orientation applied, but the
    # raster itself may still be sideways (common in scanned mixed PDFs). Run OSD for
    # real images; preserve the old byte-stream behavior for synthetic/test inputs.
    if not rendered:
        image=ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert('RGB')
        orientation=run(data,['-l','osd','--psm','0'])
        angle,osd_confidence,verified=verified_orientation(image,orientation,run,_png,ocr_language(settings))
        if angle:image=image.rotate(-angle,expand=True,fillcolor='white');glyph_rotation=-angle
        image,deskew_angle=deskew(image)
        data=_png(image)
    elif data:
        try:
            image=ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert('RGB')
            orientation=run(data,['-l','osd','--psm','0'])
            angle,osd_confidence,verified=verified_orientation(image,orientation,run,_png,ocr_language(settings))
            if angle:
                glyph_rotation=-angle
                data=_png(image.rotate(-angle,expand=True,fillcolor='white'))
                warnings.append(label+f': scan orientation corrected by {angle} degrees (OSD confidence {osd_confidence:.1f}'+('; verified by OCR comparison' if verified else '')+').')
        except Exception:
            pass
    if glyph_source is not None and glyph_rotation:
        original_source=glyph_source
        glyph_source=lambda:original_source().rotate(glyph_rotation,expand=True,fillcolor='white')
    grid=None;grid_rows=None;grid_confidence=[];probe=None;probe_data=None
    use_engine=use_onnx(settings)
    if not quick_mode(settings):
        try:
            image=Image.open(io.BytesIO(data)).convert('RGB')
            image,cleaned=remove_color_stamps(image)
            if cleaned:
                warnings.append(label+': detected colored stamps suppressed for OCR only; original image retained.')
            # Cleanup11: one layout reading first. A page that reads as noise gets a smoothed re-read or a
            # clear notice and stops here; otherwise this reading is reused below when no grid is found.
            probe_data=_png(image) if cleaned else data
            probe=run(probe_data,['-l',ocr_language(settings),'--psm','3','tsv'])
            if probe.returncode==0:
                probe_rows=_tsv_rows(probe)
                if good_words(probe_rows)<5:
                    verdict=_unreadable_scan(probe_data,probe_rows,run,settings,glyph_source,label)
                    if verdict is not None:
                        if use_engine:
                            better=_engine_poor_scan(image,settings,threads,label)
                            if better is not None:
                                value,more,confidence=better
                                return value,warnings+more,confidence
                        value,more,confidence=verdict
                        return value,warnings+more,confidence
            else: probe=None
            image,grid=best_ruled_grid(image)
            if grid:
                engine_cells={'engine_reader':lambda cell:ocrengine.engine(threads).read(cell,settings['language'])} if use_engine else {}
                grid_rows,grid_confidence=_grid_transcription(image,grid,run,ocr_language(settings),glyph_source,**engine_cells)
                # Only suppress the grid if cell reading succeeded. Blank cells
                # retain their slots; wrapped descriptions stay with their row.
                from PIL import ImageDraw
                outside=image.copy();ImageDraw.Draw(outside).rectangle(grid['bbox'],fill='white');data=_png(outside)
                warnings.append(label+': ruled table read cell by cell; review merged cells and numerical values against the original.')
                if review_engine(grid_rows):
                    warnings.append(label+f": {review_engine(grid_rows)} table cells read by the ONNX OCR engine; the others by Tesseract.")
                if grid.get('rowspans'):
                    warnings.append(label+': partial separators and vertical merged cells preserved; covered slots are not transcribed twice.')
                if grid.get('layout_review'):
                    warnings.append(label+': ambiguous partial cell boundaries; coarse table geometry retained for review.')
                review=getattr(grid_rows,'ocr_review',{})
                if review.get('numeric_refinements'):
                    warnings.append(label+f": {review['numeric_refinements']} inline numeric readings recovered from local pixel evidence; review the original image.")
                if review.get('glyph_resolution'):
                    warnings.append(label+': small table glyphs checked against 300 dpi PDF pixels after matching cell ownership; body text and table geometry retained.')
                if review.get('digit_refinements'):
                    warnings.append(label+f": isolated digits in {review['digit_refinements']} table cells were reread from their shapes using local OCR anchors; review the original image.")
                if review.get('percent_refinements'):
                    warnings.append(label+f": percentage marks in {review['percent_refinements']} table cells were recovered by two English readings of the same pixels; review the original image.")
                if review.get('number_disagreements'):
                    warnings.append(label+f": alternate cell OCR disagreed on numbers in {review['number_disagreements']} cells; original readings retained for review.")
            elif cleaned:data=_png(image)
        except Exception:
            grid=None;grid_rows=None;grid_confidence=[];probe=None
            warnings.append(label+': enhanced scan layout unavailable; ordinary OCR and original image retained.')
    language=ocr_language(settings)
    if use_engine and data:
        try:
            rows=ocrengine.engine(threads).read(Image.open(io.BytesIO(data)).convert('RGB'),settings['language'])
        except Exception:
            use_engine=False
            warnings.append(label+': the ONNX OCR engine failed on this page; Tesseract was used instead.')
        else:
            return _finish(rows,grid,grid_rows,grid_confidence,data,settings,warnings,label,engine=True)
    result=probe if (probe is not None and grid is None and data==probe_data) else run(data,['-l',language,'--psm','3','tsv'])
    if result.returncode and grid_rows is None:
        return '',[label+': OCR failed (engine code '+str(result.returncode)+'). Visual retained.'],None
    if result.returncode:
        warnings.append(label+': OCR outside the table failed; table transcription and original image retained.')
        result.stdout=b''
    rows=list(csv.DictReader(io.StringIO(result.stdout.decode('utf-8','replace')),delimiter='\t',quoting=csv.QUOTE_NONE))
    # Sparse-text pass recovers isolated captions/short lines missed by automatic layout.
    # Geometry keeps sparse text from duplicating the first reading.
    # Noisy photocopies (speckle, binder holes) can read as empty or garbled. One more reading on a cleaned
    # copy is kept only when it is clearly better; the retained page image is never altered (Cleanup3).
    if not quick_mode(settings) and grid_rows is None and data:
        try:
            from .ocrclean import clean_scan,needs_cleanup,prefer_cleaned,cleanup_numbers_changed
            if needs_cleanup(rows):
                cleaned=clean_scan(Image.open(io.BytesIO(data)).convert('RGB'))
                if cleaned is not None:
                    cdata=_png(cleaned); alt=run(cdata,['-l',language,'--psm','3','tsv'])
                    if alt.returncode==0:
                        crows=list(csv.DictReader(io.StringIO(alt.stdout.decode('utf-8','replace')),delimiter='\t',quoting=csv.QUOTE_NONE))
                        if cleanup_numbers_changed(rows,crows):
                            warnings.append(label+': cleaned OCR disagrees on numbers; original reading retained. Verify numbers against the original image.')
                        elif prefer_cleaned(rows,crows):
                            rows=crows; data=cdata
                            warnings.append(label+': noisy scan; text was read from a cleaned copy of the image. Review against the original.')
        except Exception: pass
    primary=[r for r in rows if r.get('text','').strip()]
    # Mixed Arabic/Latin recognition can damage a short Arabic line. Re-read
    # only that line's own crop with Arabic, so the alternate pass cannot
    # replace English lines elsewhere on the page.
    if '+' in language:
        line_groups={}
        for r in primary:
            line_groups.setdefault((r.get('block_num'),r.get('par_num'),r.get('line_num')),[]).append(r)
        for group in line_groups.values():
            value=' '.join(r.get('text','').strip() for r in group)
            arabic=sum('\u0621'<=c<='\u064a' for c in value); latin=sum(c.isascii() and c.isalpha() for c in value)
            if arabic<3 or arabic<latin:continue
            try:
                geometric=sorted(group,key=lambda r:int(r['left']))
                if any(int(b['left'])-int(a['left'])-int(a['width'])>3*max(int(a['height']),int(b['height']))
                       for a,b in zip(geometric,geometric[1:])): continue
                boxes=[(int(r['left']),int(r['top']),int(r['width']),int(r['height'])) for r in group]
                x0=max(0,min(x for x,y,w,h in boxes)-12); y0=max(0,min(y for x,y,w,h in boxes)-12)
                x1=min(Image.open(io.BytesIO(data)).width,max(x+w for x,y,w,h in boxes)+12)
                y1=min(Image.open(io.BytesIO(data)).height,max(y+h for x,y,w,h in boxes)+12)
                crop=Image.open(io.BytesIO(data)).convert('RGB').crop((x0,y0,x1,y1))
                alt=run(_png(crop),['-l','ara_best' if settings.get('quality')=='high' else 'ara','--psm','7','tsv'])
                alternate=reading_words(alt)
                accept,reason=prefer_arabic(group,alternate)
                if accept: collapse_line(group,alternate)
                elif alternate and reason=='numbers':
                    warnings.append(label+': Arabic alternate disagreed on numbers; original reading retained for review.')
            except Exception:
                pass
    sparse=None if quick_mode(settings) else run(data,['-l',language,'--psm','11','tsv'])
    if sparse is not None and sparse.returncode==0:
        merge_sparse(rows,reading_words(sparse),warnings,label)
        try:
            reread_numeric_columns(rows,Image.open(io.BytesIO(data)).convert('RGB'),run,_png,warnings,label,language)
        except (OSError,ValueError,KeyError): pass
    if not quick_mode(settings) and data:
        try:
            image=Image.open(io.BytesIO(data)).convert('RGB')
            remove_pixel_separators(rows,image,warnings,label)
            refine_latin_tables(rows,image,run,_png,warnings,label,language,_table_rows,
                                reading_words(sparse) if sparse is not None else ())
        except (OSError,ValueError,KeyError):
            warnings.append(label+': local table refinement unavailable; original reading and image retained.')
    return _finish(rows,grid,grid_rows,grid_confidence,data,settings,warnings,label)

def use_onnx(settings):
    """Cleanup17: Standard and High accuracy read scanned text with the bundled ONNX engine when it is
    present and settings['ocr_engine'] is 'onnx' (the conversion default); Quick keeps the single Tesseract pass."""
    return (not quick_mode(settings) and settings.get('ocr_engine')=='onnx'
            and ocrengine.available())

def _engine_poor_scan(image,settings,threads,label):
    """A page Tesseract reads as noise: keep the ONNX reading under the poor-scan notice when it has at
    least eight confident words; otherwise None and the Tesseract verdict stands."""
    try:
        rows=ocrengine.engine(threads).read(image,settings['language'])
    except Exception:
        return None
    if good_words(rows)<8: return None
    lines={}
    for r in rows: lines.setdefault(r['block_num'],[]).append(r['text'])
    body='\n'.join(text(' '.join(v)) for v in lines.values())
    conf=[float(r['conf']) for r in rows]
    return (ScanText(POOR_SCAN_NOTICE+'\n'+body,[('text',POOR_SCAN_NOTICE),('text',body)]),
            [label+': poor-quality scan read with the ONNX OCR engine; the text is approximate. Check every word and number against the page image.'],
            sum(conf)/len(conf) if conf else None)

def _finish(rows,grid,grid_rows,grid_confidence,data,settings,warnings,label,engine=False):
    if engine and data:
        try: remove_pixel_separators(rows,Image.open(io.BytesIO(data)).convert('RGB'),warnings,label)
        except (OSError,ValueError,KeyError): pass
    rows.sort(key=lambda r:(int(r.get('top',0)),int(r.get('left',0))) if not r.get('text','').strip() else (0,0))
    lines={}; confidences=[]
    for r in rows:
        word=r.get('text','').strip()
        if not word: continue
        key=(r.get('block_num'),r.get('par_num'),r.get('line_num'))
        lines.setdefault(key,[]).append(word)
        try: confidences.append(float(r['conf']))
        except (ValueError,KeyError): pass
    if not lines and grid_rows is None:
        # Empty graphics are common, but never claim complete OCR on a required scan.
        return '',[label+': OCR found no readable text; review the retained image.'],None
    confidences.extend(grid_confidence)
    confidence=sum(confidences)/len(confidences) if confidences else None
    if confidence is not None and confidence<70: warnings.append(label+f': low OCR confidence ({confidence:.0f}/100); review text and numbers.')
    # Tesseract emits logical Unicode text. No manual reversal of Arabic.
    warnings.append(label+': OCR is an approximate transcription'+(' (ONNX OCR engine)' if engine else '')+'; review the retained image, especially numbers and layout.')
    # Order complete lines geometrically, while preserving Tesseract's logical word order.
    positions={}
    for r in rows:
        key=(r.get('block_num'),r.get('par_num'),r.get('line_num'))
        if r.get('text','').strip():positions[key]=min(positions.get(key,(10**9,10**9)),(int(r['top']),int(r['left'])))
    table_rows,used=_table_rows([r for r in rows if r.get('text','').strip()],settings['language'])
    out=[]
    for key in lines:
        words=[r for r in rows if r.get('text','').strip() and (r.get('block_num'),r.get('par_num'),r.get('line_num'))==key and id(r) not in used]
        if not words: continue
        # Table words have already been emitted in their cells. Keep only the
        # remaining words of a partially consumed OCR line, in logical TSV order.
        words_text=[r['text'].strip() for r in words]
        top=min(int(r['top']) for r in words); left=min(int(r['left']) for r in words)
        out.append(((top,left),text(' '.join(words_text))))
    # Distinct spatial rows can share a top coordinate (for example a short
    # bullet beside tall text). Bind cells to a unique output entry so one row
    # cannot replace another row when the structured parts are assembled.
    for index,(top,cells) in enumerate(table_rows):
        out.append(((top,-1,index),'\t'.join(text(c) for c in cells)))
    if grid_rows is not None:
        above='\n'.join(v for pos,v in sorted(out) if pos[0]<grid['bbox'][1])
        below='\n'.join(v for pos,v in sorted(out) if pos[0]>=grid['bbox'][1])
        parts=[('text',above),('table',grid_rows),('text',below)]
        value='\n'.join([above]+['\t'.join(row) for row in grid_rows]+[below])
        return ScanText(value,parts),warnings,confidence
    if table_rows:
        parts=[]; block=[]
        cells_by_position={(top,-1,index):cells for index,(top,cells) in enumerate(table_rows)}
        for pos,value in sorted(out):
            if pos[1]==-1:
                block.append(cells_by_position[pos])
            else:
                if block: parts.append(('table',block)); block=[]
                parts.append(('text',value))
        if block: parts.append(('table',block))
        return ScanText('\n'.join(v for _,v in sorted(out)),parts),warnings,confidence
    return '\n'.join(v for _,v in sorted(out)),warnings,confidence

def _table_rows(words,language='ara+eng'):
    """Scanned tables: Tesseract splits table columns into separate blocks, so rebuild rows from
    word positions. Rows whose words fall into two or more columns separated by wide gaps, in a run
    that has at least three rows with three or more columns, become table rows.
    Two-column tables also need stable column positions and a mostly numeric column.
    Cells follow the table's script (Arabic rightmost first, English leftmost
    first). Words inside each cell retain Tesseract's logical Unicode order.
    Returns ([(top, [cell, ...])], ids of the words used)."""
    word_order={id(r):n for n,r in enumerate(words)}
    try: items=sorted(words,key=lambda r:int(r['top'])+int(r['height'])/2)
    except (KeyError,ValueError): return [],set()
    rowsets=[]
    for r in items:
        cy=int(r['top'])+int(r['height'])/2; h=int(r['height']) or 1
        # Tiny bullets need the established text height; ordinary glyphs keep
        # their own tolerance so wrapped headers retain their grouping.
        row_height=statistics.median(int(w['height']) or 1 for w in rowsets[-1][1]) if rowsets else h
        tolerance=row_height if h<.35*row_height else h
        if rowsets and abs(rowsets[-1][0]-cy)<0.6*tolerance: rowsets[-1][1].append(r)
        else: rowsets.append([cy,[r]])
    parsed=[]
    for cy,ws in rowsets:
        ws.sort(key=lambda r:int(r['left'])); h=sorted(int(r['height']) for r in ws)[len(ws)//2] or 1
        segs=[[ws[0]]]
        for a,b in zip(ws,ws[1:]):
            if int(b['left'])-(int(a['left'])+int(a['width']))>1.8*h: segs.append([b])
            else: segs[-1].append(b)
        parsed.append((min(int(r['top']) for r in ws),segs))
    result=[]; used=set(); n=0
    while n<len(parsed):
        m=n
        while m<len(parsed) and len(parsed[m][1])>=2: m+=1
        run=parsed[n:m]
        discarded=[]; separator_x=[]
        for _,segs in run:
            for seg in segs:
                if all(re.fullmatch(r'[:|;]+',w['text'].strip()) for w in seg):
                    separator_x.append(statistics.mean(int(w['left']) for w in seg))
        cleaned=[]
        for top,segs in run:
            kept=[]
            for seg in segs:
                delimiter=all(re.fullmatch(r'[:|;]+',w['text'].strip()) for w in seg)
                # A colon can look like a low-confidence narrow "5". Remove it
                # only when other rows establish a delimiter at the same position.
                mistaken=(len(seg)==1 and word_confidence(seg[0])<60
                    and int(seg[0]['width'])<0.4*max(1,int(seg[0]['height']))
                    and sum(abs(int(seg[0]['left'])-x)<max(1,int(seg[0]['height'])) for x in separator_x)>=2)
                if delimiter or mistaken: discarded.extend(seg)
                else: kept.append(seg)
            cleaned.append((top,kept))
        run=cleaned
        pairs=[segs for _,segs in run if len(segs)==2]
        two_columns=False
        if len(pairs)>=3 and len(pairs)>=0.8*len(run):
            heights=[int(w['height']) for segs in pairs for seg in segs for w in seg]
            tolerance=2*statistics.median(heights)
            anchors=[statistics.median(int(segs[c][0]['left']) for segs in pairs) for c in (0,1)]
            stable=all(sum(abs(int(segs[c][0]['left'])-anchors[c])<=tolerance for segs in pairs)>=0.8*len(pairs) for c in (0,1))
            mostly_numeric=any(sum(numeric(' '.join(w['text'] for w in segs[c])) for segs in pairs)>=0.8*len(pairs) for c in (0,1))
            two_columns=stable and mostly_numeric
        if sum(1 for _,segs in run if len(segs)>=3)>=3 or two_columns:
            value=' '.join(w['text'] for _,segs in run for seg in segs for w in seg)
            arabic=len(re.findall(r'[\u0621-\u064a\u0671-\u06d3]',value))
            latin=len(re.findall(r'[A-Za-z]',value))
            rtl=(language=='ara' or (language!='eng' and arabic>latin))
            if language=='ara+eng' and not arabic and not latin:
                rtl=len(re.findall(r'[\u0660-\u0669\u06f0-\u06f9]',value))>len(re.findall(r'[0-9]',value))
            for top,segs in run:
                columns=reversed(segs) if rtl else segs
                cells=[' '.join(w['text'].strip() for w in sorted(seg,key=lambda r:word_order[id(r)])) for seg in columns]
                result.append((top,cells)); used.update(id(w) for seg in segs for w in seg)
            used.update(id(w) for w in discarded)
            n=m; continue
        n+=1
    return result,used

def apply_result(ctx,result):
    """Record a transcribe() result on the context (main thread only)."""
    value,warnings,confidence=result
    for w in warnings: ctx.warn(w)
    if confidence is not None: ctx.counts.setdefault('ocr_mean_confidence',[]).append(round(confidence,1))
    return value

def recognize(image,ctx,label,rendered=False,glyph_source=None):
    preflight(ctx.settings); ctx.stage('Reading image text: '+label)
    image=ImageOps.exif_transpose(image).convert('RGB')
    if image.width<100 or image.height<40: return ''
    if max(image.size)>12000: ctx.warn(label+': unusually large image; OCR may reach the configured file limit.')
    options={'glyph_source':glyph_source} if glyph_source is not None else {}
    return apply_result(ctx,transcribe(_png(image),ctx.settings,ctx.work,label,rendered=rendered,**options))
