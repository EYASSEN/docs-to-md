# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
import io, os, unicodedata
from concurrent.futures import ThreadPoolExecutor
import pymupdf as fitz
from PIL import Image, ImageDraw
from .render import table, text, RuledRows
from .ocr import recognize, transcribe, apply_result, ScanText
from . import fontdecode
from .arabicfix import fix_text, drop_stray_tanween
import re
AR=re.compile('[\u0600-\u06ff]')

def _fix_presentation_forms(value):
    if isinstance(value,ScanText):
        return ScanText(_fix_presentation_forms(str(value)),[
            (kind,(part.map_cells(_fix_presentation_forms) if isinstance(part,RuledRows) else [[_fix_presentation_forms(c) for c in row] for row in part]) if kind=='table' else _fix_presentation_forms(part))
            for kind,part in value.parts])
    # Some PDFs store Arabic as presentation-form glyphs (U+FB50-FDFF, U+FE70-FEFF).
    # Map them back to ordinary letters so the Markdown is searchable and renders normally.
    # Also repairs Windows-1256 mojibake, swapped lam+hamza from Word PDFs, and kashida (arabicfix).
    # isolated harakat forms (U+FE70-FE7F) normalize to space + mark; keep only the mark (Update10)
    return fix_text(''.join((unicodedata.normalize('NFKC',c).replace(' ','') if '\ufe70'<=c<='\ufe7f' else unicodedata.normalize('NFKC',c)) if '\ufb50'<=c<='\ufdff' or '\ufe70'<=c<='\ufeff' else c for c in value))

def _hidden_layer(page, blocks):
    """Return rects of native text that is an OCR layer hidden behind or inside a scan.
    Invisible text (render mode 3) and any text inside an image covering most of the page
    is treated as a hidden layer: it is not exported and not painted out before OCR."""
    rects=[]
    try:
        for span in page.get_texttrace():
            if span.get('type')==3 or span.get('opacity',1)==0: rects.append(fitz.Rect(span['bbox']))
    except Exception: pass
    bounds=page.rect*page.derotation_matrix
    area=abs(bounds) or 1
    # Text drawn BEFORE a page-sized image is covered by it (an OCR layer behind a scan). Text drawn
    # AFTER it sits on top: the image is a letterhead or background and the text is real (Update18).
    try:
        log=page.get_bboxlog()
        big=[i for i,(kind,r) in enumerate(log) if 'image' in kind and abs(fitz.Rect(r)&bounds)>=0.8*area]
        if big:
            first=big[0]
            for i,(kind,r) in enumerate(log):
                if 'text' in kind and i<first: rects.append(fitz.Rect(r))
            return rects
    except Exception: pass
    for b in blocks:
        if b['type']==1:
            r=fitz.Rect(b['bbox'])&bounds
            if abs(r)>=0.8*area: rects.append(r)
    return rects

def _inside(rect, rects):
    c=fitz.Point((rect.x0+rect.x1)/2,(rect.y0+rect.y1)/2)
    return any(r.contains(c) for r in rects)

def _invisible(span, hidden):
    # A span the text blocks report as fully transparent is hidden by itself. Its block box can be much
    # taller than the tight trace boxes of _hidden_layer (a scanner's OCR layer uses huge font sizes), so the
    # centre test alone let invisible OCR text leak into the output (VOL 1.1 pages 510 and 928). The span's
    # own flag is used, not its box: an invisible watermark box must not hide real text under it (Cleanup10).
    return span.get('alpha',255)==0 or _inside(fitz.Rect(span['bbox']),hidden)

def _garbled(value, share=0.05):
    chars=[c for c in value if not c.isspace()]
    if not chars: return False
    bad=sum(1 for c in chars if unicodedata.category(c) in ('Cc','Co','Cs') or c=='\ufffd'
            or ('\u0080'<=c<='\u00ff' and not c.isalpha() and c not in '°±×÷©®µ·'))
    # Broken Arabic font maps can emit alphabetic Latin-Extended characters
    # plus repeated non-Arabic signs, which the control-code check misses.
    extended=sum('\u0100'<=c<='\u024f' for c in chars)
    foreign_marks=sum('\u0300'<=c<='\u03ff' for c in chars)
    if sum('\u0621'<=c<='\u064a' for c in chars)>=10 and extended>=3 and foreign_marks>=3:
        bad+=extended+foreign_marks
    return bad>=max(2,share*len(chars))

def _unusable_text(page, value=None):
    value=page.get_text() if value is None else value
    return len(value.strip())>=3 and _garbled(value)

def _read_region(ctx,page,rect,label,dpi=300):
    clip=(fitz.Rect(rect)*page.rotation_matrix)&page.rect
    if clip.is_empty:
        ctx.warn(label+': region lies outside the page; no image could be rendered.')
        return False
    pix=page.get_pixmap(dpi=dpi,clip=clip,alpha=False)
    if not pix.width or not pix.height:
        ctx.warn(label+': region rendered empty.')
        return False
    with Image.open(io.BytesIO(pix.tobytes('png'))) as source:
        image=source.convert('RGB')
    ctx.image(image,label,ocr=False)
    if ctx.settings['ocr']=='off':
        ctx.warn(label+': unreadable native text omitted; OCR is disabled. Review the retained image.')
        return False
    # Drawn by this app from the PDF itself: orientation is known, skip orientation/deskew passes.
    glyph_source=None
    if dpi<300 and ctx.settings.get('quality')=='standard' and ctx.settings.get('language','').startswith('ara'):
        def glyph_source():
            high=page.get_pixmap(dpi=300,clip=clip,alpha=False)
            with Image.open(io.BytesIO(high.tobytes('png'))) as source:return source.convert('RGB')
    options={'glyph_source':glyph_source} if glyph_source is not None else {}
    result=_fix_presentation_forms(recognize(image,ctx,label,rendered=True,**options))
    if result:_write_ocr(ctx,result)
    return bool(result)

def _workers():
    # Parallel OCR of whole pages: leave one core free for the window and the rest of Windows.
    return max(1,min(6,(os.cpu_count() or 2)-1))

def _visible_text(page,blocks,hidden):
    return '\n'.join(''.join(s['text'] for s in line['spans'] if not _invisible(s,hidden))
                     for b in blocks if b['type']==0 for line in b['lines'])

def _needs_whole_page_ocr(page):
    blocks=page.get_text('dict',sort=True)['blocks']
    return _unusable_text(page,_visible_text(page,blocks,_hidden_layer(page,blocks)))

def _content_lines(lines):
    return [i for i,l in enumerate(lines) if l.strip() and not l.startswith(('![','## Page ','[Page ','Annotation: '))]

def _strip_running_lines(pages):
    """Remove short lines that repeat at the top/bottom of many pages (running headers, footers,
    logos read as text). Returns the removed line texts so they can be reported."""
    if len(pages)<5: return []
    counts={}
    split=[p.split('\n') for p in pages]
    for lines in split:
        idx=_content_lines(lines); edge=idx[:3]+idx[-3:]
        for value in {lines[i].strip() for i in edge}:
            if len(value)<=60: counts[value]=counts.get(value,0)+1
    running={v for v,c in counts.items() if c>=max(5,0.4*len(pages))}
    if not running: return []
    for n,lines in enumerate(split):
        idx=_content_lines(lines); edge=set(idx[:3]+idx[-3:])
        pages[n]='\n'.join(l for i,l in enumerate(lines) if not (i in edge and l.strip() in running))
    return sorted(running)

def _align(rows):
    """Place cells in columns by their horizontal position, so a header with a blank cell or a
    row with a missing value still lines up. rows: [(cells, boxes or None)]; boxes are (x0, x1)
    per cell in reading order (rightmost first)."""
    cols=[]; most=max((len(r[1]) for r in rows if r[1]),default=0)
    # columns come from the fullest rows only; a wide header cell must not merge two columns
    for cells,boxes in (r for r in rows if r[1] and len(r[1])==most):
        for x0,x1 in boxes:
            best=max(cols,key=lambda c:min(c[1],x1)-max(c[0],x0),default=None)
            if best and min(best[1],x1)-max(best[0],x0)>0: best[0]=min(best[0],x0); best[1]=max(best[1],x1)
            else: cols.append([x0,x1])
    cols.sort(key=lambda c:-c[1])
    out=[]
    for cells,boxes in rows:
        row=['']*max(1,len(cols))
        if not boxes: row[0]=' '.join(cells).strip(); out.append(row); continue
        for text,(x0,x1) in zip(cells,boxes):
            n=max(range(len(cols)),key=lambda i:min(cols[i][1],x1)-max(cols[i][0],x0))
            row[n]=(row[n]+' '+text).strip()
        out.append(row)
    return out

