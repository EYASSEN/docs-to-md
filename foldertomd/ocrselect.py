# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Conservative selection between local OCR readings of the same pixels."""
import csv, io, re, statistics, unicodedata


def words(result):
    if result.returncode: return []
    return [r for r in csv.DictReader(io.StringIO(result.stdout.decode('utf-8','replace')),
            delimiter='\t',quoting=csv.QUOTE_NONE) if r.get('text','').strip()]


def confidence(word):
    try: return max(0.0,float(word['conf']))
    except (KeyError,ValueError,TypeError): return 0.0


def mean_confidence(group):
    return sum(confidence(w) for w in group)/len(group) if group else 0.0


def number_tokens(value):
    """Compare digit scripts without losing signs, decimal places or leading zeroes."""
    normalized=[]
    for c in value:
        if unicodedata.category(c)=='Cf': continue
        if c in '٫٬٪': normalized.append({'٫':'.','٬':',','٪':'%'}[c]); continue
        if c=='−': normalized.append('-'); continue
        try: normalized.append(str(unicodedata.digit(c)))
        except (ValueError,TypeError): normalized.append(c)
    return tuple(re.findall(r'[+-]?\d+(?:[.,/]\d+)*(?:\s*%)?', ''.join(normalized)))


def numeric(value):
    value=value.strip()
    return bool(number_tokens(value)) and not any(c.isalpha() for c in value) and not re.search(r'[^\d\s+\-−.,٫٬/%٪\u200e\u200f]',value)


def box(word):
    x,y,w,h=(int(word[k]) for k in ('left','top','width','height'))
    return x,y,x+w,y+h


def overlap(a,b,pad=0):
    return a[0]<b[2]+pad and a[2]>b[0]-pad and a[1]<b[3]+pad and a[3]>b[1]-pad


def orientation_angle(result):
    """Tesseract documents orientation confidence 15 as reasonably confident."""
    if result.returncode: return 0,None
    value=result.stdout.decode('utf-8','replace')
    rotation=re.search(r'Rotate:\s*(\d+)',value)
    score=re.search(r'Orientation confidence:\s*([\d.]+)',value)
    angle=int(rotation[1]) if rotation else 0
    conf=float(score[1]) if score else None
    if angle not in (90,180,270) or conf is None or conf<15: return 0,conf
    return angle,conf


def verified_orientation(image,result,run,png,language):
    angle,conf=orientation_angle(result)
    if angle or result.returncode: return angle,conf,False
    match=re.search(r'Rotate:\s*(\d+)',result.stdout.decode('utf-8','replace'))
    proposed=int(match[1]) if match else 0
    if proposed not in (90,180,270) or conf is None: return 0,conf,False
    preview=image.copy();preview.thumbnail((1600,1600))
    primary=words(run(png(preview),['-l',language,'--psm','3','tsv']))
    alternate=words(run(png(preview.rotate(-proposed,expand=True,fillcolor='white')),['-l',language,'--psm','3','tsv']))
    good_old=sum(confidence(w)>=80 for w in primary)
    good_new=sum(confidence(w)>=80 for w in alternate)
    if (len(alternate)>=5 and mean_confidence(alternate)>=70
            and mean_confidence(alternate)>=mean_confidence(primary)+15
            and good_new>=max(5,2*good_old)):
        return proposed,conf,True
    return 0,conf,False


def prefer_arabic(primary,alternate):
    old=' '.join(r['text'].strip() for r in primary)
    new=' '.join(r['text'].strip() for r in alternate)
    if number_tokens(old)!=number_tokens(new): return False,'numbers'
    if sum('\u0621'<=c<='\u064a' for c in new)<5: return False,'text'
    if mean_confidence(alternate)<50 or mean_confidence(alternate)<mean_confidence(primary)+5:
        return False,'confidence'
    return True,None


def collapse_line(group,alternate):
    bounds=[box(w) for w in group]
    first=group[0]
    x0=min(b[0] for b in bounds); y0=min(b[1] for b in bounds)
    x1=max(b[2] for b in bounds); y1=max(b[3] for b in bounds)
    first.update(text=' '.join(w['text'].strip() for w in alternate),conf=str(mean_confidence(alternate)),
                 left=str(x0),top=str(y0),width=str(x1-x0),height=str(y1-y0))
    for w in group[1:]: w['text']=''


def merge_sparse(rows,extra,warnings,label):
    """Keep primary text, but let a strong isolated numeric reading repair a weak word."""
    primary=[r for r in rows if r.get('text','').strip()]
    groups={}
    for r in extra:
        groups.setdefault((r.get('block_num'),r.get('par_num'),r.get('line_num')),[]).append(r)
    for candidate in extra:
        if not numeric(candidate['text']) or confidence(candidate)<90: continue
        hits=[r for r in primary if r.get('text','').strip() and overlap(box(candidate),box(r))]
        if len(hits)!=1: continue
        old=hits[0]; a=box(old); b=box(candidate)
        if not (0.45*(a[3]-a[1])<=b[3]-b[1]<=1.8*(a[3]-a[1])): continue
        if confidence(old)>85 or confidence(candidate)<confidence(old)+10: continue
        if number_tokens(old['text'])!=number_tokens(candidate['text']):
            warnings.append(label+': a low-confidence numeric reading was replaced by a stronger sparse reading; review the original image.')
        old.update({k:candidate[k] for k in ('text','conf','left','top','width','height')})
    for group in groups.values():
        if mean_confidence(group)<35: continue
        if any(overlap(box(r),box(p),4) for r in group for p in primary if p.get('text','').strip()): continue
        for r in group: r['block_num']='extra-'+r.get('block_num','0')
        rows.extend(group); primary.extend(group)


