# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unknown numeric font codes and pixel-established scan cell spans."""
import io,json
from pathlib import Path
from types import SimpleNamespace
import pytest
import pymupdf as fitz
from PIL import Image
from foldertomd import fontdecode as F,ocr as O,pdf as P
from foldertomd.render import RuledRows,table
ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('case,expected',[
 ('agree',True),('one-page',False),('disagree',False),('weak',False),
 ('unlinked-separator',False),('mostly-letters',False),('already-known',False)])
def test_unknown_numeric_recovery_requires_context_and_independent_agreement(monkeypatch,case,expected):
 m=F.FontModel.__new__(F.FontModel);m.mapping={'digit':'٧','dash':'-','letter':'ب'};m.blank=set();m.doc=[None,None]
 m._samples={'unknown':[(0,(0,0,1,1)),(1,(0,0,1,1))]}
 if case=='one-page':m._samples['unknown']=[(0,(0,0,1,1)),(0,(0,0,1,1))]
 if case=='already-known':m.mapping['unknown']='٢'
 from collections import defaultdict,Counter
 near=defaultdict(Counter,{'unknown':Counter({'dash':4}),'dash':Counter({'digit':4})})
 if case=='unlinked-separator':near['dash']=Counter({'letter':4})
 if case=='mostly-letters':near['unknown']['letter']=20
 monkeypatch.setattr(m,'_neighbours',lambda:near)
 readings=iter([('٤',.9),('٣' if case=='disagree' else '٤',.81 if case=='weak' else .9)])
 monkeypatch.setattr(F,'classify_shape',lambda *a,**kw:next(readings))
 original=dict(m.mapping);count=m.recover_numeric_glyphs([])
 assert count==int(expected)
 assert all(m.mapping[k]==v for k,v in original.items())
 assert ('unknown' in m.mapping)==(expected or case=='already-known')


def test_actual_legacy_document_recovers_digit_four_without_overwriting_known_codes():
 fixture=ROOT/'tests/fixtures/update38'
 with fitz.open(fixture/'arSuppSpec.pdf') as doc:
  m=F.FontModel(doc);state=json.loads((fixture/'font-baseline.json').read_text(encoding='utf-8'))
  m.mapping={tuple(k):v for k,v in state['mapping']};m.blank={tuple(k) for k in state['blank']};m.find_spaces(range(len(doc)))
  original=dict(m.mapping);before=sum(m.decode(p)[0].count('[?]') for p in doc)
  assert m.recover_numeric_glyphs(F.shape_references())>=1
  assert m.mapping[('MSTT31c3fe00','GD1')]=='٤'
  assert all(m.mapping[k]==v for k,v in original.items())
  after=sum(m.decode(p)[0].count('[?]') for p in doc)
  assert before-after>=100


def test_merged_scan_cells_render_html_spans_and_escape_content():
 rows=RuledRows([['<Header>','','tail'],['a|b','x\ny','&']], [[(0,2),(2,3)],[(0,1),(1,2),(2,3)]])
 value=table(rows)
 assert '<td colspan="2">&lt;Header&gt;</td>' in value
 assert '<td>a|b</td>' in value and 'x<br>y' in value and '<td>&amp;</td>' in value
 assert value.count('<td')==5


def test_unmerged_scan_table_keeps_markdown_output():
 rows=[['name','value'],['a','1']]
 assert table(RuledRows(rows,[[(0,1),(1,2)]]*2))==table(rows)


@pytest.mark.parametrize('language,value,expected_spans',[
 ('eng','HEADER',[[(0,2),(2,3)]]),('ara','العنوان',[[(0,1),(1,3)]])])
def test_grid_ocr_preserves_merged_span_after_script_ordering(monkeypatch,language,value,expected_spans):
 monkeypatch.setattr(O,'cell_content',lambda image:image)
 result=SimpleNamespace(returncode=0,stdout=('text\tconf\n'+value+'\t95\n').encode())
 grid={'columns':3,'rows':[[(0,2,(0,0,20,20)),(2,3,(20,0,40,20))]]}
 rows,_=O._grid_transcription(Image.new('RGB',(40,20),'white'),grid,lambda *a:result,language)
 assert isinstance(rows,RuledRows) and rows.spans==expected_spans
 assert sum(last-first for first,last in rows.spans[0])==3
 assert 'colspan="2"' in table(rows)


def test_pdf_unicode_normalization_keeps_table_span_metadata():
 rows=RuledRows([['ﺑ','','x']], [[(0,2),(2,3)]])
 value=P._fix_presentation_forms(O.ScanText('ﺑ',[('table',rows)]))
 fixed=value.parts[0][1]
 assert isinstance(fixed,RuledRows) and fixed.spans==rows.spans and fixed[0][0]=='ب'
 assert 'colspan="2"' in table(fixed)
