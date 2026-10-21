# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pixel geometry for ruled scans. No OCR strings or document-specific corrections."""
import re, statistics
from collections import defaultdict
from PIL import Image, ImageOps, ImageChops, ImageFilter, ImageDraw


def _runs(image, minimum):
    w,h=image.size; data=image.tobytes(); pattern=re.compile(b'\x00{'+str(minimum).encode()+b',}')
    return [(m.start(),y,m.end(),y+1) for y in range(h)
            for m in pattern.finditer(data[y*w:(y+1)*w])]


def _clusters(values, gap=4):
    groups=[]
    for v in sorted(set(values)):
        if groups and v-groups[-1][-1]<=gap:groups[-1].append(v)
        else:groups.append([v])
    return [sum(g)/len(g) for g in groups]


def _edge_covered(vertical, x, top, bottom, tolerant=True):
    """True when an outer vertical rule spans the table, allowing small scan breaks.

    A whole stroke is accepted as before. Otherwise strokes on the same line are joined
    across gaps of at most 8% of the table height, and must still cover 88% of it.
    """
    if any(abs(v[0]-x)<12 and v[1]<=top+12 and v[3]>=bottom-12 for v in vertical):return True
    if not tolerant:return False
    segments=sorted((v[1],v[3]) for v in vertical if abs(v[0]-x)<12)
    if not segments:return False
    height=bottom-top;gap=height*.08;merged=[list(segments[0])]
    for a,b in segments[1:]:
        if a-merged[-1][1]<=gap:merged[-1][1]=max(merged[-1][1],b)
        else:merged.append([a,b])
    covered=sum(max(0,min(b,bottom)-max(a,top)) for a,b in merged)
    return any(a<=top+12 and b>=bottom-12 for a,b in merged) and covered>=height*.88


