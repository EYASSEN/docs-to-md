"""Noisy-scan cleanup for OCR only (Cleanup3). The original image is never changed or replaced in the output.
Pure Pillow, so it needs no extra libraries in the portable build."""
import re
from PIL import Image, ImageChops, ImageDraw, ImageFilter

_RUN=re.compile(rb'\xff+')

def _otsu(hist):
    total=sum(hist); sum_all=sum(i*c for i,c in enumerate(hist)); best=(0,0); w0=0; s0=0
    for t in range(256):
        w0+=hist[t]
        if not w0: continue
        w1=total-w0
        if not w1: break
        s0+=t*hist[t]; m0=s0/w0; m1=(sum_all-s0)/w1
        var=w0*w1*(m0-m1)**2
        if var>best[0]: best=(var,t)
    return best[1]

def _components(bw,w,h):
    """Connected components (8-neighbour) of the 255-pixels of an 'L' image, from row runs. Returns (runs, parent, stats)."""
    data=bw.tobytes(); runs=[]; parent=[]; prev=[]
    def find(i):
        while parent[i]!=i: parent[i]=parent[parent[i]]; i=parent[i]
        return i
    for y in range(h):
        row=data[y*w:(y+1)*w]; cur=[]
        for m in _RUN.finditer(row):
            a,b=m.span(); idx=len(runs); runs.append((y,a,b)); parent.append(idx); cur.append((a,b,idx))
        if prev and cur:
            j=0
            for a,b,idx in cur:
                while j<len(prev) and prev[j][1]<a: j+=1          # previous run ends before this one starts (touching diagonally counts)
                k=j
                while k<len(prev) and prev[k][0]<=b:
                    ra,rb=find(prev[k][2]),find(idx)
                    if ra!=rb: parent[ra]=rb
                    k+=1
        prev=cur
    stats={}
    for idx,(y,a,b) in enumerate(runs):
        r=find(idx); s=stats.get(r)
        if s is None: stats[r]=[b-a,a,y,b,y+1]               # area, x0, y0, x1, y1
        else:
            s[0]+=b-a; s[1]=min(s[1],a); s[2]=min(s[2],y); s[3]=max(s[3],b); s[4]=max(s[4],y+1)
    return runs,find,stats

def clean_scan(image):
    """Cleaned black-on-white copy: flat background, speckle and binder-hole strips removed."""
    g=image.convert('L'); w,h=g.size; scale=max(1.0,min(w,h)/1650.0)
    small=g.resize((max(1,w//4),max(1,h//4)),Image.Resampling.BOX).filter(ImageFilter.GaussianBlur(25*scale/4))
    bg=small.resize((w,h),Image.Resampling.BILINEAR)
    diff=ImageChops.subtract(bg,g.filter(ImageFilter.GaussianBlur(1.2*scale)))
    thr=max(20,_otsu(diff.histogram()))
    bw=diff.point(lambda p:255 if p>thr else 0)
    runs,find,stats=_components(bw,w,h)
    min_area=int(18*scale*scale); edge=int(0.12*w); drop=set()
    for r,(area,x0,y0,x1,y1) in stats.items():
        if area<min_area or ((x0>w-edge or x1<edge) and (y1-y0)>0.04*h): drop.add(r)
    out=Image.new('L',(w,h),255); draw=ImageDraw.Draw(out)
    for idx,(y,a,b) in enumerate(runs):
        if find(idx) not in drop: draw.line([(a,y),(b-1,y)],fill=0)
    return out.convert('RGB')

def _score(rows):
    words=[r for r in rows if r.get('text','').strip()]
    conf=[]
    for r in words:
        try:
            c=float(r['conf'])
            if c>=0: conf.append(c)
        except (ValueError,KeyError): pass
    return (sum(conf)/len(conf) if conf else 0.0), len(words)

def needs_cleanup(rows):
    """A reading that is empty, tiny or low-confidence is worth one more attempt on a cleaned copy."""
    conf,n=_score(rows)
    return n<15 or conf<65

def prefer_cleaned(base_rows,clean_rows):
    """True when the cleaned reading is clearly better: more readable words at no lower confidence, or much higher confidence."""
    if cleanup_numbers_changed(base_rows,clean_rows): return False
    bc,bn=_score(base_rows); cc,cn=_score(clean_rows)
    if cn==0: return False
    if bn<5: return cn>=5 and cc>=48
    return (cn>=bn*1.25 and cc>=bc-2) or (cc>=bc+8 and cn>=bn*0.8)

def cleanup_numbers_changed(base_rows,clean_rows):
    """Confidence alone cannot authorize changing numeric evidence."""
    from .ocrselect import number_tokens
    return number_tokens(' '.join(r.get('text','') for r in base_rows)) != number_tokens(' '.join(r.get('text','') for r in clean_rows))

# ---- Unreadable and poor-quality scans (Cleanup11) ------------------------------------------------
# Some scans are printed as fine dots (halftone) or are so speckled that Tesseract's layout pass finds
# almost nothing while its sparse pass turns the speckle into hundreds of fragments (Geotechnical
# Report). Such a page is first re-read from a smoothed copy; if that is still not readable, a clear
# notice is written instead of noise. Pages with readable text never reach this path.

def _letters(word):
    return sum(c.isalpha() for c in word)

def _conf(r):
    try: return float(r.get('conf',-1))
    except (TypeError,ValueError): return -1.0

def good_words(rows):
    """Words Tesseract is sure of: confidence 80+ and at least three letters."""
    return sum(1 for r in rows if _conf(r)>=80 and _letters(r.get('text','').strip())>=3)

def looks_unreadable(layout_rows,sparse_rows):
    """The layout pass found almost nothing readable, and the sparse pass found many fragments of low mean
    confidence of which few are confident words: the page is read as noise. Thresholds from the bundled
    Windows Tesseract on the Geotechnical Report (sparse: 27-192 fragments, mean 36-52, confident share
    0-10 %) against the readable sample pages (Cleanup11b)."""
    sparse=[r for r in sparse_rows if r.get('text','').strip()]
    conf=[_conf(r) for r in sparse if _conf(r)>=0]
    mean=sum(conf)/len(conf) if conf else 0.0
    return (good_words(layout_rows)<5 and len(sparse)>=20 and mean<55
            and good_words(sparse)<0.12*len(sparse))

def descreen(image,dpi=300):
    """Smoothed black-on-white copy: blurring merges halftone dots into solid strokes."""
    radius=3.0*dpi/300.0
    return image.convert('L').filter(ImageFilter.GaussianBlur(radius)).point(lambda p:0 if p<140 else 255).convert('RGB')

def accept_smoothed(smoothed_rows,sparse_rows):
    good=good_words(smoothed_rows)
    return good>=8 and good>=good_words(sparse_rows)+5

def smoothed_lines(rows):
    """Lines of a smoothed reading, without its own noise: low-confidence fragments are dropped and a line
    is kept only when it holds at least one fairly confident word."""
    lines={}
    for r in rows:
        word=r.get('text','').strip()
        if not word or _conf(r)<25: continue
        lines.setdefault((r.get('block_num'),r.get('par_num'),r.get('line_num')),[]).append(r)
    out=[]
    for words in lines.values():
        if not any(_conf(r)>=60 and _letters(r['text'].strip())>=2 for r in words): continue
        top=min(int(r.get('top',0)) for r in words); left=min(int(r.get('left',0)) for r in words)
        out.append((top,left,' '.join(r['text'].strip() for r in words)))
    return [v for _,__,v in sorted(out)]
