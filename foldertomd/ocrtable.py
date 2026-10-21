# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pixel separators and local, single-script rereads of established scan tables."""
import statistics
from PIL import ImageOps
from .ocrselect import box, words, numeric, number_tokens, confidence, mean_confidence


def colon_pixels(image,bounds):
    """Two compact, vertically separated ink components; never infer from OCR text."""
    x0,y0,x1,y1=bounds
    if not (0<x1-x0<=0.7*(y1-y0) and 5<=y1-y0<=100): return False
    crop=ImageOps.grayscale(image.crop((max(0,x0-2),max(0,y0-2),min(image.width,x1+2),min(image.height,y1+2))))
    w,h=crop.size;active=bytearray(1 if v<180 else 0 for v in crop.tobytes());parts=[]
    for seed in range(w*h):
        if not active[seed]: continue
        active[seed]=0;stack=[seed];points=[]
        while stack:
            n=stack.pop();points.append(n);x=n%w;y=n//w
            for yy in range(max(0,y-1),min(h,y+2)):
                for xx in range(max(0,x-1),min(w,x+2)):
                    k=yy*w+xx
                    if active[k]: active[k]=0;stack.append(k)
        parts.append(points)
    area=sum(map(len,parts));parts=[p for p in parts if len(p)>=max(2,area*.08)]
    if len(parts)!=2: return False
    shapes=sorted([(min(n%w for n in p),min(n//w for n in p),max(n%w for n in p)+1,max(n//w for n in p)+1) for p in parts],key=lambda b:b[1])
    a,b=shapes;total=b[3]-a[1];gap=b[1]-a[3]
    return (gap>=max(2,total*.2) and abs((a[0]+a[2])-(b[0]+b[2]))<=4
            and max(a[3]-a[1],b[3]-b[1])<=total*.4
            and all(.4<=(r[2]-r[0])/(r[3]-r[1])<=2 for r in shapes))


def remove_pixel_separators(rows,image,warnings,label):
    active=[r for r in rows if r.get('text','').strip()];possible=[]
    for r in active:
        b=box(r);h=b[3]-b[1]
        if not colon_pixels(image,b): continue
        cy=(b[1]+b[3])/2
        neighbors=[w for w in active if w is not r and abs((box(w)[1]+box(w)[3])/2-cy)<h]
        left=[w for w in neighbors if box(w)[2]<b[0]-1.8*h]
        right=[w for w in neighbors if box(w)[0]>b[2]+1.8*h]
        if left and right and numeric(max(left,key=lambda w:box(w)[2])['text']) and numeric(min(right,key=lambda w:box(w)[0])['text']):
            possible.append(r)
    removed=0
    for r in possible:
        b=box(r);h=b[3]-b[1]
        aligned=[w for w in possible if abs((box(w)[0]+box(w)[2])-(b[0]+b[2]))<=h
                 and (w is r or abs(box(w)[1]-b[1])>=h)]
        if len(aligned)>=2: r['text']='';removed+=1
    if removed:
        warnings.append(label+': repeated table separators identified from their pixels; OCR guesses were excluded from data columns.')


def spatial_rows(items):
    """Match OCR words to rows, preserving the original dicts and logical word order."""
    rows=[]
    for r in sorted(items,key=lambda w:(box(w)[1]+box(w)[3])/2):
        b=box(r);cy=(b[1]+b[3])/2;h=b[3]-b[1]
        if rows and abs(rows[-1][0]-cy)<.6*h: rows[-1][1].append(r)
        else: rows.append([cy,[r]])
    result=[]
    for cy,items in rows:
        ordered=sorted(items,key=lambda w:box(w)[0]);h=statistics.median(box(w)[3]-box(w)[1] for w in items)
        cells=[[ordered[0]]]
        for a,b in zip(ordered,ordered[1:]):
            if box(b)[0]-box(a)[2]>1.8*h: cells.append([b])
            else: cells[-1].append(b)
        result.append((cy,cells))
    return result


def _value(group): return ' '.join(w['text'].strip() for w in group)


def _strong(group):
    numbered=[w for w in group if number_tokens(w['text'])]
    return bool(numbered) and mean_confidence(group)>=80 and all(confidence(w)>=85 for w in numbered)


def _confirmed(first,second,regional,sparse=()):
    key=number_tokens(_value(first))
    if not key or key!=number_tokens(_value(second)): return False
    if _strong(first) and _strong(second): return True
    # Cropping can reduce one token's confidence despite an identical reading.
    # Require matching contextual readings, two strong votes, and both
    # local crops to remain credible; never lower the general replacement limit.
    if key!=number_tokens(_value(regional)): return False
    if sum(_strong(group) for group in (first,second,regional))<2:
        # Reuse the sparse page reading only when it belongs to this cell and
        # independently agrees with both local crops and the regional reading.
        # Both context readings must be strong; confidence limits are unchanged.
        if key!=number_tokens(_value(sparse)) or not _strong(regional) or not _strong(sparse): return False
    return all(mean_confidence(group)>=80 and all(confidence(w)>=50 for w in group if number_tokens(w['text']))
               for group in (first,second))


def _format_preserved(old,new):
    a=number_tokens(old);b=number_tokens(new)
    if len(a)!=len(b): return False
    for before,after in zip(a,b):
        if before.endswith('%')!=after.endswith('%'): return False
        if ('.' in before)!=('.' in after) or (',' in before)!=(',' in after): return False
        if before[:1] in '+-' and before[:1]!=after[:1]: return False
        if len(before)>1 and before[0]=='0' and before[1].isdigit() and before!=after: return False
    return True


def _in_cell(items,region,cy,height):
    return sorted((w for w in items if region[0]-.7*height<=(box(w)[0]+box(w)[2])/2<=region[2]+.7*height
                  and abs((box(w)[1]+box(w)[3])/2-cy)<.8*height),key=lambda w:box(w)[0])


def refine_latin_tables(rows,image,run,png,warnings,label,language,table_rows,sparse_words=()):
    """Revisit established English/numeric tables, including three-row tables.

    Strong numbers need agreeing isolated pixel readings and two strong votes;
    a contextual table reading can corroborate a crop with reduced confidence.
    Full-page confidence is not treated as proof of a cell's numerical value.
    Arabic tables and ordinary prose are not sent to an English-only reader.
    """
    if not {'eng','eng_best'}&set(language.split('+')): return
    active=[r for r in rows if r.get('text','').strip()]
    _,used=table_rows(active,language)
    selected=[w for w in active if id(w) in used]
    if not selected: return
    parsed=spatial_rows(selected);blocks=[]
    for cy,cells in parsed:
        h=statistics.median(box(w)[3]-box(w)[1] for c in cells for w in c)
        if not blocks or cy-blocks[-1][-1][0]>4*h: blocks.append([])
        blocks[-1].append((cy,cells))
    lang='eng_best' if '_best' in language else 'eng'
    for block in blocks:
        if len(block)<3: continue
        count=statistics.mode(len(cells) for _,cells in block)
        if not 2<=count<=8 or sum(len(cells)==count for _,cells in block)<.8*len(block): continue
        text=' '.join(w['text'] for _,cells in block for cell in cells for w in cell)
        if any('\u0621'<=c<='\u06ff' for c in text): continue
        if not any(c.isdigit() for c in text): continue
        all_words=[w for _,cells in block for cell in cells for w in cell]
        h=statistics.median(box(w)[3]-box(w)[1] for w in all_words)
        anchors=[statistics.median(min(box(w)[0] for w in cells[c]) for _,cells in block if len(cells)==count) for c in range(count)]
        if any(sum(abs(min(box(w)[0] for w in cells[c])-anchors[c])<=3*h for _,cells in block if len(cells)==count)<.8*len(block) for c in range(count)): continue
        bounds=[box(w) for w in all_words];margin=max(12,int(h*.6))
        band=(max(0,min(b[0] for b in bounds)-margin),max(0,min(b[1] for b in bounds)-margin),
              min(image.width,max(b[2] for b in bounds)+margin),min(image.height,max(b[3] for b in bounds)+margin))
        regional=words(run(png(ImageOps.expand(image.crop(band),border=12,fill='white')),['-l',lang,'--psm','6','tsv']))
        for w in regional:
            w['left']=str(int(w['left'])+band[0]-12);w['top']=str(int(w['top'])+band[1]-12)
        for cy,cells in block:
            for cell in cells:
                old=_value(cell);b=[box(w) for w in cell]
                region=(min(v[0] for v in b),min(v[1] for v in b),max(v[2] for v in b),max(v[3] for v in b))
                alt=_in_cell(regional,region,cy,h)
                if not number_tokens(old) and not number_tokens(_value(alt)): continue
                disagreement=number_tokens(old)!=number_tokens(_value(alt))
                short=numeric(old) and len(old.strip())<=3
                if not (disagreement or short or mean_confidence(cell)<85): continue
                pad=max(12,int(h*.7))
                crop_bounds=(max(0,region[0]-pad),max(0,region[1]-pad),min(image.width,region[2]+pad),min(image.height,region[3]+pad))
                crop=ImageOps.expand(image.crop(crop_bounds),border=12,fill='white')
                first=words(run(png(crop),['-l',lang,'--psm','7','tsv']))
                candidate=first
                changed=number_tokens(old)!=number_tokens(_value(first))
                if not changed and _strong(first): continue
                if mean_confidence(cell)>=85 or not _strong(first) or number_tokens(_value(first))!=number_tokens(_value(alt)):
                    binary=ImageOps.grayscale(crop).point(lambda p:255 if p>180 else 0)
                    second=words(run(png(binary),['-l',lang,'--psm','7','tsv']))
                    if not _confirmed(first,second,alt,_in_cell(sparse_words,region,cy,h)):
                        if changed: warnings.append(label+': numeric table readings disagreed or lacked enough confidence; original cell retained for review.')
                        continue
                    candidate=second if _strong(second) else first
                elif not _strong(alt): continue
                if number_tokens(old)==number_tokens(_value(candidate)): continue
                if not _format_preserved(old,_value(candidate)):
                    warnings.append(label+': numeric table format conflicted; original cell retained for review.')
                    continue
                # A numeric cell cannot grow prose; a description keeps its words.
                if numeric(old) and not numeric(_value(candidate)): continue
                candidate_boxes=[box(w) for w in candidate]
                x0=min(v[0] for v in candidate_boxes)+crop_bounds[0]-12;y0=min(v[1] for v in candidate_boxes)+crop_bounds[1]-12
                x1=max(v[2] for v in candidate_boxes)+crop_bounds[0]-12;y1=max(v[3] for v in candidate_boxes)+crop_bounds[1]-12
                cell[0].update(text=_value(candidate),conf=str(mean_confidence(candidate)),left=str(x0),top=str(y0),width=str(x1-x0),height=str(y1-y0))
                for w in cell[1:]: w['text']=''
                warnings.append(label+': numeric table cell corrected by agreeing local readings; review the original image.')