def _write_ocr(ctx,value):
    """OCR text, with column-aligned blocks (scanned tables) written as Markdown tables."""
    for kind,part in (value.parts if isinstance(value,ScanText) else _text_parts(value)):
        ctx.write((part if kind=='text' else table(part).rstrip('\n'))+'\n\n')

def _text_parts(value,cells=None):
    """Decoded lines use a tab where a wide gap separates columns. Three or more such lines in a
    row with at least three columns become a Markdown table (borderless tables such as bills of
    quantities); every other tab becomes a space."""
    lines=value.split('\n'); cells=cells if cells and len(cells)==len(lines) else [None]*len(lines)
    parts=[]; n=0; plain=[]
    def flush():
        if plain: parts.append(('text','\n'.join(l.replace('\t',' ') for l in plain))); plain.clear()
    while n<len(lines):
        m=n
        # a table continues over one line without columns (a wrapped description) if the next has them
        while m<len(lines) and (lines[m].count('\t')>=1 or (m>n and m+1<len(lines) and lines[m+1].count('\t')>=1)): m+=1
        block=lines[n:m]
        cols=[l.count('\t')+1 for l in block]
        real=[c for l in block for c in l.split('\t') if c.strip()]
        sensible=sum(1 for c in real if re.search(r'[\u0621-\u064aA-Za-z]{2}|\d',c))
        # guard: a table has a handful of columns and mostly real words or numbers in its cells
        # (dot leaders of a contents page read by OCR give many tiny garbage "columns")
        if sum(1 for c in cols if c>=3)>=3 and max(cols)<=8 and real and sensible>=0.8*len(real):
            flush()
            rows=[(l.split('\t'),cells[n+i]) for i,l in enumerate(block)]
            if all(r[1] or '\t' not in l for r,l in zip(rows,block)): table_rows=_align(rows)
            else:
                width=max(len(c) for c,_ in rows); table_rows=[c+['']*(width-len(c)) for c,_ in rows]
            parts.append(('table',table_rows)); n=m; continue
        plain.append(lines[n]); n+=1
    flush()
    return parts

def _expand_cells(cells):
    """Cell boxes come from PyMuPDF's view of the page, which is poor for legacy fonts: the last
    letter of a word can fall outside its box. Stretch each cell to the middle of the gap to its
    neighbours (and a little at the outer edges)."""
    order=sorted((i for i,c in enumerate(cells) if c),key=lambda i:cells[i][0]); out=list(cells)
    for pos,i in enumerate(order):
        x0,y0,x1,y1=cells[i]
        prev=cells[order[pos-1]][2] if pos>0 else None
        nxt=cells[order[pos+1]][0] if pos+1<len(order) else None
        out[i]=((prev+x0)/2 if prev is not None and prev<=x0 else x0-8, y0, (x1+nxt)/2 if nxt is not None and nxt>=x1 else x1+8, y1)
    return out

def _decoded_parts(model,page):
    """Text and ruled tables of a font-decoded page, top to bottom. Table lines are drawn as real
    lines in these PDFs, so the grid is found from them and each cell is read from its glyphs."""
    tables=[]
    if not page.rotation:
        try: tables=[t for t in page.find_tables().tables if t.row_count>=2 and t.col_count>=2]
        except Exception: tables=[]
    if not tables: return _text_parts(model.decode(page)[0],model.last_cells)
    tables.sort(key=lambda t:t.bbox[1]); parts=[]; top=0.0; width=page.rect.width
    boxes=[tuple(t.bbox) for t in tables]
    for t in tables:
        above=model.decode(page,clip=(0,top,width,t.bbox[1]),exclude=boxes)[0]
        if above.strip(): parts.extend(_text_parts(above,model.last_cells))
        rows=[]
        for row in t.rows:
            cells=[]
            for cell in _expand_cells(list(row.cells)):
                cells.append(model.decode(page,clip=cell,headings=False,columns=False)[0].replace('\n',' ').replace('\t',' ') if cell else '')
            rows.append(cells)
        arabic=sum(1 for r in rows for c in r if AR.search(c)); latin=sum(1 for r in rows for c in r if c and not AR.search(c))
        if arabic>=latin: rows=[r[::-1] for r in rows]          # right-to-left table: first column is the rightmost
        parts.append(('table',[[_fix_presentation_forms(c) for c in r] for r in rows]))
        top=t.bbox[3]
    below=model.decode(page,clip=(0,top,width,page.rect.height+1),exclude=boxes)[0]
    if below.strip(): parts.extend(_text_parts(below,model.last_cells))
    return parts

def render_decoded(value):
    # decoded lines are plain text; keep "### " headings, escape the rest for Markdown
    return '\n'.join(('### '+text(l[4:])) if l.startswith('### ') else text(l) for l in value.split('\n'))

