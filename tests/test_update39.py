# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Partial ruled boundaries, rowspan ownership, and the original scan geometry."""
import io,json
from pathlib import Path
from types import SimpleNamespace
from html.parser import HTMLParser
import pytest
import pymupdf as fitz
from PIL import Image,ImageDraw
from foldertomd import scanlayout as S,ocr as O,pdf as P
from foldertomd.render import RuledRows,table
ROOT=Path(__file__).resolve().parents[1]


def partial_grid():
    image=Image.new('RGB',(900,750),'white');draw=ImageDraw.Draw(image)
    for y in (60,180,600,700):draw.line((40,y,860,y),fill='black',width=2)
    for y in (300,420):draw.line((40,y,600,y),fill='black',width=2)
    for x in (40,200,400,600,860):draw.line((x,60,x,700),fill='black',width=2)
    draw.line((730,180,730,600),fill='black',width=2)
    return image


def regions(grid):
    return sorted([r,r+grid.get('rowspans',{}).get((r,first),1),first,last]
        for r,row in enumerate(grid['rows']) for first,last,_ in row)


def assert_coverage(grid):
    slots=set()
    for r0,r1,c0,c1 in regions(grid):
        for r in range(r0,r1):
            for c in range(c0,c1):
                assert (r,c) not in slots
                slots.add((r,c))
    assert slots=={(r,c) for r in range(len(grid['rows'])) for c in range(grid['columns'])}


def test_partial_separators_recover_subrows_and_short_column():
    grid=S.ruled_grid(partial_grid())
    assert grid['columns']==5 and len(grid['rows'])==5
    assert grid['rowspans']=={(1,3):3,(1,4):3}
    assert all(last<=3 for row in grid['rows'][2:4] for first,last,_ in row)
    assert [0,1,3,5] in regions(grid)
    assert_coverage(grid)


def test_rule_gap_repair_requires_a_long_connected_stroke():
    image=Image.new('L',(220,50),255);draw=ImageDraw.Draw(image)
    draw.line((10,10,36,10),fill=0);draw.line((40,10,160,10),fill=0)
    draw.line((10,30,36,30),fill=0)
    mask=S._joined_rule_mask(image,45)
    assert mask.getpixel((12,10))==0 and mask.getpixel((38,10))==0
    assert mask.getpixel((12,30))==255


def test_nonrectangular_missing_boundaries_are_rejected():
    # Three joined slots form an L; no valid HTML rectangular merge can represent it.
    horizontal=[[True,True],[False,True],[True,True]]
    vertical=[[True,False,True],[True,True,True]]
    assert S._rectangles(horizontal,vertical) is None


def test_ambiguous_refinement_preserves_coarse_grid(monkeypatch):
    monkeypatch.setattr(S,'_refine_grid',lambda *a:None)
    grid=S.ruled_grid(partial_grid())
    assert grid is not None and grid['layout_review'] is True
    assert_coverage(grid)


@pytest.mark.parametrize('dpi',[144,200,300])
def test_original_scan_geometry_matches_manually_reviewed_cells(dpi):
    fixture=ROOT/'tests/fixtures/update39'
    expected=json.loads((fixture/'ground-truth.json').read_text(encoding='utf-8'))
    with fitz.open(fixture/'coefficient-table.pdf') as doc:
        image=Image.open(io.BytesIO(doc[0].get_pixmap(dpi=dpi,alpha=False).tobytes('png'))).rotate(90,expand=True)
    selected,grid=S.best_ruled_grid(image)
    assert grid['columns']==expected['columns']
    assert len(grid['rows'])==expected['row_bands']
    assert regions(grid)==expected['regions']
    assert not grid.get('layout_review')
    assert grid['fine_skew']==-.5
    assert_coverage(grid)


@pytest.mark.parametrize('language,value,anchor',[('eng','TITLE',0),('ara','العنوان',1)])
def test_merged_origin_is_read_once_and_rowspan_follows_script(monkeypatch,language,value,anchor):
    monkeypatch.setattr(O,'cell_content',lambda image:image)
    grid={'columns':3,'rows':[[(0,2,(0,0,40,40)),(2,3,(40,0,60,20))],[(2,3,(40,20,60,40))]],'rowspans':{(0,0):2}}
    calls=[]
    def run(*args):
        calls.append(args)
        return SimpleNamespace(returncode=0,stdout=('text\tconf\n'+value+'\t95\n').encode())
    rows,_=O._grid_transcription(Image.new('RGB',(60,40),'white'),grid,run,language)
    assert len(calls)==3 and rows.rowspans=={(0,anchor):2}
    assert rows[0][anchor]==value
    assert table(rows).count('rowspan="2"')==1
    fixed=P._fix_presentation_forms(O.ScanText(value,[('table',rows)])).parts[0][1]
    assert fixed.rowspans==rows.rowspans and fixed.spans==rows.spans


def test_vertical_merge_without_horizontal_merge_uses_html_and_skips_covered_slot():
    rows=RuledRows([['A','B'],['','C']],[[(0,1),(1,2)],[(1,2)]],{(0,0):2})
    value=table(rows)
    assert '<td rowspan="2">A</td>' in value
    assert value.count('<td')==3 and '<tr><td>C</td></tr>' in value


def test_fully_covered_row_retains_its_row_band():
    rows=RuledRows([['A',''],['','']],[[(0,2)],[]],{(0,0):2})
    value=table(rows)
    assert '<td colspan="2" rowspan="2">A</td>' in value
    assert value.count('<tr>')==2 and '<tr></tr>' in value


