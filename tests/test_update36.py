# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Replay submitted Windows readings; these tests do not launch Windows OCR."""
import copy,csv,io,json,re,sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from foldertomd import ocr as O,ocrtable as T,ocrselect as S
from foldertomd.context import Context

def records():
    return json.loads((ROOT/'tests/fixtures/update36/windows-update35-trace.json').read_text(encoding='utf-8'))

def parsed(record):
    return S.words(SimpleNamespace(returncode=record['returncode'],stdout=record['stdout'].encode('utf-8')))

def install_replay(monkeypatch,reads):
    position=[0]
    def launch(root,data,args,work,threads):
        assert position[0]<len(reads),'Unexpected extra OCR call during recorded replay'
        record=reads[position[0]]
        assert args==record['args'],(position[0],args,record['args'])
        position[0]+=1
        return SimpleNamespace(returncode=record['returncode'],stdout=record['stdout'].encode('utf-8'),stderr=record['stderr'].encode('utf-8'))
    monkeypatch.setattr(O,'preflight',lambda settings:None)
    monkeypatch.setattr(O,'_tesseract',launch)
    return position

def test_exact_submitted_windows_readings_produce_all_original_table_cells(tmp_path,monkeypatch):
    from foldertomd.pdf import extract_pdf
    reads=records();position=install_replay(monkeypatch,reads)
    source=ROOT/'tests/fixtures/update34/electro-table-pages.pdf'
    expected=json.loads((source.parent/'ground-truth.json').read_text(encoding='utf-8'))
    ctx=Context(dict(source=str(source),work=str(tmp_path),relative=source.name,asset_link='assets',
        settings=dict(language='ara+eng',ocr='auto',quality='standard',decode_fonts=False)))
    try:extract_pdf(ctx)
    finally:ctx.close()
    assert position[0]==len(reads)==42
    parts=re.split(r'^## Page \d+\s*$',(tmp_path/'result.md').read_text(encoding='utf-8'),flags=re.M)[1:]
    assert len(parts)==2
    for page,part in zip(expected['pages'],parts):
        rows=[[c.strip() for c in line.split('|')[1:-1]] for line in part.splitlines()
              if line.startswith('|') and not re.fullmatch(r'[|\s:-]+',line)]
        if page['fixture_page']==2:rows=rows[1:]
        assert rows==page['rows']

def test_recorded_confidences_require_a_second_strong_context():
    reads=records();first,second=parsed(reads[7]),parsed(reads[8])
    regional=[w for w in parsed(reads[3]) if int(w['top'])==63 and int(w['left'])<350]
    sparse=[w for w in parsed(reads[2]) if 730<=int(w['top'])<=735 and int(w['left'])<700]
    assert S.number_tokens(T._value(first))==S.number_tokens(T._value(second))==('600','900')
    assert not T._confirmed(first,second,regional)
    assert T._confirmed(first,second,regional,sparse)

@pytest.mark.parametrize('defect',['missing','conflict','weak','other_row','other_column','failed','local_low'])
def test_replay_keeps_the_original_number_when_corroboration_is_invalid(defect,monkeypatch):
    import pymupdf as fitz
    reads=copy.deepcopy(records()[:13]);record=reads[7] if defect=='local_low' else reads[2]
    source=list(csv.DictReader(io.StringIO(record['stdout']),delimiter='\t',quoting=csv.QUOTE_NONE))
    changed=False
    for word in source:
        target=(word.get('text')=='900' and (defect=='local_low' or (word['left']=='615' and word['top']=='731')))
        if not target:continue
        changed=True
        if defect=='missing':word['text']=''
        elif defect=='conflict':word['text']='901'
        elif defect=='weak':word['conf']='84.9'
        elif defect=='other_row':word['top']=str(int(word['top'])+500)
        elif defect=='other_column':word['left']=str(int(word['left'])+500)
        elif defect=='local_low':word['conf']='49'
    assert changed
    stream=io.StringIO();writer=csv.DictWriter(stream,list(source[0]),delimiter='\t')
    writer.writeheader();writer.writerows(source);record['stdout']=stream.getvalue()
    if defect=='failed':record['returncode']=1
    position=install_replay(monkeypatch,reads)
    with fitz.open(ROOT/'tests/fixtures/update34/electro-table-pages.pdf') as doc:
        data=doc[0].get_pixmap(dpi=200,alpha=False).tobytes('png')
    with Image.open(io.BytesIO(data)) as image:
        value,warnings,_=O.transcribe(O._png(image),dict(language='ara+eng',quality='standard'),None,'Recorded Windows page',rendered=True)
    assert position[0]==len(reads)==13
    table_rows=[row for kind,part in value.parts if kind=='table' for row in part]
    assert table_rows==[['up to 600','6','3'],['over 600 and up to 0','4','2'],['over 900 and up to 1200','3','1.5']]
    assert any('original cell retained' in warning for warning in warnings)
