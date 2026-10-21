# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""OCR table direction, partially consumed lines, and unresolved font glyphs.

Synthetic TSV words and geometry only; no document content is embedded here.
"""
import csv
import hashlib
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pymupdf as fitz
from foldertomd import ocr as O, fontdecode as F


def word(value,x,y,width=35,line=1):
    return {'text':value,'left':str(x),'top':str(y),'width':str(width),
            'height':'10','conf':'90','block_num':'1','par_num':'1',
            'line_num':str(line)}


def test_english_table_keeps_columns_and_word_order():
    rows=[('Power','Factor','0.8','1.0'),('Full','Load','50','100'),
          ('Efficiency','Rate','95','98')]
    words=[]
    for n,(first,second,middle,last) in enumerate(rows):
        words.extend([word(first,10,n*30,width=55,line=n+1),
                      word(second,70,n*30,line=n+1),
                      word(middle,220,n*30,line=n+1),
                      word(last,400,n*30,line=n+1)])
    table,used=O._table_rows(words)
    assert [cells for _,cells in table]==[
        ['Power Factor','0.8','1.0'],['Full Load','50','100'],
        ['Efficiency Rate','95','98']]
    assert used=={id(w) for w in words}


def test_arabic_table_keeps_rightmost_column_first_and_latin_cell_order():
    words=[]
    for n in range(3):
        # TSV keeps English phrase logical order inside an Arabic table.
        words.extend([word('القدرة',400,n*30,line=n+1),
                      word('Power',200,n*30,line=n+1),
                      word('Factor',240,n*30,line=n+1),
                      word(str(n+1),10,n*30,line=n+1)])
    table,_=O._table_rows(words,'ara')
    assert [cells for _,cells in table]==[
        ['القدرة','Power Factor','1'],['القدرة','Power Factor','2'],
        ['القدرة','Power Factor','3']]


def test_arabic_words_inside_a_cell_retain_logical_tsv_order():
    words=[]
    for n in range(3):
        words.extend([word('القدرة',430,n*30,line=n+1),
                      word('الكاملة',385,n*30,line=n+1),
                      word('٢',220,n*30,line=n+1),word('١',10,n*30,line=n+1)])
    table,_=O._table_rows(words)
    assert all(cells==['القدرة الكاملة','٢','١'] for _,cells in table)


def test_numeric_table_uses_the_number_script_when_language_is_mixed():
    for values,expected in [(['10','20','30'],['10','20','30']),
                            (['١٠','٢٠','٣٠'],['٣٠','٢٠','١٠'])]:
        words=[word(v,x,n*30,line=n+1) for n in range(3)
               for v,x in zip(values,[10,220,400])]
        table,_=O._table_rows(words)
        assert all(cells==expected for _,cells in table)


def test_part_of_an_ocr_line_consumed_by_table_is_not_duplicated(monkeypatch):
    fields=['text','left','top','width','height','conf','block_num','par_num','line_num']
    stream=io.StringIO();writer=csv.DictWriter(stream,fields,delimiter='\t')
    writer.writeheader();writer.writerows([word('INSIDE',10,10),word('OUTSIDE',300,10)])
    monkeypatch.setattr(O,'preflight',lambda settings:None)
    monkeypatch.setattr(O,'_tesseract',lambda *args:SimpleNamespace(
        returncode=0,stdout=stream.getvalue().encode(),stderr=b''))
    monkeypatch.setattr(O,'_table_rows',lambda words,language:([(0,['INSIDE'])],{id(words[0])}))
    value,_,_=O.transcribe(b'',{'language':'eng','quality':'quick'},None,'Synthetic',rendered=True)
    assert value.count('INSIDE')==1
    assert value.count('OUTSIDE')==1


def model_and_page(monkeypatch,mapping,glyphs,blank=()):
    monkeypatch.setattr(F,'page_glyphs',lambda page,names:glyphs)
    model=F.FontModel.__new__(F.FontModel)
    model.names={};model.mapping=mapping;model.blank=set(blank);model.markers=set()
    page=SimpleNamespace(rotation=0,rect=fitz.Rect(0,0,200,100))
    return model,page


def glyph(key,x,width=5):
    return (key,True,(x,10,x+width,20),(x,20),10,'')


def test_unknown_letter_is_visible_instead_of_silently_removed(monkeypatch):
    model,page=model_and_page(monkeypatch,{'left':'ب','right':'س'},
                              [glyph('left',10),glyph('unknown',15),glyph('right',20)])
    value,known=model.decode(page,columns=False)
    assert value=='س[?]ب'
    assert known==2/3


def test_genuine_blank_font_glyph_does_not_become_unknown_marker(monkeypatch):
    model,page=model_and_page(monkeypatch,{'left':'ب','right':'س'},
                              [glyph('left',10),glyph('space',15),glyph('right',20)],
                              blank=['space'])
    value,known=model.decode(page,columns=False)
    assert value=='س ب'
    assert known==1


def test_operator_recovered_from_image_shape_has_no_unknown_marker(monkeypatch):
    model,page=model_and_page(monkeypatch,{'left':'١','right':'٢'},
                              [glyph('left',10,10),glyph('sign',20,5),glyph('right',25,10)])
    model._operator=lambda *args:'±'
    value,known=model.decode(page,columns=False)
    assert '±' in value and '[?]' not in value
    assert known==1


def test_updated_converter_cannot_reuse_the_previous_output_signature():
    from foldertomd.engine import signature,DEFAULTS
    new_hash,new_data=signature(DEFAULTS)
    old_data=dict(new_data)
    old_data.pop('converter_revision')
    old_hash=hashlib.sha256(json.dumps(old_data,sort_keys=True).encode()).hexdigest()
    assert new_hash!=old_hash