def test_span_mapping_keeps_text_escaping_and_metadata():
    rows=RuledRows([['<A>',''],['','']],[[(0,2)],[]],{(0,0):2})
    copied=rows.map_cells(lambda value:value.replace('A','B'))
    assert copied.rowspans==rows.rowspans and copied.spans==rows.spans
    assert '&lt;B&gt;' in table(copied)


def test_generated_original_table_has_one_html_owner_per_slot():
    fixture=ROOT/'tests/fixtures/update39';expected=json.loads((fixture/'ground-truth.json').read_text())
    cells=[['']*expected['columns'] for _ in range(expected['row_bands'])];spans=[[] for _ in cells];heights={}
    for r0,r1,c0,c1 in expected['regions']:
        cells[r0][c0]=f'{r0}:{c0}';spans[r0].append((c0,c1))
        if r1-r0>1:heights[r0,c0]=r1-r0
    class Layout(HTMLParser):
        def __init__(self):super().__init__();self.r=-1;self.c=0;self.slots=set();self.origins=0
        def handle_starttag(self,tag,attrs):
            if tag=='tr':self.r+=1;self.c=0
            if tag!='td':return
            while (self.r,self.c) in self.slots:self.c+=1
            attrs=dict(attrs);width=int(attrs.get('colspan',1));height=int(attrs.get('rowspan',1))
            for r in range(self.r,self.r+height):
                for c in range(self.c,self.c+width):
                    assert (r,c) not in self.slots
                    self.slots.add((r,c))
            self.c+=width;self.origins+=1
    layout=Layout();layout.feed(table(RuledRows(cells,spans,heights)))
    assert layout.origins==len(expected['regions'])
    assert layout.slots=={(r,c) for r in range(24) for c in range(30)}


def test_full_width_first_text_line_is_not_erased_as_a_rule():
    image=Image.new('RGB',(120,80),'white');draw=ImageDraw.Draw(image)
    for x in range(6,114,18):draw.text((x,3),'A',fill='black')
    draw.text((40,40),'body',fill='black')
    crop=S.cell_content(image)
    assert crop is not None and crop.height>35


def test_multiline_text_at_left_edge_is_not_erased_as_a_rule():
    image=Image.new('RGB',(120,90),'white');draw=ImageDraw.Draw(image)
    for y in range(3,84,16):draw.text((4,y),'L',fill='black')
    draw.text((55,40),'body',fill='black')
    crop=S.cell_content(image)
    assert crop is not None and crop.height>70


@pytest.mark.parametrize('different_number',[False,True])
def test_arabic_cell_refinement_preserves_disputed_numbers(monkeypatch,different_number):
    monkeypatch.setattr(O,'cell_content',lambda image:image)
    first='نص عربي x'+(' 00123' if different_number else '')
    second='النص العربي المحسن'+(' 00124' if different_number else '')
    readings=iter([first,second]);calls=[]
    def run(data,args):
        calls.append(args);value=next(readings)
        return SimpleNamespace(returncode=0,stdout=('text\tconf\n'+value+'\t'+('30' if len(calls)==1 else '90')+'\n').encode())
    grid={'columns':2,'rows':[[(0,2,(0,0,100,50))]]}
    rows,_=O._grid_transcription(Image.new('RGB',(100,50),'white'),grid,run,'ara+eng')
    assert len(calls)==2 and calls[-1][1]=='ara'
    assert rows[0][0]==(first if different_number else second)
    assert rows.ocr_review['number_disagreements']==int(different_number)


def test_failed_cell_alternate_retains_primary_text(monkeypatch):
    monkeypatch.setattr(O,'cell_content',lambda image:image)
    count=[0]
    def run(*args):
        count[0]+=1
        return SimpleNamespace(returncode=0 if count[0]==1 else 1,stdout='text\tconf\nالنص العربي\t30\n'.encode())
    rows,_=O._grid_transcription(Image.new('RGB',(100,50),'white'),{'columns':2,'rows':[[(0,2,(0,0,100,50))]]},run,'ara+eng')
    assert rows[0][0]=='النص العربي' and rows.ocr_review['arabic_refinements']==0


def test_assessment_reports_text_errors_even_with_correct_geometry():
    from scripts.assess_update39 import assess
    truth={'columns':2,'row_bands':1,'regions':[[0,1,0,1],[0,1,1,2]],
           'item_numbers':[[0,1,'19']],'percent_markers':[[0,0]]}
    result=assess('<table><tr><td>18</td><td>%</td></tr></table>',truth)
    assert result['geometry']['passed'] and result['text_review_required']
    assert result['item_numbers']['correct']==0 and result['percent_markers']['correct']==1


def test_assessment_rejects_missing_or_overlapping_cells():
    from scripts.assess_update39 import assess
    truth={'columns':2,'row_bands':2,'regions':[[0,1,0,1],[0,1,1,2],[1,2,0,1],[1,2,1,2]],
           'item_numbers':[],'percent_markers':[]}
    assert not assess('<table><tr><td>x</td></tr></table>',truth)['geometry']['passed']
    with pytest.raises(ValueError,match='Overlapping'):
        assess('<table><tr><td>b</td><td rowspan="2">a</td></tr><tr><td colspan="2">c</td></tr></table>',truth)