def _decode_legacy_fonts(ctx,doc,pool):
    """Learn the legacy Arabic font codes of this PDF from OCR of a sample of pages, then read
    every such page straight from its codes. Pages the model does not fully understand stay on OCR."""
    if ctx.settings['ocr']=='off' or not ctx.settings.get('decode_fonts',True): return {}
    try:
        legacy=[i for i in range(len(doc)) if _needs_whole_page_ocr(doc[i])]
        if len(legacy)<8: return {}
        model=fontdecode.FontModel(doc)
        if not model.usable(): return {}
        upright=[i for i in legacy if not doc[i].rotation]
        if ctx.settings.get('quality')=='high':
            ctx.warn('Legacy Arabic font codes were learned with the standard OCR models for consistent decoding across quality settings; High still applies to page/image OCR.')
        step=max(1,len(upright)//40); sample=upright[::step][:40]
        ctx.stage('Learning the document fonts',0,len(sample),'Sample page')
        jobs={}
        for n,i in enumerate(sample):
            png=doc[i].get_pixmap(dpi=300,alpha=False).tobytes('png')
            jobs[i]=pool.submit(fontdecode.ocr_words,png,ctx.settings,ctx.work,1) if pool else None
            if not pool: jobs[i]=fontdecode.ocr_words(png,ctx.settings,ctx.work)
        samples={}
        for n,(i,job) in enumerate(jobs.items(),1):
            ctx.stage('Learning the document fonts',n,len(sample),'Sample page')
            samples[i]=job.result() if pool else job
        model.find_spaces(legacy); pairs=model.train(samples); model.learn_shapes()
        if pairs<200: ctx.warn('Legacy font decoding skipped: too few OCR words to learn from.'); return {}
        # Update11: glyphs that only occur in bold headings are missed by evenly spaced sample pages.
        # OCR a few more pages, chosen because they contain the most still-unknown glyphs, then relearn.
        extra=model.pick_extra_pages(legacy,set(samples),max_pages=16)
        if extra:
            ctx.stage('Learning bold and heading fonts',0,len(extra),'Extra page')
            xjobs={}
            for i in extra:
                png=doc[i].get_pixmap(dpi=300,alpha=False).tobytes('png')
                xjobs[i]=pool.submit(fontdecode.ocr_words,png,ctx.settings,ctx.work,1) if pool else fontdecode.ocr_words(png,ctx.settings,ctx.work)
            for n,(i,job) in enumerate(xjobs.items(),1):
                ctx.stage('Learning bold and heading fonts',n,len(extra),'Extra page')
                samples[i]=job.result() if pool else job
            sample=sample+extra
            model.find_spaces(legacy); pairs=model.train(samples); model.learn_shapes()
        # Update13: rare ligature glyphs (a few uses in the whole file) are still unknown; OCR only the lines that contain them
        rects=model.pick_unknown_lines(legacy)
        if rects:
            ctx.stage('Learning rare letter shapes',0,len(rects),'Line')
            ljobs=[]
            for i,r in rects:
                png=doc[i].get_pixmap(dpi=300,clip=r,alpha=False).tobytes('png')
                ljobs.append((i,pool.submit(fontdecode.ocr_words,png,ctx.settings,ctx.work,1,'7',(r.x0,r.y0)) if pool else fontdecode.ocr_words(png,ctx.settings,ctx.work,None,'7',(r.x0,r.y0))))
            for n,(i,job) in enumerate(ljobs,1):
                ctx.stage('Learning rare letter shapes',n,len(rects),'Line')
                samples[i]=list(samples.get(i,[]))+list(job.result() if pool else job)
            model.find_spaces(legacy); pairs=model.train(samples); model.learn_shapes()
        decoded={}; incomplete=[]
        for i in legacy:
            value,known=model.decode(doc[i])
            if known<0.995 or '[?]' in value: incomplete.append(i+1)
            if known>=fontdecode.MIN_KNOWN and AR.search(value):
                decoded[i]=[(kind,_fix_presentation_forms(v) if kind=='text' else v) for kind,v in _decoded_parts(model,doc[i])]
        if incomplete:
            ctx.warn(f'{len(incomplete)} pages contain glyphs that could not be read; [?] marks unresolved glyphs in decoded text. Pages: '+', '.join(map(str,incomplete[:15]))+(' …' if len(incomplete)>15 else '')+'. Compare with the page images.')
        if decoded:
            ctx.counts['pages_decoded_from_fonts']=len(decoded)
            ctx.warn(f'{len(decoded)} of {len(legacy)} pages with legacy Arabic fonts were read from their font codes '
                     f'(learned from OCR of {len(sample)} pages). '
                     f'The other {len(legacy)-len(decoded)} used OCR. Check numbers and tables against the page images.')
        return decoded
    except Exception as e:
        ctx.warn(f'Legacy font decoding was skipped ({type(e).__name__}); OCR was used instead.')
        return {}

_AI=str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789')
def _plausible_year(digits):
    return digits.isdigit() and len(digits)==4 and 1900<=int(digits)<=2099

def _digits_reversed(doc):
    """Some Arabic PDFs (many UN documents) store Arabic-Indic digits in visual order, so text
    extraction returns them backwards (2000 comes out as ٠٠٠٢). Decide per document, from
    four-digit runs in a sample of pages: reversed only if runs that are a valid year only when
    reversed clearly outnumber runs that are a valid year as written. Western digits are not affected."""
    ok=rev=0
    step=max(1,len(doc)//40)
    for i in range(0,len(doc),step):
        try: value=doc[i].get_text()
        except Exception: continue
        for m in re.finditer(r'(?<![٠-٩])[٠-٩]{4}(?![٠-٩])',value):
            d=m.group(0).translate(_AI)
            if _plausible_year(d) and not _plausible_year(d[::-1]): ok+=1
            elif _plausible_year(d[::-1]) and not _plausible_year(d): rev+=1
    return rev>=5 and rev>=3*max(1,ok)

def _reverse_digit_runs(value):
    # a year split by a stray space ("١ ٠٠٢") is joined first, only when the result is a valid year
    def joined(m):
        d=(m.group(1)+m.group(2)).translate(_AI)
        return m.group(1)+m.group(2) if _plausible_year(d[::-1]) else m.group(0)   # joined here, reversed by the next step
    value=re.sub(r'(?<![٠-٩])([٠-٩]) ([٠-٩]{3})(?![٠-٩])',joined,value)
    # a number with single separators (٥٧/١٣, ١٫٥, ٢٠٠٢/٧/٢٧) is one unit on the page: reverse it whole (Update10)
    return re.sub(r'[٠-٩]+(?:[/.:٫٬,\-][٠-٩]+)*',lambda m:m.group(0)[::-1] if len(m.group(0))>1 else m.group(0),value)

def _native_fix(value,flip):
    value=drop_stray_tanween(_fix_presentation_forms(value))
    return _reverse_digit_runs(value) if flip else value

# Private-use glyphs of the Traditional Arabic font used in UN documents (Update10).
# Ligatures become their letters; the rest are shadda/tanween marks placed over a letter,
# which are dropped because their position in the text cannot be recovered reliably.
_PUA_LETTERS={'\ue811':'لمج','\ue812':'به','\ue814':'ته','\ue815':'نه'}
_AR_LETTER=re.compile('[\u0621-\u064a\u066e-\u06d3\u06fa-\u06ff]')   # letters only, not ٫ ٬ ، digits
_LTR_CHAR=re.compile(r'[A-Za-z0-9\u0660-\u0669\u06f0-\u06f9\u00c0-\u024f]')

def _pua(ch):
    return '\ue000'<=ch<='\uf8ff'

def _span_text(span):
    # a ligature body has no text of its own; its letters are the zero-width glyphs on it (Update20)
    return span['text'] if 'text' in span else ''.join(c['c'] for c in span.get('chars',()) if 'lig' not in c)

# Ligature bodies (Update20). InDesign/Adobe PDFs draw some Arabic ligatures (في، بين، تر، نز ...) as a dotless
# body glyph plus zero-width dot glyphs. The dots carry the letters in ToUnicode; the body maps to U+FFFD, which
# MuPDF shows as the raw code (½ Ë Ñ ...). The body's glyph name (u06490631.f = dotless tooth + reh) gives the
# letters it draws, so a letter without dots (the ر of تر) is recovered as well.
_SKELETON={'\u0649':'بتثنيىئ','\u066e':'بتثنيىئ','\u06ba':'ن','\u0631':'رز','\u062d':'حجخ','\u062f':'دذ',
           '\u0633':'سش','\u0635':'صض','\u0637':'طظ','\u0639':'عغ','\u06a1':'فق','\u066f':'ق','\u0647':'هة'}
_BARE={'\u066e':'\u0649','\u06ba':'\u0646','\u06a1':'\u0641','\u066f':'\u0642'}   # a dotless form with no dots on the page

def _skeleton(name):
    """Letters drawn by a glyph named uniXXXX / uXXXXYYYY(.suffix); None when the name says nothing."""
    base=name.split('.')[0]
    hexpart=base[3:] if base.startswith('uni') else base[1:] if base.startswith('u') else ''
    if not hexpart or len(hexpart)%4 or not re.fullmatch('[0-9A-Fa-f]+',hexpart): return None
    letters=''.join(chr(int(hexpart[i:i+4],16)) for i in range(0,len(hexpart),4))
    return letters if all('\u0621'<=ch<='\u06ff' for ch in letters) else None

def _font_key(name):
    return re.sub(r'^[A-Z]{6}\+','',name or '')

def _simple_font_glyphs(doc,xref):
    """Ligature bodies of one simple font: ({shown character: skeleton} for codes whose ToUnicode entry is U+FFFD
    or empty, set of characters the font maps properly, [(advance width, skeleton)] of every ligature glyph).
    MuPDF shows a U+FFFD body as the raw code (½ Ë Ñ); a few ligature glyphs come out as U+FFFD itself, and
    those are told apart by their width."""
    obj=doc.xref_object(xref)
    if '/Type0' in obj: return {},set(),[]
    m=re.search(r'/Encoding\s+(\d+)\s+0\s+R',obj)
    enc=doc.xref_object(int(m.group(1))) if m else obj
    names={}
    m=re.search(r'/Differences\s*\[(.*?)\]',enc,re.S)
    if m:
        code=0
        for tok in re.findall(r'/[^\s/\[\]<>()]+|\d+',m.group(1)):
            if tok[0]=='/': names[code]=tok[1:]; code+=1
            else: code=int(tok)
    m=re.search(r'/ToUnicode\s+(\d+)\s+0\s+R',obj)
    if not m or not names: return {},set(),[]
    cmap=doc.xref_stream(int(m.group(1))).decode('latin-1')
    uni={}
    for blk in re.findall(r'beginbfchar(.*?)endbfchar',cmap,re.S):
        for a,b in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>',blk): uni[int(a,16)]=b.upper()
    for blk in re.findall(r'beginbfrange(.*?)endbfrange',cmap,re.S):
        for a,b,c in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>',blk):
            for k in range(int(a,16),int(b,16)+1): uni.setdefault(k,'X')
    widths={}
    m=re.search(r'/Widths\s*\[([^\]]*)\]',obj); f=re.search(r'/FirstChar\s+(\d+)',obj)
    if m and f:
        for i,w in enumerate(m.group(1).split()):
            try: widths[int(f.group(1))+i]=float(w)
            except ValueError: pass
    junk={}; good=set(); wide=[]
    for code,name in names.items():
        if code>255: continue
        u=uni.get(code); sk=_skeleton(name)
        if u in ('FFFD',''):
            if sk is not None: junk[chr(code)]=sk
        elif u: good.add(chr(code))
        if sk and (len(sk)>1 or u in ('FFFD','')) and widths.get(code): wide.append((widths[code],sk))
    return junk,good,wide

def _ligature_table(doc,page,cache):
    """{font name: (character table, width table)} for the fonts of this page (cached per font object)."""
    table={}; clash=set()
    try: fonts=page.get_fonts()
    except Exception: return {}
    for f in fonts:
        xref,key=f[0],_font_key(f[3])
        if xref not in cache:
            try: cache[xref]=_simple_font_glyphs(doc,xref)
            except Exception: cache[xref]=({},set(),[])
        junk,good,wide=cache[xref]
        if key in table:          # two fonts with one name on the page: keep only what both agree on
            old,oldwide=table[key]
            merged={ch:sk for ch,sk in old.items() if junk.get(ch,sk)==sk and ch not in good}
            merged.update({ch:sk for ch,sk in junk.items() if ch not in old})
            clash|=good
            table[key]=({ch:sk for ch,sk in merged.items() if ch not in clash},[])   # widths of two fonts: ambiguous
        else:
            table[key]=(dict(junk),list(wide)); clash|=good&set(junk)
    return {k:v for k,v in table.items() if v[0] or v[1]}

def _by_width(wide,units):
    """Skeleton of the ligature glyph whose advance width matches (within 1.5%); None if none or ambiguous."""
    hits={sk for w,sk in wide if abs(w-units)<=max(4,0.015*w)}
    return hits.pop() if len(hits)==1 else None

def _mark_ligature_bodies(doc,page,blocks,cache):
    """Tag ligature body characters in rawdict blocks with c['lig'] = the letters the glyph draws (Update20).
    Returns True when the page has any."""
    table=_ligature_table(doc,page,cache)
    if not table: return False
    # rawdict reports the vertical font size. InDesign can use a different horizontal
    # text scale, so a replacement body's advance cannot always be divided by that
    # size. texttrace carries the actual horizontal size at the same glyph origin.
    replacements=[(_font_key(sp.get('font')),c)
                  for b in blocks for line in b.get('lines',()) for sp in line['spans']
                  for c in sp.get('chars',()) if c['c']=='\ufffd']
    trace_sizes={}
    if replacements:
        try:
            for sp in page.get_texttrace():
                key=_font_key(sp.get('font'))
                if not any(k==key for k,_ in replacements): continue
                for _,_,origin,_ in sp.get('chars',()):
                    for k,c in replacements:
                        if (k==key and abs(origin[0]-c['origin'][0])<0.2
                                and abs(origin[1]-c['origin'][1])<0.2):
                            trace_sizes[id(c)]=sp.get('size')
        except Exception:
            pass
    found=False
    for b in blocks:
        for line in b.get('lines',()):
            for sp in line['spans']:
                t=table.get(_font_key(sp.get('font')))
                if not t: continue
                chars,wide=t; size=sp.get('size') or 0
                sp['adobe']=True                                   # font with Adobe ligature glyphs: diacritics sit left
                for c in sp.get('chars',()):
                    if c['c'] in chars: c['lig']=chars[c['c']]; found=True
                    elif c['c']=='\ufffd' and wide and size:
                        sk=_by_width(wide,(c['bbox'][2]-c['bbox'][0])*1000/size)
                        if not sk and trace_sizes.get(id(c)):
                            sk=_by_width(wide,(c['bbox'][2]-c['bbox'][0])*1000/trace_sizes[id(c)])
                        if sk: c['lig']=sk; found=True
    return found

def _zero_width_letter(c):
    return c['bbox'][2]-c['bbox'][0]<0.3 and bool(AR.match(c['c'])) and not unicodedata.combining(c['c'][0])

def _restore_dropped_dots(page,blocks,learned):
    """MuPDF's text extraction drops some dot glyphs of a ligature body (usually two dot glyphs on one spot);
    the page's glyph trace still has them. Each dot glyph (font, glyph id) is learned from the dots MuPDF did
    keep, per letter family, and a dropped one is put back as a zero-width letter (Update20)."""
    try: trace=page.get_texttrace()
    except Exception: return
    dots=[]
    for sp in trace:
        key=_font_key(sp.get('font'))
        for u,gid,origin,bbox in sp.get('chars',()):
            if bbox[2]-bbox[0]<0.3 and gid>0: dots.append((key,gid,origin[0],origin[1],chr(u) if u>0 else ''))
    if not dots: return
    kept=[]
    for b in blocks:
        for line in b.get('lines',()):
            for sp in line['spans']:
                for c in sp.get('chars',()):
                    if _zero_width_letter(c): kept.append((_font_key(sp.get('font')),c))
    used=set()
    for key,c in kept:
        x,y=c['origin']
        for i,(k,gid,dx,dy,_) in enumerate(dots):
            if i not in used and k==key and abs(dx-x)<0.15 and abs(dy-y)<0.15:
                used.add(i); learned.setdefault((k,gid),{}); learned[(k,gid)][c['c']]=learned[(k,gid)].get(c['c'],0)+1; break
    for b in blocks:
        for line in b.get('lines',()):
            for sp in line['spans']:
                key=_font_key(sp.get('font')); size=sp.get('size',11); chars=sp.get('chars',[])
                for idx in range(len(chars)-1,-1,-1):
                    body=chars[idx]
                    if not body.get('lig'): continue
                    x0,x1=body['bbox'][0],body['bbox'][2]; y=body['origin'][1]
                    inside=[c for s2 in line['spans'] for c in s2.get('chars',()) if _zero_width_letter(c) and x0+0.05<c['bbox'][0]<x1-0.05]
                    _,n=_fill_ligature(body['lig'],[c['c'] for c in sorted(inside,key=lambda c:-c['bbox'][0])])
                    families=[_SKELETON[ch] for ch in body['lig'] if ch in _SKELETON]
                    if n>=len(families): continue
                    extra=[]
                    for i,(k,gid,dx,dy,u) in enumerate(dots):
                        if i in used or k!=key or not (x0+0.05<dx<x1-0.05) or abs(dy-y)>0.8*size: continue
                        if any(abs(c['origin'][0]-dx)<0.15 and abs(c['origin'][1]-dy)<0.15 for c in inside): continue
                        extra.append((i,gid,dx,dy,u))
                    if not extra: continue
                    # the dots MuPDF kept fill the first slots; dropped ones go to the slots still open, right to left
                    open_slots=[ch for ch in body['lig'] if ch in _SKELETON]
                    kept_letters=sorted(inside,key=lambda c:-c['bbox'][0])
                    for c in kept_letters:
                        for j,ch in enumerate(open_slots):
                            if c['c'] in _SKELETON[ch]: del open_slots[j]; break
                    new=[]
                    for i,gid,dx,dy,u in sorted(extra,key=lambda e:-e[2]):
                        if not open_slots: break
                        fam=_SKELETON[open_slots[0]]
                        seen=learned.get((key,gid),{})
                        letter=max((l for l in seen if l in fam),key=lambda l:seen[l],default=None) or (u if u in fam else None)
                        if not letter: continue
                        used.add(i); del open_slots[0]
                        new.append({'c':letter,'origin':(dx,dy),'bbox':(dx,body['bbox'][1],dx,body['bbox'][3]),'restored':True})
                    chars[idx+1:idx+1]=new

def _fill_slots(skeleton,dots):
    """[(letter, index of the dot letter it came from or None)] for a ligature body: each dotless skeleton letter
    takes the next dot letter of its family (ى takes ت، ن، ي ...; ر takes ز); a skeleton letter without dots on
    the page stays as drawn (the ر of تر). Unknown skeleton: the dot letters themselves."""
    if not skeleton: return [(d,i) for i,d in enumerate(dots)]
    out=[]; used=0
    for ch in skeleton:
        family=_SKELETON.get(ch)
        if family and used<len(dots) and dots[used] in family:
            out.append((dots[used],used)); used+=1
        else: out.append((_BARE.get(ch,ch),None))
    return out

def _fill_ligature(skeleton,dots):
    """(letters of a ligature body, number of dot letters used)."""
    slots=_fill_slots(skeleton,dots)
    return ''.join(l for l,_ in slots),sum(1 for _,i in slots if i is not None)

def _needs_visual_order(spans):
    """True for an Arabic line whose stored order cannot be trusted: it contains a private-use
    glyph, or its pieces are not stored right to left. MuPDF then starts such lines in the middle
    or puts the paragraph number at the end."""
    chars=[c for s in spans for c in s.get('chars',())]
    if not chars: return False
    if any('lig' in c for c in chars): return True          # ligature body with dot glyphs (Update20)
    txt=''.join(c['c'] for c in chars)
    if not (AR.search(txt) or re.search('[\ufb50-\ufdff\ufe70-\ufeff]',txt)): return False
    if any(_pua(ch) for ch in txt): return True
    # Word/LibreOffice ligatures (لى، ير، تز، لي) store one letter with zero width on the edge of the
    # other; the stored order is then wrong (عىل for على). Position rebuild orders them (Update18).
    for c in chars:
        ch=c['c']
        if c['bbox'][2]-c['bbox'][0]<0.3 and AR.match(ch) and not unicodedata.combining(ch) and ch!='\u0640': return True
    # In an Arabic line stored in reading order, each Arabic letter lies to the LEFT of the previous one,
    # even across numbers, brackets and spaces between them. A jump to the right means the line is stored
    # in visual order (browser-printed PDFs such as Etimad), so rebuild it (Update18). Only for lines that
    # are mostly Arabic: Arabic words inside an English sentence legitimately move right.
    letters=[c for c in chars if AR.match(c['c']) and not unicodedata.combining(c['c']) and c['bbox'][2]-c['bbox'][0]>=0.3]
    latin=sum(1 for c in chars if c['c'].isascii() and c['c'].isalpha())
    if len(letters)>latin:
        size=max((sp.get('size',11) for sp in spans),default=11)
        for a,b in zip(letters,letters[1:]):
            if b['bbox'][0]>a['bbox'][2]+1.5*size: return True
    centers=[(s['bbox'][0]+s['bbox'][2])/2 for s in spans if _span_text(s).strip()]
    return any(b>a+1 for a,b in zip(centers,centers[1:]))

def _visual_line(spans):
    """Rebuild an Arabic line from character positions (right to left), then put left-to-right
    runs (Latin, digits, and the spaces and signs between them) back in reading order."""
    clusters=[]; bodies=[]; pieces={}
    for s in spans:
        size=s.get('size',11)
        for c in s.get('chars',()):
            ch=c['c']; x0,_,x1,_=c['bbox']
            if 'lig' in c or (ch=='\ufffd' and x1-x0>=0.3):
                # ligature body (Update20): its letters are the zero-width dot glyphs on it, filled in below
                cl=[x0,ch,x1,size]; clusters.append(cl); bodies.append((cl,c.get('lig'),'lig' in c)); continue
            if _pua(ch):
                ch=_PUA_LETTERS.get(ch,'')
                if not ch: continue
            mark=unicodedata.normalize('NFKC',ch).replace('\u0640','').strip()
            if ch.strip() and mark and all(unicodedata.combining(m) for m in mark):
                clusters.append([x0,mark,x1,size,'mark'])       # attached to its glyph below
                continue
            clusters.append([x0,ch if ch.strip() else ' ',x1,size])
    for body,skeleton,known in bodies:
        x0,x1=body[0],body[2]
        dots=sorted([c for c in clusters if len(c)==4 and c is not body and c[2]-c[0]<0.3 and AR.match(c[1])
              and not unicodedata.combining(c[1][0]) and x0+0.05<c[0]<x1-0.05],key=lambda c:-c[0])   # right to left
        if not known and not dots: continue                 # a plain unknown glyph: left as it is
        slots=_fill_slots(skeleton or '',[c[1] for c in dots])
        filled=''.join(l for l,_ in slots); used=sum(1 for _,i in slots if i is not None)
        # where each letter sits, so a diacritic on the body goes after the right one (تبيِّن، اختَرْ)
        n=len(slots) or 1
        pieces[id(body)]=[[l,dots[i][0] if i is not None else x1-(k+0.5)*(x1-x0)/n,''] for k,(l,i) in enumerate(slots)]
        spots=[c[0] for c in clusters if c is not body and c[1]!=' ' and c[2]-c[0]<0.3 and x0+0.05<c[0]<x1-0.05]
        for c in dots[:used]: clusters.remove(c)
        # MuPDF puts a "space" after a dot glyph when the next glyph lies to its left; inside the body, or starting
        # at a dot or diacritic on it, that is no word space
        for sp in [c for c in clusters if len(c)==4 and c[1]==' ' and ((x0+0.05<(c[0]+c[2])/2<x1-0.05 and c[2]-c[0]<x1-x0)
                   or any(abs(c[2]-x)<0.2 for x in spots))]:
            clusters.remove(sp)
        if filled: body[1]=filled
        else: clusters.remove(body)
    # A browser-printed PDF can store a zero-width letter plus a "space" that starts exactly where the
    # letter sits (كل ًيا for كليًا); that space is the letter's own width (Update18).
    # Only for a joining letter (ي ب ت ...) on the edge of a letter that ends a ligature (ا ى ر ...): a zero-width
    # alef of لا sits at the same place as a genuine word space, and that space must stay.
    endings='اأإآٱدذرزوؤىة'
    for z in [c for c in clusters if len(c)==4 and c[1]!=' ' and c[2]-c[0]<0.3 and AR.match(c[1]) and c[1][:1] not in endings]:
        base=next((g for g in clusters if len(g)==4 and g[1][:1] in endings and g[2]-g[0]>=0.3 and abs(g[2]-z[0])<0.3),None)
        sp=next((c for c in clusters if c[1]==' ' and abs(c[0]-z[0])<0.3),None) if base is not None else None
        if sp is not None: z[2]=sp[2]; clusters.remove(sp)
    glyphs=[c for c in clusters if c[1]!=' ' and len(c)==4 and c[2]-c[0]>=0.3]
    def owner(z):
        # Ligatures store a letter or a diacritic with zero width on or inside the glyph it belongs to
        # (عىل for على, تأخري for تأخير). Its owner is the glyph containing its position, preferring the
        # one whose right edge it sits on (Update16, Update18).
        near=[o for o in glyphs if o[0]-0.3<=z[0]<=o[2]+0.3]
        if not near: return None
        # A zero-width alef or hamza-alef inside a lam glyph is the alef of the lam-alef ligature (الأيام، والآخر):
        # it belongs to that lam, even when it also touches the right edge of the next letter (Update20).
        # One exactly on a lam's edge (اللاجئين) is left to the edge rule below.
        if z[1][:1] in '\u0627\u0623\u0625\u0622' and len(z)==4:
            lams=[o for o in near if o[1][-1:]=='\u0644' and o[0]+0.15<z[0]<o[2]-0.15]
            if lams: return min(lams,key=lambda o:abs((o[0]+o[2])/2-z[0]))
        return min(near,key=lambda o:abs(o[2]-z[0]))
    # Adobe/InDesign Arabic fonts place a diacritic at the LEFT edge of its letter (التعلُّم، وتُعدُّ، جديداً), Word at
    # the right edge; the font tells which (Update20)
    adobe=any(s.get('adobe') for s in spans)
    def mark_owner(m):
        if not adobe: return owner(m)
        near=[o for o in glyphs if o[0]-0.3<=m[0]<=o[2]+0.3]
        return min(near,key=lambda o:abs(o[0]-m[0])) if near else None
    for m in [c for c in clusters if len(c)==5]:
        o=mark_owner(m) or next((c for c in reversed(clusters[:clusters.index(m)]) if c[1]!=' ' and len(c)==4),None)
        if o is not None and id(o) in pieces and pieces[id(o)]:
            part=min(pieces[id(o)],key=lambda q:abs(q[1]-m[0])); part[2]+=m[1]
            o[1]=''.join(q[0]+q[2] for q in pieces[id(o)])
        elif o is not None: o[1]+=m[1]
    clusters=[c for c in clusters if len(c)==4]
    marks=[c for c in clusters if c[1]!=' ']
    # Which letter of the ligature comes first: a letter that never joins the next one (ا د ر ز و ى ة ...)
    # can only be the last letter of a ligature. Word stores عىل (zero-width ى after ل); a browser stores
    # كليًا (zero-width ي before ا) - the joining rule orders both (Update18).
    nonjoin='اأإآٱدذرزوؤىة'
    key={}
    for m in marks:
        if m[2]-m[0]<0.3:
            o=owner(m)
            if o is None: continue
            centre=(o[0]+o[2])/2
            before=m[1][:1] not in nonjoin and o[1][:1] in nonjoin
            key[id(m)]=centre+0.001 if before else centre-0.001
    marks.sort(key=lambda c:-key.get(id(c),(c[0]+c[2])/2))
    # The lam-alef ligature is stored as two characters in the same box; position cannot order them,
    # but in reading order lam always comes first (Update16).
    for i in range(len(marks)-1):
        a,b=marks[i],marks[i+1]
        overlap=min(a[2],b[2])-max(a[0],b[0]); width=min(a[2]-a[0],b[2]-b[0]) or 1
        if overlap>=0.8*width and a[1][:1] in 'اأإآ' and b[1][:1]=='ل': marks[i],marks[i+1]=b,a
    spaces=[((sp[0]+sp[2])/2,sp[2]-sp[0]) for sp in clusters if sp[1]==' ']
    digit=lambda u: u[1] in '0123456789٠١٢٣٤٥٦٧٨٩'
    units=[]; prev=None
    for c in marks:
        if id(c) in key:                       # zero-width part of a neighbouring glyph: no gap check
            units.append(c); continue
        if prev is not None:
            gap=prev[0]-c[2]                              # right unit's left edge minus this unit's right edge
            between=[w for m,w in spaces if c[2]-0.5<=m<=prev[0]+0.5]
            thin=digit(c) and digit(prev) and gap<0.2*c[3] and all(w<0.2*c[3] for w in between)
            if not thin and (gap>0.2*c[3] or between): units.append(' ')   # a thin space inside a number (1 514) is not a word space
        units.append(c); prev=c
    seq=[u if u==' ' else _fix_presentation_forms(u[1]) for u in units]
    seq=[u for u in seq if u]                            # kashida and dropped marks leave empty units
    strong=[bool(_LTR_CHAR.match(u)) for u in seq]
    n=len(seq); ltr=strong[:]
    # Neutrals between two left-to-right parts join them: any neutrals between Latin text,
    # a single separator between numbers (20.5, 2002/5, MC-30). Numbers separated by spaces
    # stay separate numbers in Arabic order (١٧ - ١٨).
    latin=[bool(re.match('[A-Za-z\u00c0-\u024f]',u)) for u in seq]
    i=0
    while i<n:
        if not strong[i]:
            j=i
            while j<n and not strong[j] and not _AR_LETTER.search(seq[j]): j+=1
            if i>0 and j<n and strong[i-1] and strong[j]:
                gapchars=''.join(seq[i:j])
                an=lambda u: bool(re.match('[\u0660-\u0669]',u[:1]))
                # a hyphen between two Arabic-Indic numbers is neutral in bidi: the numbers keep right-to-left order (Update13)
                hyphen_between_an = gapchars=='-' and an(seq[i-1][-1:]) and an(seq[j])
                if latin[i-1] or latin[j] or (len(gapchars)==1 and gapchars in '.,:/-٫٬' and not hyphen_between_an):
                    for k in range(i,j): ltr[k]=True
            i=max(j,i+1)
        else: i+=1
    # a bracket pair whose contents are all left to right belongs to that run: (1514 (XV))
    for _ in range(3):
        for a,b in _bracket_pairs(seq):
            inner=range(a+1,b)
            if any(latin[k] for k in inner) and not any(_AR_LETTER.search(seq[k]) for k in inner):
                for k in range(a,b+1): ltr[k]=True
    out=[]; i=0
    while i<n:
        if ltr[i]:
            j=i
            while j<n and ltr[j]: j+=1
            out.extend(seq[i:j][::-1]); i=j
        else:
            out.append(seq[i]); i+=1
    return re.sub(' {2,}',' ',''.join(out)).strip()

_OPEN,_CLOSE='([{','\x29]}'
def _bracket_pairs(seq):
    """Matching bracket positions in a unit sequence. Fonts differ in whether they map the drawn
    shape or the meaning, so pair by whichever reading balances."""
    for opens,closes in ((_OPEN,_CLOSE),(_CLOSE,_OPEN)):
        stack=[]; pairs=[]; ok=True
        for i,u in enumerate(seq):
            if len(u)==1 and u in opens: stack.append((i,opens.index(u)))
            elif len(u)==1 and u in closes:
                if stack and stack[-1][1]==closes.index(u): pairs.append((stack.pop()[0],i))
                else: ok=False
        if ok and not stack and pairs: return pairs
    return []

def _balance_brackets(value):
    """Some Arabic fonts map a bracket to its mirror, so a pair reads )..( instead of (..).
    Pair each bracket with the next opposite one (nesting allowed) and swap the pairs that
    start with a closing bracket. Unpaired brackets are left alone. Works across lines, so
    call it on a whole text block (Update10)."""
    chars=list(value)
    for o,c in zip(_OPEN,_CLOSE):
        stack=[]
        for i,ch in enumerate(chars):
            if ch not in (o,c): continue
            nxt=chars[i+1] if i+1<len(chars) else ' '; prv=chars[i-1] if i else ' '
            if stack and chars[stack[-1]]!=ch:
                j=stack.pop()
                if chars[j]==c:
                    if prv.strip(): chars[j],chars[i]=o,c    # reversed pair hugging its text: )..(
                    else: stack.append(i)                    # '(' after a space opens a new pair
            elif ch==c and not nxt.strip():
                continue                                     # list marker '١) ' or a stray closer: never an opener
            else: stack.append(i)
    return ''.join(chars)

def _bbox_key(bbox):
    return tuple(round(v) for v in bbox)

def _image_xrefs(page):
    """{rounded image bbox: xref} for the images drawn on a page."""
    try: return {_bbox_key(i['bbox']):i.get('xref',0) for i in page.get_image_info(xrefs=True)}
    except Exception: return {}

def _repeated_images(doc,min_pages=3):
    """xrefs of images drawn on at least min_pages pages: logos, letterheads, page decorations (Update16)."""
    seen={}
    for page in doc:
        for x in set(_image_xrefs(page).values()):
            if x: seen[x]=seen.get(x,0)+1
    return {x for x,n in seen.items() if n>=min_pages}

def _native_tables(page):
    """Use visible rules, excluding background fills that create false cells.

    PDF producers often draw borders as thin filled rectangles rather than
    strokes. Keep those, but exclude broad fills and pale shading strips.
    """
    drawings=page.get_drawings()
    def color(d): return tuple(round(c,3) for c in (d.get('fill') or (1,)))
    backgrounds={color(d) for d in drawings if d['type']=='f' and
                 min(d['rect'].width,d['rect'].height)>3 and min(color(d))>=0.85}
    paths=[d for d in drawings if d['type']!='f' or
           (min(d['rect'].width,d['rect'].height)<=3 and color(d) not in backgrounds)]
    return page.find_tables(paths=paths).tables

def _table_rows(t,blocks,hidden):
    """Cell text rebuilt from character positions (Update16). PyMuPDF's table extraction orders the
    characters of a cell left to right, which writes every Arabic cell backwards; this uses the same
    visual-order rebuild as damaged native lines. Cells keep their line breaks."""
    chars=[]
    for b in blocks:
        if b.get('type')!=0: continue
        for li,line in enumerate(b.get('lines',())):
            for sp in line['spans']:
                if sp.get('alpha',255)==0: continue
                for c in sp.get('chars',()):
                    r=fitz.Rect(c['bbox'])
                    if not _inside(r,hidden): chars.append(((id(b),li),sp.get('size',11),c,(r.x0+r.x1)/2,(r.y0+r.y1)/2,r.y0))
    rows=[]
    for row in t.rows:
        out=[]
        for cell in row.cells:
            if cell is None: out.append(None); continue
            box=fitz.Rect(cell)
            inside=[x for x in chars if box.x0<=x[3]<=box.x1 and box.y0<=x[4]<=box.y1]
            groups=[]          # [centre y, size, chars]; MuPDF splits English inside Arabic into its own line
            for key,size,c,cx,cy,y0 in sorted(inside,key=lambda x:x[4]):
                if groups and abs(cy-groups[-1][0])<=0.5*max(size,groups[-1][1]): groups[-1][2].append(c)
                else: groups.append([cy,size,[c]])
            arabic_cell=any(AR.search(x[2]['c']) for x in inside)
            parts=[_visual_line([{'size':size,'chars':cs}]) if arabic_cell
                   else ''.join(c['c'] for c in sorted(cs,key=lambda c:c['bbox'][0])).strip()
                   for _,size,cs in groups]
            out.append(drop_stray_tanween('\n'.join(x for x in parts if x)))   # Cleanup2b: cells skip _native_fix
        rows.append(out)
    return rows

def _stored_order_ligatures(spans):
    """Text of a rotated or curved line with ligature bodies, in stored order: character positions cannot be
    compared there, but these PDFs store each body just before its dot letters (Update20)."""
    chars=[c for s in spans for c in s.get('chars',())]
    out=[]; i=0
    while i<len(chars):
        c=chars[i]; i+=1
        if 'lig' not in c: out.append(c['c']); continue
        skeleton=c['lig']; dots=[]; j=i
        while j<len(chars) and len(dots)<len(skeleton or 'xx'):
            ch=chars[j]['c']
            if AR.match(ch) and not unicodedata.combining(ch): dots.append(ch); j+=1
            elif ch==' ' and '\u06ba' in skeleton[len(dots):len(dots)+1] and j+1<len(chars) and chars[j+1]['c']=='\u0646': j+=1
            else: break
        filled,used=_fill_ligature(skeleton,dots)
        # consume exactly the dot letters used (and a space skipped before a noon dot)
        k=i; n=0
        while n<used and k<j:
            if chars[k]['c']!=' ': n+=1
            k+=1
        out.append(filled); i=k
    return ''.join(out)

def _join_split_lines(lines):
    """MuPDF sometimes splits one drawn line in two (pieces drawn out of order). The dot letters of a ligature
    body can then sit in the other piece. Join such same-baseline pieces so positions order them (Update20)."""
    out=list(lines)
    for line in lines:
        if line not in out or abs(line.get('dir',(1,0))[1])>=0.01: continue
        chars=[c for s in line['spans'] for c in s.get('chars',())]
        orphans=[c for c in chars if 'lig' in c and not any(z is not c and z['bbox'][2]-z['bbox'][0]<0.3 and AR.match(z['c'])
                  and c['bbox'][0]+0.05<z['bbox'][0]<c['bbox'][2]-0.05 for z in chars)]
        for body in orphans:
            y=body['origin'][1]; size=max((s.get('size',11) for s in line['spans']),default=11)
            for other in out:
                if other is line or abs(other.get('dir',(1,0))[1])>=0.01: continue
                oc=[c for s in other['spans'] for c in s.get('chars',())]
                if any(z['bbox'][2]-z['bbox'][0]<0.3 and AR.match(z['c']) and abs(z['origin'][1]-y)<0.6*size
                       and body['bbox'][0]+0.05<z['bbox'][0]<body['bbox'][2]-0.05 for z in oc):
                    line['spans']=line['spans']+other['spans']
                    line['bbox']=tuple(fitz.Rect(line['bbox'])|fitz.Rect(other['bbox']))
                    out.remove(other); break
    return out

def _line_text(line,hidden,flip):
    spans=[s for s in line['spans'] if not _invisible(s,hidden)]
    if abs(line.get('dir',(1,0))[1])>=0.01 and any('lig' in c for s in spans for c in s.get('chars',())):
        return _native_fix(_stored_order_ligatures(spans),flip)
    if _needs_visual_order(spans):
        return drop_stray_tanween(fix_text(_visual_line(spans)))   # digits already in visual order: no flip
    return _native_fix(''.join(_span_text(s) for s in spans),flip)

def extract_pdf(ctx):
    with fitz.open(ctx.source) as doc:
        if doc.needs_pass: raise RuntimeError('Password-protected PDF; no password was attempted.')
        ctx.counts['pages']=len(doc)
        flip=_digits_reversed(doc)
        if flip: ctx.warn('Arabic-Indic digits in this PDF are stored backwards; the digit order was corrected in text read from the file. Check numbers against the page images.')
        # Page text is collected per page and written at the end, so running headers can be removed.
        buffers=[]; write=ctx.write; ctx.write=lambda value: buffers[-1].append(value)
        workers=_workers() if ctx.settings['ocr']!='off' else 1
        pool=ThreadPoolExecutor(workers) if workers>1 else None
        pending={}; scanned=[0]
        decoded=_decode_legacy_fonts(ctx,doc,pool)   # {page index: text} for pages read straight from font codes
        repeated=_repeated_images(doc)
        ligcache={}
        def prefetch(index):
            # Render upcoming unreadable-font pages here (PyMuPDF stays on this thread) and OCR them in parallel.
            while pool and scanned[0]<len(doc) and scanned[0]<=index+workers*2:
                j=scanned[0]; scanned[0]+=1
                try:
                    if j not in decoded and _needs_whole_page_ocr(doc[j]):
                        pix=doc[j].get_pixmap(dpi=300,alpha=False); png=pix.tobytes('png')
                        pending[j]=(png,pool.submit(transcribe,png,ctx.settings,ctx.work,f'Page {j+1}',True,1))
                except Exception: pass  # the normal page path below reports the problem
        try:
          for index,page in enumerate(doc):
            ctx.stage(f'Reading page {index+1} of {len(doc)}',index+1,len(doc),'Page')
            buffers.append([]); ctx.write(f'## Page {index+1}\n\n')
            try:
                prefetch(index)
                if index in decoded:
                    for annotation in page.annots() or []:
                        content=annotation.info.get('content')
                        if content:ctx.write('Annotation: '+text(content)+'\n\n')
                    pix=page.get_pixmap(dpi=120,alpha=False)
                    ctx.write(f'[Page {index+1} image for review]({ctx.asset(pix.tobytes("png"))})\n\n')
                    for kind,part in decoded[index]:
                        ctx.write((render_decoded(part) if kind=='text' else table(part).rstrip('\n'))+'\n\n')
                    continue
                if index in pending:
                    png,future=pending.pop(index)
                    for annotation in page.annots() or []:
                        content=annotation.info.get('content')
                        if content:ctx.write('Annotation: '+text(content)+'\n\n')
                    ctx.write(f'![Page {index+1}]({ctx.asset(png)})\n\n')
                    ctx.stage(f'Reading image text: Page {index+1}')
                    result=_fix_presentation_forms(apply_result(ctx,future.result()))
                    if result: _write_ocr(ctx,result)
                    ctx.warn(f'Page {index+1}: unreadable native character codes; whole-page image retained for OCR and layout review.')
                    continue
                words=page.get_text('words',sort=True)
                blocks=page.get_text('rawdict',sort=True)['blocks']   # per-character boxes (Update10)
                if _mark_ligature_bodies(doc,page,blocks,ligcache):   # ½ Ë Ñ ... ligature bodies (Update20)
                    _restore_dropped_dots(page,blocks,ligcache.setdefault('dots',{}))
                for b in blocks:
                    for line in b.get('lines',()):
                        for sp in line['spans']: sp['text']=_span_text(sp)
                hidden=_hidden_layer(page,blocks)
                words=[w for w in words if not _inside(fitz.Rect(w[:4]),hidden)]
                visible=_visible_text(page,blocks,hidden)
                for annotation in page.annots() or []:
                    content=annotation.info.get('content')
                    if content:ctx.write('Annotation: '+text(content)+'\n\n')
                if _unusable_text(page,visible):
                    _read_region(ctx,page,page.rect*page.derotation_matrix,f'Page {index+1}')
                    ctx.warn(f'Page {index+1}: unreadable native character codes; whole-page image retained for OCR and layout review.')
                    continue
                # Scanners/exporters can represent one page using overlapping
                # large rasters. OCR the displayed composite once, so stamp
                # cleanup and ruled grids see the complete page, not fragments.
                image_area=sum(abs(fitz.Rect(b['bbox'])&(page.rect*page.derotation_matrix))
                               for b in blocks if b['type']==1)
                image_count=sum(b['type']==1 for b in blocks)
                # A single scan must retain its original raster dimensions.
                # Its displayed PDF rectangle may stretch the aspect ratio;
                # rendering it again can distort Arabic letter shapes.
                composite_scan=(image_count>1 and image_area>=abs(page.rect)*.05)
                # "No useful text": only punctuation/dashes survive (e.g. VOL 1.1 pages 1-3) counts as empty (Cleanup4).
                useful_chars=sum(c.isalnum() for c in visible)
                # A hidden OCR layer with hundreds of spans but almost no visible letters is a scan whose
                # visible residue is noise (VOL 1.1 pages 43, 100, 163...): read the page image instead (Cleanup5).
                if len(hidden)>=20 and useful_chars<30: useful_chars=0
                # Some scanners draw the page-sized raster without reporting it as an image block, leaving only
                # small stamp/signature blocks: the page would be read as empty. A page with no useful text and a
                # page-sized raster is read as a whole page (Cleanup4).
                if not composite_scan and useful_chars<3:
                    try: composite_scan=any(im[2]*im[3]>=300000 for im in page.get_images(full=True))
                    except Exception: pass
                if (useful_chars<3 and composite_scan
                        and ctx.settings.get('quality')!='quick' and not ctx.settings.get('quick')):
                    dpi=300 if ctx.settings.get('quality')=='high' else 200
                    _read_region(ctx,page,page.rect*page.derotation_matrix,f'Page {index+1}',dpi=dpi)
                    ctx.warn(f'Page {index+1}: image-only scan composited and read once; original displayed page retained.')
                    continue
                # Broken word coordinates must never erase pixels needed for OCR.
                words=[w for w in words if not _garbled(w[4])]
                tables=[]
                try: tables=list(_native_tables(page))
                except Exception: ctx.warn(f'Page {index+1}: table detection failed; text and page visual retained.')
                # Only retained tables may suppress their native text blocks.
                tables=[t for t in tables if not _inside(fitz.Rect(t.bbox),hidden)]
                elements=[]
                for t in tables:
                    try: rows=[[_balance_brackets(c) if isinstance(c,str) else c for c in row] for row in _table_rows(t,blocks,hidden)]
                    except Exception: rows=[[_balance_brackets(_native_fix(c,flip)) if isinstance(c,str) else c for c in row] for row in t.extract()]
                    if any(_garbled(c,0.2) for row in rows for c in row if isinstance(c,str)):
                        elements.append((t.bbox[1],t.bbox[0],'ocrblock',fitz.Rect(t.bbox)))
                    else:elements.append((t.bbox[1],t.bbox[0],'table',rows))
                # Text of every block first, so brackets can be repaired across blocks: MuPDF often
                # splits a paragraph, leaving )..( pairs whose halves sit in different blocks (Update10).
                texts={}
                for bi,b in enumerate(blocks):
                    if b['type']==0 and not any(fitz.Rect(t.bbox).contains(fitz.Rect(b['bbox'])) for t in tables):
                        texts[bi]='\n'.join(_line_text(line,hidden,flip) for line in _join_split_lines(b['lines'])).strip()
                joined='\n\x00\n'.join(texts.values())
                if AR.search(joined):
                    texts=dict(zip(texts,_balance_brackets(joined).split('\n\x00\n')))
                for bi,b in enumerate(blocks):
                    rect=fitz.Rect(b['bbox'])
                    if b['type']==0:
                        if bi not in texts: continue
                        value=texts[bi]
                        if value and _garbled(value,0.2):
                            elements.append((rect.y0,rect.x0,'ocrblock',rect)); continue
                        if value:
                            size=max((s['size'] for line in b['lines'] for s in line['spans']),default=11)
                            prefix='### ' if size>=16 and len(value)<160 else ''
                            elements.append((rect.y0,rect.x0,'text',prefix+text(value)+'\n\n'))
                    elif b['type']==1:
                        elements.append((rect.y0,rect.x0,'image',b))
                # Update16: logos and icons are not OCR'd (they only produced noise and time); a scan cut into
                # many small tiles is OCR'd once as the region the tiles cover.
                # An image that repeats on 3+ pages is a logo or letterhead; a tiny one (<3% of the page) is an
                # icon or stamp. Neither is OCR'd. Other images are OCR'd as before, however small: they can hold
                # real text. Many tiny tiles covering 40%+ of the page are a cut-up scan, OCR'd as one region.
                pa=abs(page.rect)
                marks=_image_xrefs(page)
                images=[e for e in elements if e[2]=='image']
                tiny=[e for e in images if abs(fitz.Rect(e[3]['bbox']))<0.03*pa]
                if tiny and sum(abs(fitz.Rect(e[3]['bbox'])) for e in tiny)>=0.4*pa:
                    # tiles first: blank tiles of a scan are often the same image on every page
                    union=fitz.Rect(tiny[0][3]['bbox'])
                    for e in tiny[1:]: union|=fitz.Rect(e[3]['bbox'])
                    elements=[e for e in elements if e not in tiny]+[(union.y0,union.x0,'image',{'bbox':tuple(union),'type':1})]
                    images=[e for e in images if e not in tiny]; tiny=[]
                logos=[e for e in images if e not in tiny and marks.get(_bbox_key(e[3]['bbox'])) in repeated]
                skip=logos+tiny
                if skip: elements=[e if e not in skip else (e[0],e[1],'smallimage',e[3]) for e in elements]
                found=False
                for _,__,kind,value in sorted(elements,key=lambda x:(x[0],x[1])):
                    if kind=='smallimage':
                        clip=(fitz.Rect(value['bbox'])*page.rotation_matrix)&page.rect
                        if not clip.is_empty:
                            pix=page.get_pixmap(matrix=fitz.Matrix(150/72,150/72),clip=clip,alpha=False)
                            with Image.open(io.BytesIO(pix.tobytes('png'))) as im: ctx.image(im.convert('RGB'),f'Page {index+1} image',ocr=False)
                        continue
                    if kind=='text': ctx.write(value); found=True
                    elif kind=='table': ctx.write(table(value)); found=True
                    elif kind=='ocrblock':
                        found=_read_region(ctx,page,fitz.Rect(value)+(-4,-4,4,4),f'Page {index+1} text block') or found
                        ctx.warn(f'Page {index+1}: unreadable native text block replaced by a retained image and OCR where enabled; review the transcription.')
                    else:
                        b=value; rect=fitz.Rect(b['bbox']); label=f'Page {index+1} image'
                        # Render in its displayed orientation. Mask native text before OCR,
                        # so a native header never hides a scanned body or gets duplicated.
                        clip=(rect*page.rotation_matrix)&page.rect
                        if clip.is_empty:
                            ctx.warn(label+': image lies outside the page; skipped empty clip.'); continue
                        pix=page.get_pixmap(matrix=fitz.Matrix(300/72,300/72),clip=clip,alpha=False)
                        image=Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
                        ctx.image(image,label,ocr=False)
                        if ctx.settings['ocr']!='off':
                            overlap=[w for w in words if not (fitz.Rect(w[:4]) & rect).is_empty]
                            # Preserve original scan resolution when no native text needs masking.
                            # Re-rendering an already-raster image can damage Arabic glyph shapes.
                            if not overlap and not page.rotation and page.rect.contains(rect) and b.get('image'):
                                try: image=Image.open(io.BytesIO(b['image'])).convert('RGB')
                                except Exception: pass  # e.g. JBIG2/CCITT scans: keep the rendered image
                            draw=ImageDraw.Draw(image)
                            for w in overlap:
                                wr=(fitz.Rect(w[:4])*page.rotation_matrix) & clip
                                if not wr.is_empty:
                                    box=(wr.x0*300/72-pix.x-2,wr.y0*300/72-pix.y-2,wr.x1*300/72-pix.x+2,wr.y1*300/72-pix.y+2)
                                    draw.rectangle(box,fill='white')
                            # A page-sized image plus dense native text is often a searchable scan.
                            result=_fix_presentation_forms(recognize(image,ctx,label,rendered=True))
                            if result: _write_ocr(ctx,result); found=True
                            ctx.warn(f'Page {index+1}: scanned region retained as image and OCR text; table/column layout requires review.')
                        else: ctx.warn(f'Page {index+1}: image text was not read because OCR is disabled.')
                if not elements or (not found and not any(b['type']==1 for b in blocks)):
                    dpi=300 if ctx.settings.get('quality') in ('high','quick') else 200
                    _read_region(ctx,page,page.rect*page.derotation_matrix,f'Page {index+1}',dpi=dpi)
                    ctx.warn(f'Page {index+1}: no usable native text; page image and OCR fallback retained.')
                if len(tables) or any(b['type']==1 for b in blocks):
                    pix=page.get_pixmap(dpi=120,alpha=False)
                    link=ctx.asset(pix.tobytes('png'))
                    ctx.write(f'[Page {index+1} layout reference]({link})\n\n')
            except Exception as e:
                ctx.warn(f'Page {index+1}: extraction failed ({type(e).__name__}); other pages continued.')
            finally:
                ctx.complete_unit()
        finally:
            if pool: pool.shutdown(wait=False,cancel_futures=True)
            ctx.write=write
            pages=[''.join(b) for b in buffers]
            removed=_strip_running_lines(pages)
            if removed: ctx.warn('Repeated page header/footer lines removed: '+', '.join('"'+v+'"' for v in removed))
            for value in pages: ctx.write(value if value.endswith('\n') else value+'\n')
        if doc.embfile_count(): ctx.warn('Embedded PDF attachments were not extracted.')
