# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Update16: Arabic table cells, lam-alef ligature, logos not OCR'd, tiled scans OCR'd once."""
import sys, io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import pymupdf as fitz
from PIL import Image
from foldertomd import pdf as P

FIX=Path(__file__).resolve().parent/'fixtures'/'arabic_table.pdf'

def test_arabic_table_cells_read_in_order():
    page=fitz.open(FIX)[0]
    blocks=page.get_text('rawdict',sort=True)['blocks']
    rows=[[P._balance_brackets(c) if c else c for c in row] for t in page.find_tables().tables for row in P._table_rows(t,blocks,[])]
    assert rows[0]==['قيمة الغرامة','نوع الغرامة','م']
    assert rows[1][1]=='عدم الالتزام بالخطة الزمنية\nالمعتمدة'          # lam-alef ligature, no stray space
    assert rows[1][0].startswith('غرامة بنسبة (1%) من قيمة')
    assert 'RGA-TM-000)' in rows[2][1]

def test_zero_width_alef_follows_its_glyph():
    # as stored by Word/LibreOffice: alef, zero-width alef on the lam-alef glyph edge, lam, lam, teh (visual, RTL)
    chars=[('ا',341.5,344.5),('ا',341.5,341.5),('ل',335.2,341.5),('ل',331.8,335.2),('ت',328.6,331.9)]
    span={'size':12,'chars':[{'c':c,'bbox':(x0,100,x1,112)} for c,x0,x1 in chars]}
    assert P._visual_line([span])=='الالت'

def _run(tmp_path, monkeypatch, doc):
    from foldertomd.context import Context
    from foldertomd import ocr
    src=tmp_path/'m.pdf'; doc.save(src); (tmp_path/'w').mkdir()
    calls=[]
    monkeypatch.setattr(P,'recognize',lambda image,ctx,label,**kwargs: calls.append(label) or 'نص')
    monkeypatch.setattr(ocr,'preflight',lambda *a,**k: None)
    ctx=Context({'source':str(src),'work':str(tmp_path/'w'),'asset_link':'assets','relative':'m.pdf',
                 'settings':{'language':'ara+eng','ocr':'standard','timeout':900,'quality':'standard','decode_fonts':True}})
    P.extract_pdf(ctx); ctx.out.close()
    return [c.split()[1] for c in calls if c.startswith('Page')]

def _png(w=60,h=60,shade=128):
    b=io.BytesIO(); Image.new('RGB',(w,h),(shade,shade,shade)).save(b,'PNG'); return b.getvalue()

def test_tiny_icon_not_ocrd_tiles_and_scans_are(tmp_path, monkeypatch):
    doc=fitz.open()
    page=doc.new_page(width=595,height=842); page.insert_image(fitz.Rect(40,20,90,70),stream=_png(shade=10))   # tiny icon
    page=doc.new_page(width=595,height=842)                                                                   # tiled scan
    for i in range(10):
        for j in range(10): page.insert_image(fitz.Rect(i*59.5,j*84.2,(i+1)*59.5,(j+1)*84.2),stream=_png(shade=20+i*10+j))
    page=doc.new_page(width=595,height=842); page.insert_image(page.rect,stream=_png(shade=250))            # full-page scan
    pages=_run(tmp_path, monkeypatch, doc)
    assert '1' not in pages and pages.count('2')==1 and pages.count('3')==1

def test_repeated_logo_not_ocrd_but_small_text_image_is(tmp_path, monkeypatch):
    doc=fitz.open(); xref=0
    for n in range(3):
        page=doc.new_page(width=595,height=842)
        r=fitz.Rect(40,20,240,170)                                                         # 6% logo on every page
        xref=page.insert_image(r,stream=_png(200,150,shade=200)) if not xref else (page.insert_image(r,xref=xref) or xref)
    page=doc.new_page(width=400,height=800)                                               # like test_core rotated-image:
    page.insert_image(fitz.Rect(50,500,150,780),stream=_png(100,280,shade=60))                     # one image, 8.75% of the page
    pages=_run(tmp_path, monkeypatch, doc)
    assert not any(p in pages for p in ('1','2','3'))
    assert pages.count('4')==1

def test_tiles_that_repeat_across_pages_are_still_one_scan(tmp_path, monkeypatch):
    doc=fitz.open()
    for n in range(3):                       # the same blank tiles on every page, one different tile per page
        page=doc.new_page(width=595,height=842)
        for i in range(10):
            for j in range(10):
                shade=30+n if (i,j)==(5,5) else 255
                page.insert_image(fitz.Rect(i*59.5,j*84.2,(i+1)*59.5,(j+1)*84.2),stream=_png(shade=shade))
    pages=_run(tmp_path, monkeypatch, doc)
    assert pages==['1','2','3']
