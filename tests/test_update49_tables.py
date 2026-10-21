"""Retain scan prose and every table row when OCR heights/coordinates differ."""
import csv
import io
from pathlib import Path
from types import SimpleNamespace

from foldertomd import ocr as O


def word(value,x,y,width=35,height=22,line=1):
    return {'text':value,'left':str(x),'top':str(y),'width':str(width),
            'height':str(height),'conf':'95','block_num':'1','par_num':'1',
            'line_num':str(line)}


def result(rows):
    stream=io.StringIO()
    writer=csv.DictWriter(stream,list(rows[0]),delimiter='\t')
    writer.writeheader();writer.writerows(rows)
    return SimpleNamespace(returncode=0,stdout=stream.getvalue().encode(),stderr=b'')


def test_small_bullets_do_not_split_numeric_prose_into_fake_table():
    rows=[]
    for n in range(3):
        y=n*40
        rows.extend([word('-',10,y+12,width=7,height=3,line=n+1),
                     word('Activation',27,y,width=121,line=n+1),
                     word('range',159,y+6,width=71,line=n+1),
                     word('(switching',241,y,width=120,height=28,line=n+1),
                     word('distance)',371,y,width=112,height=28,line=n+1),
                     word('10',497,y+1,width=27,height=21,line=n+1),
                     word('mm',535,y+6,width=44,height=16,line=n+1)])
    assert O._table_rows(rows,'eng')==([],set())


def test_same_top_table_rows_survive_structured_parts_once(monkeypatch):
    rows=[word('FIRST',10,10),word('SECOND',100,10)]
    monkeypatch.setattr(O,'preflight',lambda settings:None)
    monkeypatch.setattr(O,'_tesseract',lambda *args:result(rows))
    monkeypatch.setattr(O,'_table_rows',lambda ws,language:
                        ([(10,['FIRST','10']),(10,['SECOND','75'])],set(map(id,ws))))
    value,_,_=O.transcribe(b'',{'language':'eng','quality':'quick'},None,
                          'Synthetic',rendered=True)
    assert [part for kind,part in value.parts if kind=='table']==[
        [['FIRST','10'],['SECOND','75']]]
    assert value.count('FIRST')==1 and value.count('SECOND')==1


def test_private_page34_specs_remain_prose_with_all_numbers_once(monkeypatch):
    path=Path(__file__).parent/'fixtures/update49/boq2-page34-prose.tsv'
    rows=list(csv.DictReader(io.StringIO(path.read_text(encoding='utf-8')),delimiter='\t'))
    assert O._table_rows(rows,'ara+eng')==([],set())
    monkeypatch.setattr(O,'preflight',lambda settings:None)
    monkeypatch.setattr(O,'_tesseract',lambda *args:result(rows))
    value,_,_=O.transcribe(b'',{'language':'ara+eng','quality':'quick'},None,
                          'Private page34 TSV replay',rendered=True)
    assert value.count('Activation range (switching distance) 10 mm')==1
    assert value.count('Current rating not more than 75 mA at 24Vdc.')==1
    assert value.count('Two wire connection with min 3.5 m long cable.')==1
    assert not isinstance(value,O.ScanText)


def test_short_numeric_cells_still_keep_two_and_three_column_ownership():
    for columns in (2,3):
        rows=[word(str(100*r+c),10+250*c,40*r,width=35,height=22,line=r+1)
              for r in range(3) for c in range(columns)]
        tables,used=O._table_rows(rows,'eng')
        assert [cells for _,cells in tables]==[
            [str(100*r+c) for c in range(columns)] for r in range(3)]
        assert used==set(map(id,rows))