def reread_numeric_columns(rows,image,run,png,warnings,label,language='ara+eng'):
    """Read narrow cells only after repeated, aligned numeric rows establish a table.

    No digit whitelist is used: an ordinary English/Arabic pass must itself return
    a number. At least five row anchors and two matching rows in the other column
    are required. Strong existing readings are retained on disagreement.
    """
    candidates=[r for r in rows if r.get('text','').strip() and numeric(r['text']) and confidence(r)>=85]
    if len(candidates)<7: return
    clusters=[]
    for r in sorted(candidates,key=lambda w:(int(w['left']),int(w['top']))):
        a=box(r); h=a[3]-a[1]
        if not h: continue
        center=(a[0]+a[2])/2
        cluster=next((g for g in clusters if abs(center-statistics.median((box(w)[0]+box(w)[2])/2 for w in g))<h),None)
        if cluster is None: clusters.append([r])
        else: cluster.append(r)
    repaired=set()
    for cluster in clusters:
        anchors=sorted(cluster,key=lambda w:int(w['top']))
        if len(anchors)<5: continue
        h=statistics.median(int(w['height']) for w in anchors)
        if not h or max(int(w['width']) for w in anchors)>6*h: continue
        centers=[int(w['top'])+int(w['height'])/2 for w in anchors]
        gaps=[b-a for a,b in zip(centers,centers[1:])]
        gap=statistics.median(gaps)
        if gap<1.4*h or any(abs(g-gap)>0.35*gap for g in gaps): continue
        ax=statistics.median((box(w)[0]+box(w)[2])/2 for w in anchors)
        for other in clusters:
            if other is cluster or len(other)<2: continue
            ox=statistics.median((box(w)[0]+box(w)[2])/2 for w in other)
            if abs(ox-ax)<6*h or max(int(w['width']) for w in other)>4*h: continue
            aligned=[w for w in other if any(abs(int(w['top'])+int(w['height'])/2-c)<0.7*h for c in centers)]
            if len(aligned)<2: continue
            xs=[box(w) for w in aligned]
            x0=max(0,int(min(b[0] for b in xs)-h)); x1=min(image.width,int(max(b[2] for b in xs)+h))
            reads=[]
            lang='ara' if sum('\u0660'<=c<='\u0669' for w in aligned for c in w['text']) else 'eng'
            if '_best' in language: lang+='_best'
            for anchor,cy in zip(anchors,centers):
                bounds=(x0,max(0,int(cy-0.75*h)),x1,min(image.height,int(cy+0.75*h)))
                existing=[r for r in rows if r.get('text','').strip() and overlap(box(r),bounds)]
                if len(existing)==1 and confidence(existing[0])>=85 and numeric(existing[0]['text']):
                    reads.append((anchor,bounds,existing,existing[0]['text']));continue
                from PIL import ImageOps
                crop=ImageOps.expand(image.crop(bounds),border=12,fill='white')
                alt=words(run(png(crop),['-l',lang,'--psm','7','tsv']))
                value=' '.join(w['text'].strip() for w in alt)
                if not numeric(value) or mean_confidence(alt)<75:
                    binary=ImageOps.grayscale(crop).point(lambda p:255 if p>180 else 0)
                    retry=words(run(png(binary),['-l',lang,'--psm','7','tsv']))
                    retry_value=' '.join(w['text'].strip() for w in retry)
                    if numeric(retry_value) and mean_confidence(retry)>=75:
                        alt=retry;value=retry_value
                reads.append((anchor,bounds,alt,value))
            if sum(bool(alt) and numeric(value) and mean_confidence(alt)>=75 for _,_,alt,value in reads)<0.8*len(reads): continue
            for anchor,bounds,alt,value in reads:
                if not alt or not numeric(value) or mean_confidence(alt)<75: continue
                hits=[r for r in rows if r.get('text','').strip() and overlap(box(r),bounds)]
                if len(hits)>1: continue
                old=hits[0] if hits else None
                if old is not None:
                    if number_tokens(old['text'])==number_tokens(value) and numeric(old['text']): continue
                    if confidence(old)>85 or mean_confidence(alt)<confidence(old)+5: continue
                identity=(bounds[0],bounds[1])
                if identity in repaired: continue
                repaired.add(identity)
                if old is not None: old['text']=''
                b=[box(w) for w in alt]; x= min(v[0] for v in b)+bounds[0]-12; y=min(v[1] for v in b)+bounds[1]-12
                rows.append({**anchor,'text':value,'conf':str(mean_confidence(alt)),
                    'left':str(x),'top':str(y),'width':str(max(v[2] for v in b)-min(v[0] for v in b)),
                    'height':str(max(v[3] for v in b)-min(v[1] for v in b)),
                    'block_num':'cell-'+str(len(rows))})
                warnings.append(label+': a weak numeric table cell was reread from its own pixels; review the original image.')