def _coarse_ruled_grid(image,tolerant=False):
    """Return connected table bounds and cell boxes in original image coordinates.

    Require long intersecting horizontal/vertical strokes, not whitespace guesses.
    Closed grids with merged cells are retained, with empty continuation slots.
    """
    small=ImageOps.grayscale(image); small.thumbnail((1400,1800))
    sx=image.width/small.width; sy=image.height/small.height
    bw=small.point(lambda p:0 if p<160 else 255).filter(ImageFilter.MinFilter(9))
    horizontal=_runs(bw,max(80,int(bw.width*.28)))
    vertical=[(y,x,y+1,z) for x,y,z,_ in _runs(bw.transpose(Image.Transpose.TRANSPOSE),max(70,int(bw.height*.08)))]
    if len(horizontal)<2 or len(vertical)<3:return None
    # Select the strongest family of horizontal strokes with matching endpoints.
    families=[]
    for line in horizontal:
        group=next((g for g in families if abs(g[0][0]-line[0])<45 and abs(g[0][2]-line[2])<20),None)
        if group is None:families.append([line])
        else:group.append(line)
    candidates=[]
    for hs in families:
        ys=_clusters([h[1] for h in hs]);left=sorted(h[0] for h in hs)[len(hs)//2];right=sorted(h[2] for h in hs)[len(hs)//2]
        if len(ys)<3:continue
        vs=[v for v in vertical if left-25<=v[0]<=right+25 and v[1]<=ys[-1]-10 and v[3]>=ys[0]+10 and v[3]-v[1]>.65*(ys[-1]-ys[0])]
        xs=_clusters([v[0] for v in vs])
        if not 3<=len(xs)<=40 or abs(xs[0]-left)>25 or abs(xs[-1]-right)>25:continue
        if not all(_edge_covered(vertical,x,ys[0],ys[-1],tolerant) for x in (xs[0],xs[-1])):continue
        if any(b-a<10 for a,b in zip(xs,xs[1:])):continue
        candidates.append((len(ys)*(right-left),(xs,ys)))
    if not candidates:return None
    xs,ys=max(candidates,key=lambda v:v[0])[1]
    if len(ys)>120:return None
    cells=[]
    for a,b in zip(ys,ys[1:]):
        row=[];start=xs[0];start_col=0
        for col,x in enumerate(xs[1:],1):
            edge=col==len(xs)-1 or any(abs(v[0]-x)<4 and v[1]<=a+6 and v[3]>=b-6 for v in vertical)
            if edge:
                row.append((start_col,col,(round((start+3)*sx),round((a+3)*sy),round((x-3)*sx),round((b-3)*sy))))
                start=x;start_col=col
        cells.append(row)
    return {'bbox':(round(xs[0]*sx),round(ys[0]*sy),round(xs[-1]*sx),round(ys[-1]*sy)),
            'columns':len(xs)-1,'rows':cells,'_axes':(xs,ys)}


def _joined_rule_mask(bw, minimum):
    """Close short breaks beside a long rule, without promoting isolated text."""
    mask=Image.new('L',bw.size,255);draw=ImageDraw.Draw(mask);lines=defaultdict(list)
    for a,y,b,_ in _runs(bw,12):lines[y].append((a,b))
    for y,runs in lines.items():
        groups=[]
        for a,b in runs:
            if groups and a-groups[-1][-1][1]<=8:groups[-1].append((a,b))
            else:groups.append([(a,b)])
        for group in groups:
            if any(b-a>=minimum for a,b in group):
                draw.line((group[0][0],y,group[-1][1]-1,y),fill=0)
    return mask


def _rectangles(horizontal, vertical):
    """Join slots across absent rules; reject ambiguous nonrectangular cells."""
    rows=len(vertical);columns=len(horizontal[0]);parent=list(range(rows*columns))
    def find(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    def join(a,b):parent[find(a)]=find(b)
    for r in range(rows):
        for c in range(columns):
            if c+1<columns and not vertical[r][c+1]:join(r*columns+c,r*columns+c+1)
            if r+1<rows and not horizontal[r+1][c]:join(r*columns+c,(r+1)*columns+c)
    groups=defaultdict(list)
    for r in range(rows):
        for c in range(columns):groups[find(r*columns+c)].append((r,c))
    cells=[]
    for slots in groups.values():
        r0=min(r for r,c in slots);r1=max(r for r,c in slots)+1
        c0=min(c for r,c in slots);c1=max(c for r,c in slots)+1
        if (r1-r0)*(c1-c0)!=len(slots):return None
        cells.append((r0,r1,c0,c1))
    return sorted(cells)


def _refine_grid(image, seed):
    """Recover partial separators and both kinds of merge inside a closed grid."""
    small=ImageOps.grayscale(image);small.thumbnail((1400,1800))
    sx=image.width/small.width;sy=image.height/small.height
    xs,ys=seed['_axes'];xs=list(xs);ys=list(ys);base_xs=xs[:];base_ys=ys[:]
    bw=small.point(lambda p:0 if p<160 else 255).filter(ImageFilter.MinFilter(3))
    minimum=max(45,int(bw.width*.025));horizontal=_runs(bw,minimum)
    vertical=[(y,x,y+1,z) for x,y,z,_ in _runs(bw.transpose(Image.Transpose.TRANSPOSE),max(25,int(bw.height*.025)))]
    def distance(v,axes):return min(abs(v-a) for a in axes)
    def extend(axes,values):return sorted(axes+_clusters([v for v in values if distance(v,axes)>10]))
    # New horizontal and vertical separators can expose one another's endpoints.
    for _ in range(3):
        width=statistics.median(b-a for a,b in zip(xs,xs[1:]))
        hs=[v for v in horizontal if ys[0]-5<=v[1]<=ys[-1]+5 and xs[0]-6<=v[0]<v[2]<=xs[-1]+6
            and ((distance(v[0],xs)<5 and distance(v[2],xs)<5)
                 or (v[2]-v[0]>4*width and min(distance(v[0],xs),distance(v[2],xs))<10))]
        ys=extend(ys,[v[1] for v in hs])
        vs=[v for v in vertical if xs[0]-5<=v[0]<=xs[-1]+5 and ys[0]-6<=v[1]<v[3]<=ys[-1]+6
            and distance(v[1],ys)<10 and distance(v[3],ys)<10]
        xs=extend(xs,[v[0] for v in vs])
    if len(xs)>41 or len(ys)>121 or any(b-a<10 for axes in (xs,ys) for a,b in zip(axes,axes[1:])):
        return None
    hr=_joined_rule_mask(bw,minimum).tobytes()
    vm=Image.new('L',bw.size,255);draw=ImageDraw.Draw(vm)
    for x,a,_,b in vertical:draw.line((x,a,x,b-1),fill=0)
    vr=vm.tobytes();w,h=bw.size
    thick=small.point(lambda p:0 if p<160 else 255).filter(ImageFilter.MinFilter(9));tr=thick.tobytes()
    tv=[(y,x,y+1,z) for x,y,z,_ in _runs(thick.transpose(Image.Transpose.TRANSPOSE),max(70,int(h*.08)))]
    # A thickened thumbnail can connect stacked letters into a false full axis.
    # Permit gap repair only for axes supported across most of the table by
    # thinner, genuinely long strokes. Short real dividers stay local.
    repair_axes=[]
    for axis in base_xs:
        covered={y for x,a,_,b in vertical if abs(x-axis)<7
                 for y in range(max(round(ys[0]),a),min(round(ys[-1]),b))}
        if len(covered)>.55*(ys[-1]-ys[0]):repair_axes.append(axis)
    def hline(y,a,b):
        x0=round(a)+5;x1=round(b)-5
        if x1<=x0:return True
        strength=sum(any(hr[yy*w+x]==0 for yy in range(max(0,round(y)-4),min(h,round(y)+5))) for x in range(x0,x1))/(x1-x0)
        # Broader gap repair is reserved for the original long horizontal rules.
        repair=sum(any(tr[yy*w+x]==0 for yy in range(max(0,round(y)-3),min(h,round(y)+4))) for x in range(x0,x1))/(x1-x0) if distance(y,base_ys)<4 else 0
        return strength>.4 or repair>.65
    def vline(x,a,b):
        y0=round(a)+5;y1=round(b)-5
        if y1<=y0:return True
        strength=sum(any(vr[y*w+xx]==0 for xx in range(max(0,round(x)-7),min(w,round(x)+8))) for y in range(y0,y1))/(y1-y0)
        repair=bool(repair_axes) and distance(x,repair_axes)<10 and any(abs(v[0]-x)<7 and v[1]<=a+6 and v[3]>=b-6 for v in tv)
        return strength>.4 or repair
    horizontal_edges=[[hline(y,a,b) for a,b in zip(xs,xs[1:])] for y in ys]
    vertical_edges=[[vline(x,a,b) for x in xs] for a,b in zip(ys,ys[1:])]
    regions=_rectangles(horizontal_edges,vertical_edges)
    if regions is None:return None
    cells=[[] for _ in range(len(ys)-1)];rowspans={}
    def local_edge(strokes,axis,a,b,vertical_axis,leading):
        positions=[]
        for line in strokes:
            position,start,end=(line[0],line[1],line[3]) if vertical_axis else (line[1],line[0],line[2])
            if abs(position-axis)<=7 and min(end,b)-max(start,a)>=(b-a)*.8:
                positions.append(position)
        return (max(positions) if leading else min(positions)) if positions else axis
    for r0,r1,c0,c1 in regions:
        # Scan perspective can move a rule several pixels from its global axis.
        # Follow the local stroke at each edge so it stays outside the OCR crop.
        left=local_edge(vertical,xs[c0],ys[r0],ys[r1],True,True)
        right=local_edge(vertical,xs[c1],ys[r0],ys[r1],True,False)
        top=local_edge(horizontal,ys[r0],xs[c0],xs[c1],False,True)
        bottom=local_edge(horizontal,ys[r1],xs[c0],xs[c1],False,False)
        box=(round((left+1)*sx),round((top+1)*sy),round((right-1)*sx),round((bottom-1)*sy))
        cells[r0].append((c0,c1,box))
        if r1-r0>1:rowspans[r0,c0]=r1-r0
    return {'bbox':seed['bbox'],'columns':len(xs)-1,'rows':cells,'rowspans':rowspans,'_axes':(xs,ys)}


def ruled_grid(image):
    seed=_coarse_ruled_grid(image)
    if not seed:return None
    refined=_refine_grid(image,seed)
    if refined is not None:return refined
    seed['layout_review']=True
    return seed


def best_ruled_grid(image,tolerant=False):
    """Select fine skew by straight rule evidence, then refine the cell geometry.

    Tolerance for small breaks in the outer border is off by default: it detected more
    grids, but the cell-by-cell reading lost text the page reading had kept (Cleanup8 review).
    """
    grid=_coarse_ruled_grid(image,tolerant)
    def score(g,im):
        if not g:return 0
        x0,y0,x1,y1=g['bbox']
        if x1-x0<im.width*.5 or y1-y0<im.height*.12:return 0
        return (x1-x0)*(y1-y0)/(im.width*im.height)
    small=ImageOps.grayscale(image);small.thumbnail((1400,1800))
    def strength(angle):
        tilted=small.rotate(angle,expand=True,fillcolor=255,resample=Image.Resampling.BICUBIC)
        bw=tilted.point(lambda p:0 if p<160 else 255).filter(ImageFilter.MinFilter(3))
        hsum=sum(b-a for a,_,b,_ in _runs(bw,max(80,int(bw.width*.6))))
        vsum=sum(b-a for a,_,b,_ in _runs(bw.transpose(Image.Transpose.TRANSPOSE),max(70,int(bw.height*.3))))
        return (hsum*vsum)**.5
    base_strength=strength(0);best=(score(grid,image),image,grid,0)
    for quality,angle in sorted(((strength(a),a) for a in (-.5,.5,-1,1)),reverse=True):
        if quality<=base_strength*1.12:continue
        candidate=image.rotate(angle,expand=True,fillcolor='white')
        found=_coarse_ruled_grid(candidate,tolerant=tolerant and not best[0]);area=score(found,candidate)
        if area and area>=best[0]*.9:
            best=(area,candidate,found,angle);break
    if not best[0]:return image,None
    selected=best[1];seed=best[2];refined=_refine_grid(selected,seed)
    if refined is None:seed['layout_review']=True;refined=seed
    if best[3]:refined['fine_skew']=best[3]
    return selected,refined


def cell_content(image,with_offset=False):
    """Trim white space and remove long rule remnants at crop edges only."""
    gray=ImageOps.grayscale(image)
    w,h=gray.size
    if not w or not h:return None
    ink=gray.point(lambda p:255 if p<160 else 0)
    data=ink.tobytes(); clean=bytearray(data)
    mx=min(12,max(2,w//20));my=min(12,max(2,h//20))
    for x in list(range(mx))+list(range(max(mx,w-mx),w)):
        occupied=[y for y in range(h) if data[y*w+x]>0]
        if occupied and (len(occupied)>h*.65 or ((x<2 or x>=w-2) and len(occupied)>h*.1)) and occupied[-1]-occupied[0]>h*.8:
            for y in range(h):
                for xx in range(max(0,x-1),min(w,x+2)):clean[y*w+xx]=0
    # A photocopied rule can be interrupted or faint along most of a tall
    # cell. Retain isolated character strokes; remove only long edge runs
    # that together establish a rule spanning most of the cell height.
    if h>=120:
        for x in set(list(range(mx))+list(range(max(mx,w-mx),w))):
            if not 0<=x<w: continue
            column=bytes(data[y*w+x] for y in range(h))
            runs=[m.span() for m in re.finditer(rb'\xff+',column) if m.end()-m.start()>=max(40,h*.025)]
            if not runs or runs[-1][1]-runs[0][0]<h*.75 or sum(b-a for a,b in runs)<h*.1: continue
            for a,b in runs:
                for y in range(a,b):
                    for xx in range(max(0,x-1),min(w,x+2)):clean[y*w+xx]=0
    for y in list(range(my))+list(range(max(my,h-my),h)):
        occupied=[x for x in range(w) if data[y*w+x]>0]
        if len(occupied)>w*.75 and occupied[-1]-occupied[0]>w*.8:
            for yy in range(max(0,y-1),min(h,y+2)):clean[yy*w:(yy+1)*w]=bytes(w)
    mask=Image.frombytes('L',(w,h),bytes(clean))
    bounds=mask.getbbox()
    if bounds is None:return None
    # Keep gray anti-aliasing on retained ink; erased rules become white.
    erased=ImageChops.subtract(ink,mask)
    result=Image.composite(Image.new('RGB',(w,h),'white'),image.convert('RGB'),erased)
    return (result.crop(bounds),bounds[:2]) if with_offset else result.crop(bounds)


def remove_color_stamps(image):
    """Neutralize chromatic stamp ink: large hollow round components of any colour, and
    large blue rubber-stamp blocks (rectangular or rotated, with text inside).

    Original pixels are always retained by the caller. Only chromatic pixels inside a detected
    stamp region change; black ink under a stamp is untouched. Coloured body text, thin coloured
    bands (table shading, single coloured lines) and small blue marks (handwriting) are untouched.
    """
    rgb=image.convert('RGB');small=rgb.copy();small.thumbnail((700,1000))
    w,h=small.size;raw=small.tobytes();pixels=list(zip(raw[0::3],raw[1::3],raw[2::3]))
    mask=bytearray(int(max(p)-min(p)>35 and min(p)<220) for p in pixels)
    # Join separated ring strokes at thumbnail resolution, then label components.
    joined=Image.frombytes('L',(w,h),bytes(v*255 for v in mask)).filter(ImageFilter.MaxFilter(7))
    active=bytearray(joined.tobytes()); boxes=[]; blue=[]; blocks=[]
    for seed in range(w*h):
        if not active[seed]:continue
        active[seed]=0;stack=[seed];component=[]
        while stack:
            n=stack.pop();component.append(n);x=n%w;y=n//w
            for m in (n-1 if x else -1,n+1 if x<w-1 else -1,n-w if y else -1,n+w if y<h-1 else -1):
                if m>=0 and active[m]:active[m]=0;stack.append(m)
        if len(component)<100:continue
        xs=[n%w for n in component];ys=[n//w for n in component]
        x0,x1=min(xs),max(xs);y0,y1=min(ys),max(ys);ww=x1-x0+1;hh=y1-y0+1
        originals=[n for n in component if mask[n]]
        if not originals:continue
        box=(x0,y0,x1+1,y1+1)
        r=sum(pixels[n][0] for n in originals)/len(originals);b=sum(pixels[n][2] for n in originals)/len(originals)
        g=sum(pixels[n][1] for n in originals)/len(originals)
        if b-r>35 and b-g>25:blue.append((box,len(originals)/(ww*hh)))
        if not (.65<ww/hh<1.5 and ww>w*.06 and hh>h*.04):continue
        center=sum(x0+ww*.25<n%w<x0+ww*.75 and y0+hh*.25<n//w<y0+hh*.75 for n in originals)
        if center/len(originals)>.30:continue
        boxes.append(box)
    # A blue stamp block is large in both directions (not a heading line or table band), not a
    # filled picture, and not most of the page. Blue fragments beside it (a split border or a
    # detached line of the stamp) belong to it.
    seeds=[bx for bx,ink in blue if bx[2]-bx[0]>w*.10 and bx[3]-bx[1]>h*.08 and bx[2]-bx[0]<w*.5 and bx[3]-bx[1]<h*.4 and ink<.5]
    mx,my=w*.02,h*.02
    for sx0,sy0,sx1,sy1 in seeds:
        region=[sx0-mx,sy0-my,sx1+mx,sy1+my]
        for bx,_ in blue:
            if bx[0]<region[2] and bx[2]>region[0] and bx[1]<region[3] and bx[3]>region[1] and (bx[2]-bx[0])*(bx[3]-bx[1])<=(sx1-sx0)*(sy1-sy0):
                region=[min(region[0],bx[0]),min(region[1],bx[1]),max(region[2],bx[2]),max(region[3],bx[3])]
        blocks.append(tuple(region))
    if not boxes and not blocks:return image,False
    r,g,b=rgb.split();hi=ImageChops.lighter(ImageChops.lighter(r,g),b);lo=ImageChops.darker(ImageChops.darker(r,g),b)
    chroma=ImageChops.subtract(hi,lo).point(lambda p:255 if p>35 else 0)
    def area(regions):
        bounds=Image.new('L',rgb.size);draw=ImageDraw.Draw(bounds)
        for x0,y0,x1,y1 in regions:draw.rectangle((x0*rgb.width/w,y0*rgb.height/h,x1*rgb.width/w,y1*rgb.height/h),fill=255)
        return bounds
    selected=ImageChops.multiply(chroma,area(boxes))
    if blocks:
        # Inside a stamp block, dark pixels are black text printed under the stamp (blue mixed
        # with black stays dark): only the bright stamp ink is removed.
        bright=hi.point(lambda p:255 if p>140 else 0)
        selected=ImageChops.lighter(selected,ImageChops.multiply(ImageChops.multiply(chroma,bright),area(blocks)))
    return Image.composite(Image.new('RGB',rgb.size,'white'),rgb,selected),True
