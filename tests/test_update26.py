# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Real extraction path, synthetic documents only."""
import io,sys
from pathlib import Path
from PIL import Image
import pymupdf as fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from foldertomd import pdf as P,ocr as O
from foldertomd.context import Context

def png():
    b=io.BytesIO();Image.new('RGB',(400,400),'white').save(b,'PNG');return b.getvalue()

def convert(tmp_path,monkeypatch,doc):
    source=tmp_path/'sample.pdf';doc.save(source);work=tmp_path/'work';work.mkdir()
    calls=[]
    def recognized(image,ctx,label,**kwargs):
        calls.append((label,kwargs.get('rendered'),image.size))
        return O.ScanText('A\t\t1',[('table',[['A','','1'],['B','x','2']])])
    monkeypatch.setattr(P,'recognize',recognized)
    ctx=Context({'source':str(source),'work':str(work),'asset_link':'assets','relative':'sample.pdf',
                 'settings':{'language':'ara+eng','ocr':'auto','quality':'standard','decode_fonts':False}})
    P.extract_pdf(ctx);ctx.close()
    return calls,(work/'result.md').read_text()

def test_overlapping_large_scan_images_are_composited_once(tmp_path,monkeypatch):
    doc=fitz.open();p=doc.new_page(width=600,height=800)
    p.insert_image(fitz.Rect(0,0,600,800),stream=png(),keep_proportion=False)
    p.insert_image(fitz.Rect(0,200,600,800),stream=png(),keep_proportion=False)
    calls,result=convert(tmp_path,monkeypatch,doc)
    assert len(calls)==1 and calls[0][1] is True
    assert '| A |  | 1 |' in result and result.count('| A |')==1

def test_rotated_scan_uses_displayed_page_orientation(tmp_path,monkeypatch):
    doc=fitz.open();p=doc.new_page(width=600,height=800)
    p.insert_image(p.rect,stream=png(),keep_proportion=False);p.set_rotation(90)
    calls,_=convert(tmp_path,monkeypatch,doc)
    assert len(calls)==1 and calls[0][1] is True and calls[0][2][0]>calls[0][2][1]

def test_fragmented_small_title_is_not_treated_as_icons(tmp_path,monkeypatch):
    doc=fitz.open();p=doc.new_page(width=600,height=800)
    p.insert_image(fitz.Rect(200,200,400,280),stream=png(),keep_proportion=False)
    p.insert_image(fitz.Rect(200,290,400,370),stream=png(),keep_proportion=False)
    calls,_=convert(tmp_path,monkeypatch,doc)
    assert len(calls)==1 and calls[0][1] is True

def test_vector_only_fallback_preserves_grid_parts(tmp_path,monkeypatch):
    doc=fitz.open();p=doc.new_page();p.draw_rect(fitz.Rect(30,30,400,500))
    calls,result=convert(tmp_path,monkeypatch,doc)
    assert len(calls)==1 and calls[0][1] is True
    assert '| B | x | 2 |' in result

def test_mixed_font_corruption_is_detected_but_accented_name_is_not():
    assert P._garbled('اختبار عربي عام '*3+'ĠŢͳĦͲĪͼ')
    assert not P._garbled('اختبار عربي عام '*3+'Émile Müller')

def test_conversion_report_records_revision_and_settings(tmp_path):
    from foldertomd.engine import reports,CONVERSION_REVISION
    meta=tmp_path/'meta';meta.mkdir()
    reports(tmp_path,meta,{'settings':{'language':'ara','quality':'high'},'files':{},'elapsed_seconds':1})
    result=(meta/'conversion_report.md').read_text()
    assert f'Converter revision: {CONVERSION_REVISION}' in result and '"quality": "high"' in result
