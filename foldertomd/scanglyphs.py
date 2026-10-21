# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read isolated scan glyphs with pixel evidence; never infer a number sequence."""
from functools import lru_cache
import re,unicodedata
from PIL import Image,ImageOps
from .fontdecode import _norm,_similarity,shape_references
from .ocrselect import words,confidence,mean_confidence,numeric,number_tokens

DIGITS='٠١٢٣٤٥٦٧٨٩'


@lru_cache(maxsize=1)
def references():
    return shape_references()


def components(image):
    w,h=image.size
    data=bytearray(image.convert('L').point(lambda p:1 if p<160 else 0).tobytes());out=[]
    for seed in range(w*h):
        if not data[seed]:continue
        data[seed]=0;stack=[seed];pts=[]
        while stack:
            n=stack.pop();pts.append(n);x,y=n%w,n//w
            for yy in range(max(0,y-1),min(h,y+2)):
                for xx in range(max(0,x-1),min(w,x+2)):
                    m=yy*w+xx
                    if data[m]:data[m]=0;stack.append(m)
        if len(pts)<3:continue
        xs=[n%w for n in pts];ys=[n//w for n in pts]
        out.append((min(xs),min(ys),max(xs)+1,max(ys)+1,len(pts)))
    return sorted(out)


def digit_parts(image):
    parts=components(image)
    if not parts:return []
    tallest=max(p[3]-p[1] for p in parts)
    # Keep a small zero beside a tall one; discard detached speckles and rule dots.
    parts=[p for p in parts if p[3]-p[1]>=max(4,tallest*.25)]
    joined=[]
    for p in parts:
        if joined and p[0]-joined[-1][2]<max(1,tallest*.15):
            q=joined.pop();joined.append((min(q[0],p[0]),min(q[1],p[1]),max(q[2],p[2]),max(q[3],p[3]),q[4]+p[4]))
        else:joined.append(p)
    return joined if 1<=len(joined)<=3 else []


def ranked_shape(image,refs,allowed):
    norm=_norm(image)
    if norm is None:return []
    best={}
    for ch,ref in refs:
        if ch in allowed:best[ch]=max(best.get(ch,-100),_similarity(norm,ref))
    return sorted(best.items(),key=lambda item:-item[1])


def read_digits(image,refs,margin=.08):
    parts=digit_parts(image)
    if not parts:return None
    value=[];scores=[]
    for x0,y0,x1,y1,_ in parts:
        best=ranked_shape(image.crop((x0,y0,x1,y1)),refs,DIGITS)
        if len(best)<2 or best[0][1]<.74 or best[0][1]-best[1][1]<margin:return None
        value.append(best[0][0]);scores.append(best[0][1])
    return ''.join(value),min(scores)


def plain(value):
    return ''.join(c for c in value if unicodedata.category(c)!='Cf').strip()


def style_references(crops,refs):
    """One frozen pass over strong multi-digit shapes; no recursive relabelling."""
    extra=[];counts={}
    for crop in crops:
        candidate=read_digits(crop,refs,.08)
        if candidate is None or len(candidate[0])<2:continue
        for ch,part in zip(candidate[0],digit_parts(crop)):
            if ch in '٠١' or counts.get(ch,0)>=2:continue
            x0,y0,x1,y1,_=part;patch=crop.crop((x0,y0,x1,y1))
            ranks=ranked_shape(patch,refs,DIGITS)
            if len(ranks)<2 or ranks[0][1]<.8 or ranks[0][1]-ranks[1][1]<.12:continue
            norm=_norm(patch)
            if norm is not None:extra.append((ch,norm));counts[ch]=counts.get(ch,0)+1
    return extra


def compact_symbol(image):
    """Trim sparse scan speckles, retaining at least 92% of the dark pixels."""
    parts=components(image)
    if not parts:return image
    minimum=max(8,max(p[4] for p in parts)*.12)
    # A real dot-sized zero or detached numeral stroke must not be erased.
    kept=[p for p in parts if p[4]>=minimum or max(p[2]-p[0],p[3]-p[1])>4]
    if not kept or sum(p[4] for p in kept)<.92*sum(p[4] for p in parts):return image
    bounds=(min(p[0] for p in kept),min(p[1] for p in kept),max(p[2] for p in kept),max(p[3] for p in kept))
    return image.crop(bounds)


def refine_digits(image,grid,rows,readings,run,png,language,cell_content):
    if not language.startswith('ara'):return 0
    columns={}
    for r,first,bounds,ws in readings:
        if any(a==first and b==first+1 for a,b,_ in grid['rows'][r]):
            columns.setdefault(first,[]).append((r,bounds,ws))
    changed=0
    for column,entries in columns.items():
        anchors=[r for r,bb,ws in entries if numeric(rows[r][column])
                 and re.fullmatch(r'[\d\u200e\u200f\s]{1,3}',rows[r][column]) and mean_confidence(ws)>=55]
        if len(anchors)<3 or len(entries)<6:continue
        if sum(plain(rows[r][column]) in ('%','٪') for r,bb,ws in entries)>=2:continue
        eligible=[(r,bb,ws) for r,bb,ws in entries if r>=max(0,min(anchors)-1)]
        if sum(sum(c.isalpha() for c in rows[r][column])>4 for r,bb,ws in eligible)>.2*len(eligible):continue
        crops=[]
        for r,bb,ws in eligible:
            crop=cell_content(image.crop(bb))
            if crop is not None:crops.append((r,bb,ws,crop))
        if len(crops)<6:continue
        width=max(c.width for r,bb,ws,c in crops)+40
        if width>220:continue
        heights=[max(bb[3]-bb[1],40)+24 for r,bb,ws,c in crops]
        if sum(heights)>12000:continue
        strip=Image.new('RGB',(width,sum(heights)),'white');bands=[];top=0
        for (r,bb,ws,crop),height in zip(crops,heights):
            strip.paste(crop,((width-crop.width)//2,top+(height-crop.height)//2))
            bands.append((r,top,top+height));top+=height
        found=words(run(png(strip),['-l',language.split('+')[0],'--psm','6','tsv']))
        prototypes=[];by_row={r:crop for r,bb,ws,crop in crops}
        for word in found:
            value=plain(word['text'])
            if len(value)!=1 or value not in DIGITS or confidence(word)<90:continue
            try:cy=int(word['top'])+int(word['height'])/2
            except (KeyError,ValueError):continue
            hits=[r for r,y0,y1 in bands if y0<=cy<y1]
            if len(hits)!=1:continue
            crop=by_row[hits[0]];parts=digit_parts(crop)
            if len(parts)!=1:continue
            x0,y0,x1,y1,_=parts[0];patch=crop.crop((x0,y0,x1,y1))
            ranks=ranked_shape(patch,references(),DIGITS);score=dict(ranks).get(value,-100)
            # OCR supplies the label; built-in shapes must also support it.
            if not ranks or score<.60 or ranks[0][1]-score>.10:continue
            norm=_norm(patch)
            if norm is not None:prototypes.append((value,norm))
        if not prototypes:continue
        refs=references()+prototypes
        style_refs=refs+style_references([crop for r,bb,ws,crop in crops],refs)
        for r,bb,ws,crop in crops:
            old=plain(rows[r][column])
            if sum(c.isalpha() for c in old)>4:continue
            if numeric(old) and not old.isdecimal():continue  # preserve signs, decimals and fractions
            margin=.12 if numeric(old) and mean_confidence(ws)>=85 else .08
            candidate=read_digits(crop,refs,margin)
            if candidate is None:candidate=read_digits(crop,style_refs,margin)
            if candidate is None or number_tokens(old)==number_tokens(candidate[0]):continue
            # A valid leading-zero code must not lose its zeroes during segmentation.
            if old.isdecimal() and old[0] in '0٠' and len(candidate[0])!=len(old):continue
            rows[r][column]=candidate[0];changed+=1
    return changed


def refine_percent(image,rows,readings,run,png,cell_content):
    established=[]
    for r,column,bb,ws in readings:
        if plain(rows[r][column]) not in ('%','٪') or mean_confidence(ws)<85:continue
        crop=cell_content(image.crop(bb))
        if crop is not None and .5<crop.width/max(1,crop.height)<1.8:
            norm=_norm(crop)
            if norm is not None:established.append(('%',norm))
    if len(established)<4:return 0
    refs=references()+established;eligible=[]
    for r,column,bb,ws in readings:
        old=plain(rows[r][column])
        if old in ('%','٪') or len(old)>8 or sum(c.isalpha() for c in old)>4:continue
        if numeric(old) and (not old.isdecimal() or (len(old)>1 and old[0] in '0٠')):continue
        strong_number=numeric(old) and mean_confidence(ws)>=90
        crop=cell_content(image.crop(bb))
        if crop is None:continue
        crop=compact_symbol(crop)
        if not .5<crop.width/max(1,crop.height)<1.8 or max(crop.size)>90:continue
        ranks=ranked_shape(crop,refs,set(DIGITS+'%'+'.،/'))
        if len(ranks)<2 or ranks[0][0]!='%' or ranks[0][1]<.78 or ranks[0][1]-ranks[1][1]<.08:continue
        # A confident numeric reading requires stronger pixel evidence and two
        # confident English readings; confidence alone does not establish truth.
        if strong_number and (ranks[0][1]<.90 or ranks[0][1]-ranks[1][1]<.18):continue
        eligible.append((r,column,crop,ranks[0][1],85 if strong_number else 65))
    changed=0
    for r,column,crop,score,minimum in sorted(eligible,key=lambda value:-value[3])[:32]:
        variants=[crop]
        binary=ImageOps.grayscale(crop).point(lambda p:0 if p<128 else 255)
        ranks=ranked_shape(binary,refs,set(DIGITS+'%'+'.،/'))
        if len(ranks)>=2 and ranks[0][0]=='%' and ranks[0][1]>=.85 and ranks[0][1]-ranks[1][1]>=.12:
            variants.append(binary)
        for variant in variants:
            data=png(ImageOps.expand(variant,border=12,fill='white'))
            first=words(run(data,['-l','eng','--psm','6','tsv']))
            if plain(' '.join(w['text'] for w in first))!='%' or mean_confidence(first)<minimum:continue
            second=words(run(data,['-l','eng','--psm','10','tsv']))
            if plain(' '.join(w['text'] for w in second))!='%' or mean_confidence(second)<minimum:continue
            rows[r][column]='%';changed+=1;break
    return changed
