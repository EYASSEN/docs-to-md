# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Synthetic scan geometry; no private tender document content."""
import sys,io,csv
from pathlib import Path
from types import SimpleNamespace
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from foldertomd import scanlayout as S,ocr as O,pdf as P
from foldertomd.arabicfix import fix_text


def grid_image(merged=False):
    im=Image.new('RGB',(800,700),'white');d=ImageDraw.Draw(im)
    for y in [80,160,350,650]:d.line((40,y,760,y),fill='black',width=2)
    for x in [40,120,240,560,760]:d.line((x,160 if merged and x==240 else 80,x,650),fill='black',width=2)
    return im


def test_grid_preserves_empty_columns_and_wrapped_row_bounds():
    g=S.ruled_grid(grid_image())
    assert g['columns']==4 and len(g['rows'])==3
    assert len(g['rows'][1])==4
    assert g['rows'][1][2][2][3]-g['rows'][1][2][2][1]>170


def test_merged_cell_keeps_continuation_column_slot():
    g=S.ruled_grid(grid_image(True))
    assert g['columns']==4
    assert any(last-first==2 for first,last,_ in g['rows'][0])


def test_merged_arabic_cell_is_anchored_at_the_reading_edge():
    im=Image.new('RGB',(100,100),'white');ImageDraw.Draw(im).text((30,30),'ink',fill='black')
    grid={'columns':4,'rows':[[(0,4,(0,0,100,100))]]}
    stream='conf\ttext\n90\tعنوان\n'
    rows,_=O._grid_transcription(im,grid,lambda *a:SimpleNamespace(returncode=0,stdout=stream.encode()),'ara')
    assert rows==[['عنوان','','','']]


def test_paragraphs_are_not_promoted_to_a_ruled_grid():
    im=Image.new('RGB',(800,700),'white');d=ImageDraw.Draw(im)
    for y in range(40,640,30):d.text((40,y),'Text with numbers 123 456 and separated words',fill='black')
    assert S.ruled_grid(im) is None


def test_stamp_cleaning_preserves_black_intersections_and_colored_body():
    im=Image.new('RGB',(600,600),'white');d=ImageDraw.Draw(im)
    d.ellipse((300,300,480,480),outline='blue',width=4)
    d.line((305,300,305,490),fill='black',width=3)
    d.text((20,20),'Colored body text',fill='red')
    cleaned,changed=S.remove_color_stamps(im)
    assert changed and cleaned.getpixel((390,300))==(255,255,255)
    assert cleaned.getpixel((305,300))==(0,0,0)
    assert cleaned.crop((0,0,200,60)).tobytes()==im.crop((0,0,200,60)).tobytes()


def test_colored_body_without_ring_is_untouched():
    im=Image.new('RGB',(600,600),'white');ImageDraw.Draw(im).text((20,20),'Important heading',fill='red')
    cleaned,changed=S.remove_color_stamps(im)
    assert not changed and cleaned.tobytes()==im.tobytes()


def test_empty_cell_rule_remnants_do_not_become_values():
    im=Image.new('RGB',(100,300),'white');d=ImageDraw.Draw(im)
    d.line((1,0,1,299),fill='black',width=2)
    d.line((98,0,98,299),fill='black',width=2)
    assert S.cell_content(im) is None


def test_cell_trimming_preserves_interior_numeric_strokes():
    im=Image.new('RGB',(100,300),'white');d=ImageDraw.Draw(im)
    d.line((1,0,1,299),fill='black',width=2)
    d.text((40,140),'123',fill='black')
    crop=S.cell_content(im)
    assert crop is not None and crop.width<40 and crop.height<30


def test_broken_scan_rules_are_removed_without_losing_quantity():
    im=Image.new('RGB',(100,300),'white');d=ImageDraw.Draw(im)
    for y in range(0,300,5):d.point((1,y),fill='black')
    d.text((40,270),'6600',fill='black')
    crop=S.cell_content(im)
    assert crop is not None and crop.width<40 and crop.height<30


def test_table_is_retained_when_outside_ocr_fails(monkeypatch):
    monkeypatch.setattr(O,'preflight',lambda settings:None)
    monkeypatch.setattr(O,'best_ruled_grid',lambda im:(im,{'bbox':(0,0,100,100),'columns':3,'rows':[]}))
    monkeypatch.setattr(O,'_grid_transcription',lambda *a:([['A','','1']], [90]))
    monkeypatch.setattr(O,'_tesseract',lambda *a:SimpleNamespace(returncode=1,stdout=b'',stderr=b''))
    value,warnings,_=O.transcribe(O._png(Image.new('RGB',(200,200),'white')),{'language':'eng','quality':'standard'},None,'Synthetic',rendered=True)
    assert isinstance(value,O.ScanText) and value.parts[1][1]==[['A','','1']]
    assert any('outside' in w for w in warnings)


def test_explicit_grid_survives_arabic_normalization_and_pdf_rendering():
    v=O.ScanText('heading\nA\t\t1',[('text','heading'),('table',[['A','','1'],['B','x','2']]),('text','end')])
    v=P._fix_presentation_forms(v);out=[]
    P._write_ocr(SimpleNamespace(write=out.append),v)
    rendered=''.join(out)
    assert '| A |  | 1 |' in rendered and '| B | x | 2 |' in rendered
    assert rendered.index('heading')<rendered.index('| A')<rendered.index('end')


def test_spacing_fix_keeps_arabic_word_and_line_boundaries():
    assert fix_text('والس ُّم َّية')=='والسُّمَّية'
    assert fix_text('كلمة كلمة\nكلمة')=='كلمة كلمة\nكلمة'


def test_empty_grid_recognition_falls_back_instead_of_erasing_table(monkeypatch):
    monkeypatch.setattr(O,'preflight',lambda settings:None)
    monkeypatch.setattr(O,'best_ruled_grid',lambda image:(image,{'bbox':(0,0,100,100),'columns':3,'rows':[]}))
    stream='level\tleft\ttop\twidth\theight\tconf\ttext\tblock_num\tpar_num\tline_num\n5\t10\t10\t20\t10\t90\tRETAINED\t1\t1\t1\n'
    monkeypatch.setattr(O,'_tesseract',lambda *args:SimpleNamespace(returncode=0,stdout=stream.encode(),stderr=b''))
    value,warnings,_=O.transcribe(O._png(Image.new('RGB',(200,200),'white')),{'language':'eng','quality':'standard'},None,'Synthetic',rendered=True)
    assert 'RETAINED' in value and not isinstance(value,O.ScanText)
    assert any('unavailable' in w for w in warnings)
