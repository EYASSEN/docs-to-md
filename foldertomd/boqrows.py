# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Split one tall ruled body row into the item rows it contains.

Bills of quantities are often drawn as a header row and a single tall body row;
the items are separated only by white space. The words of that row keep their
page positions, so they can be given back to the item whose number they sit
beside. Words are never moved between columns and nothing is rewritten.
"""
import re

_ITEM=re.compile(r'^[\w٠-٩۰-۹.\-()]{1,4}$')


def _num(word,key):
    try:return int(float(word.get(key,0)))
    except (TypeError,ValueError):return 0


def _lines(words,tops):
    """Group word indexes into text lines using vertical centres."""
    order=sorted(range(len(words)),key=lambda i:tops[i]+_num(words[i],'height')/2)
    groups=[]
    for i in order:
        cy=tops[i]+_num(words[i],'height')/2;h=max(1,_num(words[i],'height'))
        if groups and abs(cy-groups[-1][1])<=h*.6:
            groups[-1][0].append(i);groups[-1][1]=(groups[-1][1]+cy)/2
        else:groups.append([[i],cy])
    return [g[0] for g in groups]


def _anchors(words,tops):
    """Item-number lines of one narrow column, or None when it is not one."""
    keep=[i for i,w in enumerate(words) if any(c.isalnum() for c in w.get('text',''))]
    words=[words[i] for i in keep];tops=[tops[i] for i in keep]
    if len(words)<2:return None
    for w in words:
        if not _ITEM.match(w.get('text','').strip()):return None
    groups=_lines(words,tops)
    if len(groups)<2:return None
    # a numbering column has one token per line
    if any(len(g)>1 for g in groups):return None
    order=sorted(range(len(words)),key=lambda i:tops[i])
    return [min(tops[i] for i in g) for g in groups],[words[i] for i in order]


def _consecutive(words):
    digits=str.maketrans('\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669','0123456789')
    try:values=[int(w.get('text','').strip().translate(digits)) for w in words]
    except ValueError:return False
    return all(b==a+1 for a,b in zip(values,values[1:]))


def _ink_anchors(image,box):
    """Top y of each short ink line in a narrow column (digits that OCR could not read)."""
    from PIL import ImageOps
    x0,y0,x1,y1=box
    w=x1-x0;h=y1-y0
    if h<60 or w<12:return None
    lo=max(1,int(w*.14));hi=w-lo
    gray=ImageOps.grayscale(image.crop((x0+lo,y0,x0+hi,y1)))
    w=hi-lo
    data=gray.point(lambda p:255 if p<160 else 0).tobytes()
    bands=[];start=None;spans={}
    for y in range(h+1):
        xs=[x for x in range(w) if y<h and data[y*w+x]]
        if xs and start is None:start=y;left=right=None
        if xs:
            left=min(xs) if left is None else min(left,min(xs));right=max(xs) if right is None else max(right,max(xs))
        if not xs and start is not None:
            bands.append((start,y,right-left+1));start=None
    merged=[]
    for a,b,width in bands:
        if merged and a-merged[-1][1]<=max(3,(b-a)//4):merged[-1]=(merged[-1][0],b,max(merged[-1][2],width))
        else:merged.append((a,b,width))
    # a rule or long text line is not a number: keep narrow bands that do not touch the cell edge
    merged=[m for m in merged if m[2]<=w*.8 and m[0]>3 and m[1]<h-3]
    if len(merged)<2:return None
    heights=sorted(b-a for a,b,_ in merged);typical=heights[len(heights)//2]
    if typical<8 or typical>70:return None
    merged=[m for m in merged if typical*.5<=m[1]-m[0]<=typical*1.8]
    if len(merged)<2:return None
    return [y0+a for a,b,_ in merged],typical


def _paragraph_gaps(spans_y,line):
    """(mid, size, next line top) of the paragraph gaps of one column: at least 1.5 line heights, so the
    wide line spacing of English descriptions (about one line height) is not taken for a paragraph break."""
    lines=[]
    for a,b in sorted(spans_y):
        if lines and a<=lines[-1][1]+line*.25:lines[-1][1]=max(lines[-1][1],b)
        else:lines.append([a,b])
    limit=line*1.5
    return [((lines[i][1]+lines[i+1][0])/2,lines[i+1][0]-lines[i][1],lines[i+1][0])
            for i in range(len(lines)-1) if lines[i+1][0]-lines[i][1]>=limit]


def _ended_boundary(index,anchors,line,ends,gaps,low,fallback,colons=()):
    """Cleanup12: the previous item's unit/quantity marks where that item ends. An item number sits
    beside the first line of its own line block, but a heading ("Section 16440 ...") or an
    introduction ("بالعدد توريد وتركيب ... التالية :-") above that block belongs to the same item.
    So the boundary is the first paragraph gap after the previous item's unit/quantity line, when
    that line lies below the previous number (the item's last line, not its first).

    Returns (first, last) gap: when they differ, the text between them is an introduction shared by
    the items below it ("بالعدد توريد وتركيب ... للأقطار التالية :-"); it becomes a row of its own
    without a number, as printed, instead of being given to one item (Cleanup14)."""
    if not index or not ends:return None
    a=anchors[index];previous=anchors[index-1]
    ended=[b for t,b in ends if previous+line*.6<(t+b)/2<a-line*.6]
    if not ended:return None
    end=max(ended)
    after=[mid for mid,size,below in gaps if end<mid<fallback and mid>low and below<=a+line*.6]
    if not after:return None
    first,last=min(after),max(after)
    # An Arabic introduction ends with ":-" ("للأقطار التالية :-"); the item line starts below it even
    # when the gap under it is narrower than a paragraph gap.
    cut=[b+line*.4 for b in colons if first<b and b+line*.4<a-line*.3]
    if cut:last=max(last,max(cut))
    return first,last


def _boundaries(anchors,line,spans_y,ends=(),text_spans=None,colons=()):
    """Boundary y for each anchor: the paragraph gap just above it, else anchor-0.6*line.
    The first anchor always uses the fallback: text above it is the section heading, not an item line.

    The item number often sits beside the second line of its description, so the
    heading line of the item would otherwise stay with the previous item.
    ends are the (top, bottom) of unit/quantity words and text_spans the description lines;
    with them a heading or introduction above an item moves to that item (Cleanup12).
    """
    paragraphs=_paragraph_gaps(text_spans,line) if text_spans else []
    lines=[]
    for a,b in sorted(spans_y):
        if lines and a<=lines[-1][1]+line*.25:lines[-1][1]=max(lines[-1][1],b)
        else:lines.append([a,b])
    gaps=[((lines[i][1]+lines[i+1][0])/2,lines[i+1][0]-lines[i][1],lines[i+1][0]) for i in range(len(lines)-1)]
    out=[];previous=None
    for index,a in enumerate(anchors):
        fallback=a-line*.6
        low=previous+line if previous is not None else a-line*8
        pick=None
        for mid,size,below in gaps:
            # a real paragraph gap above the number, whose next line starts near the number
            if index and size>=line*.8 and low<mid<fallback and below<=a+line*.6:pick=(mid,size) if pick is None or a-mid<a-pick[0] else pick
        bound=pick[0] if pick else fallback
        ended=_ended_boundary(index,anchors,line,ends,paragraphs,low,fallback,colons)
        if ended is not None and (previous is None or ended[0]>previous):
            out.extend(ended if ended[1]>ended[0] else ended[:1]);previous=ended[1];continue
        if previous is not None and bound<=previous:bound=fallback
        out.append(bound);previous=bound
    return out


def split_item_rows(rows,spans,rowspans,readings,offsets,columns,image=None,rtl=False):
    """Return (rows,spans,rowspans,split_count). Unchanged when no row qualifies.

    readings are [row,column,box,words]; offsets[(row,column)] is the page y of
    the top of the words' coordinate system for that cell. The numbering column
    is the outer column on the reading side (right for Arabic, left otherwise).
    """
    by_row={}
    for r,first,box,words in readings:by_row.setdefault(r,{})[first]=(box,words)
    plan={}
    for r,cells in by_row.items():
        if len(cells)<3:continue
        ends=[c for c in ((columns-1,0) if rtl else (0,columns-1)) if c in cells and (r,c) in offsets]
        best=None
        for position,c in enumerate(ends):
            words=[w for w in cells[c][1] if w.get('text','').strip()]
            found=_anchors(words,[offsets[r,c]+_num(w,'top') for w in words])
            if found and _consecutive(found[1]):
                line=max(1,sorted(_num(w,'height') for w in found[1])[len(found[1])//2])
                best=(c,found[0],line);break
            if position==0 and image is not None:
                # numbers OCR could not read (for example Arabic-Indic digits): use the ink lines
                if any(len(w.get('text','').strip())>4 and any(ch.isalnum() for ch in w['text']) for w in words):continue
                ink=_ink_anchors(image,cells[c][0])
                if ink:best=(c,ink[0],ink[1]);break
        if not best:continue
        c,anchors,line=best
        box=cells[c][0]
        if box[3]-box[1]<line*4:continue
        # a spanned cell crossing this row would be corrupted by inserting rows
        if any((rr==r and h>1) or rr<r<rr+h for (rr,_),h in rowspans.items()):continue
        # only rows whose text is still the plain reading (nothing rewritten later)
        plain=True
        for col,(b,words) in cells.items():
            if rows[r][col]!=' '.join(w.get('text','').strip() for w in words if w.get('text','').strip()):plain=False
        if not plain:continue
        spans_y=[]
        for col,(b,words) in cells.items():
            if col==c:continue
            for w in words:
                if w.get('text','').strip():
                    top=offsets[r,col]+_num(w,'top');spans_y.append((top,top+_num(w,'height')))
        # description beside the numbers, unit next to it (Cleanup12). Only confidently read unit words
        # mark an item's end: stamps over the quantity and price columns read as noise.
        step=-1 if c==columns-1 else 1
        description=c+step;unit=c+2*step
        def boxes(cols,sure=False):
            out=[]
            for col in cols:
                if col not in cells or (r,col) not in offsets:continue
                for w in cells[col][1]:
                    if sure:
                        try:
                            if float(w.get('conf',0))<60:continue
                        except (TypeError,ValueError):continue
                    if w.get('text','').strip() and any(ch.isalnum() for ch in w['text']):
                        top=offsets[r,col]+_num(w,'top');out.append((top,top+_num(w,'height')))
            return out
        colons=[]
        if description in cells and (r,description) in offsets:
            for w in cells[description][1]:
                t=w.get('text','').strip()
                if t.endswith((':-','-:',':')) and not any(ch.isalnum() for ch in t[-2:]):
                    colons.append(offsets[r,description]+_num(w,'top')+_num(w,'height'))
        plan[r]=(c,_boundaries(anchors,line,spans_y,boxes((unit,),sure=True),boxes((description,)),colons))
    if not plan:return rows,spans,rowspans,0
    out_rows=[];out_spans=[];shift={};count=0
    for r,row in enumerate(rows):
        shift[r]=len(out_rows)
        if r not in plan:
            out_rows.append(row);out_spans.append(spans[r]);continue
        c,bounds=plan[r];n=len(bounds)
        bands=[[ '' for _ in row] for _ in range(n+1)]
        for col,(b,words) in by_row[r].items():
            parts=[[] for _ in range(n+1)]
            for w in words:
                if not w.get('text','').strip():continue
                cy=offsets[r,col]+_num(w,'top')+_num(w,'height')/2
                k=sum(cy>=x for x in bounds)
                parts[k].append(w.get('text','').strip())
            for k,p in enumerate(parts):bands[k][col]=' '.join(p)
        for k,band in enumerate(bands):
            if not any(band):continue
            out_rows.append(band);out_spans.append(list(spans[r]))
        count+=1
    new_rowspans={}
    for (rr,col),h in rowspans.items():new_rowspans[shift[rr],col]=h
    return type(rows)(out_rows) if type(rows) is list else out_rows,out_spans,new_rowspans,count
