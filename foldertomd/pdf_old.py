# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
import io
import pymupdf as fitz
from PIL import Image, ImageDraw
from .render import table, text
from .ocr import recognize

def extract_pdf(ctx):
    with fitz.open(ctx.source) as doc:
        if doc.needs_pass: raise RuntimeError('Password-protected PDF; no password was attempted.')
        ctx.counts['pages']=len(doc)
        for index,page in enumerate(doc):
            ctx.stage(f'Reading page {index+1} of {len(doc)}')
            ctx.write(f'## Page {index+1}\n\n')
            try:
                words=page.get_text('words',sort=True)
                blocks=page.get_text('dict',sort=True)['blocks']
                tables=[]
                try: tables=list(page.find_tables().tables)
                except Exception: ctx.warn(f'Page {index+1}: table detection failed; text and page visual retained.')
                elements=[]
                for t in tables:
                    elements.append((t.bbox[1],t.bbox[0],'table',t.extract()))
                for b in blocks:
                    rect=fitz.Rect(b['bbox'])
                    if b['type']==0:
                        if any(fitz.Rect(t.bbox).contains(rect) for t in tables): continue
                        lines=[''.join(s['text'] for s in line['spans']) for line in b['lines']]
                        value='\n'.join(lines).strip()
                        if value:
                            size=max((s['size'] for line in b['lines'] for s in line['spans']),default=11)
                            prefix='### ' if size>=16 and len(value)<160 else ''
                            elements.append((rect.y0,rect.x0,'text',prefix+text(value)+'\n\n'))
                    elif b['type']==1:
                        elements.append((rect.y0,rect.x0,'image',b))
                found=False
                for _,__,kind,value in sorted(elements,key=lambda x:(x[0],x[1])):
                    if kind=='text': ctx.write(value); found=True
                    elif kind=='table': ctx.write(table(value)); found=True
                    else:
                        b=value; rect=fitz.Rect(b['bbox']); label=f'Page {index+1} image'
                        # Render in its displayed orientation. Mask native text before OCR,
                        # so a native header never hides a scanned body or gets duplicated.
                        pix=page.get_pixmap(matrix=fitz.Matrix(300/72,300/72),clip=rect,alpha=False)
                        image=Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
                        ctx.image(image,label,ocr=False)
                        if ctx.settings['ocr']!='off':
                            overlap=[w for w in words if not (fitz.Rect(w[:4]) & rect).is_empty]
                            # Preserve original scan resolution when no native text needs masking.
                            # Re-rendering an already-raster image can damage Arabic glyph shapes.
                            if not overlap and page.rect.contains(rect) and b.get('image'):
                                image=Image.open(io.BytesIO(b['image'])).convert('RGB')
                            draw=ImageDraw.Draw(image)
                            for w in overlap:
                                wr=fitz.Rect(w[:4]) & rect
                                if not wr.is_empty:
                                    box=((wr.x0-rect.x0)*300/72-2,(wr.y0-rect.y0)*300/72-2,(wr.x1-rect.x0)*300/72+2,(wr.y1-rect.y0)*300/72+2)
                                    draw.rectangle(box,fill='white')
                            # A page-sized image plus dense native text is often a searchable scan.
                            result=recognize(image,ctx,label)
                            if result: ctx.write(result+'\n\n'); found=True
                            ctx.warn(f'Page {index+1}: scanned region retained as image and OCR text; table/column layout requires review.')
                        else: ctx.warn(f'Page {index+1}: image text was not read because OCR is disabled.')
                if not elements or (not found and not any(b['type']==1 for b in blocks)):
                    pix=page.get_pixmap(dpi=300,alpha=False)
                    with Image.open(io.BytesIO(pix.tobytes('png'))) as image: ctx.image(image,f'Page {index+1}')
                    ctx.warn(f'Page {index+1}: no usable native text; page image and OCR fallback retained.')
                if len(tables) or any(b['type']==1 for b in blocks):
                    pix=page.get_pixmap(dpi=120,alpha=False)
                    link=ctx.asset(pix.tobytes('png'))
                    ctx.write(f'[Page {index+1} layout reference]({link})\n\n')
                if page.annots():
                    annotations=list(page.annots())
                    for annotation in annotations:
                        content=annotation.info.get('content')
                        if content: ctx.write('Annotation: '+text(content)+'\n\n')
            except Exception as e:
                ctx.warn(f'Page {index+1}: extraction failed ({type(e).__name__}); other pages continued.')
        if doc.embfile_count(): ctx.warn('Embedded PDF attachments were not extracted.')
