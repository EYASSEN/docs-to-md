# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Original scan pixels, numeric safeguards, matched grids, and stable font training."""
import copy,hashlib,io,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from PIL import Image,ImageDraw
from foldertomd import scanglyphs as G,scanlayout as S,ocr as O,fontdecode as F
from foldertomd.render import RuledRows
ROOT=Path(__file__).resolve().parents[1]


def result(value='',score=95):
    return SimpleNamespace(returncode=0,stdout=('text\tconf\tleft\ttop\twidth\theight\tblock_num\tpar_num\tline_num\n'+
        (f'{value}\t{score}\t0\t0\t10\t10\t1\t1\t1\n' if value else '')).encode())


@pytest.fixture(scope='module')
def original():
    with Image.open(ROOT/'tests/fixtures/update40/digit-cells.png') as image:return image.convert('RGB')


def digit_case():
    fixture=json.loads((ROOT/'tests/fixtures/update40/digit-column.json').read_text(encoding='utf-8'))
    rows=[['']*fixture['columns'] for _ in range(fixture['row_count'])]
    grid={'columns':fixture['columns'],'rows':[[] for _ in rows]};readings=[]
    for cell in fixture['cells']:
        r,a,bb,ws=cell['row'],cell['column'],cell['bounds'],cell['words']
        rows[r][a]=cell['text'];grid['rows'][r]=[(a,a+1,bb)];readings.append((r,a,bb,ws))
    def replay(data,args):
        key=hashlib.sha256(Image.open(io.BytesIO(data)).convert('RGB').tobytes()).hexdigest()
        item=next(t for t in fixture['ocr_replay'] if t['pixel_sha256']==key and t['args']==args)
        return SimpleNamespace(returncode=item['returncode'],stdout=item['stdout'].encode())
    return rows,grid,readings,replay


def test_original_digit_column_learns_from_ocr_and_keeps_unresolved_cells(original):
    rows,grid,readings,replay=digit_case();before=copy.deepcopy(rows)
    assert G.refine_digits(original,grid,rows,readings,replay,O._png,'ara+eng',S.cell_content)==9
    for r,value in [(6,'٤'),(7,'٥'),(14,'١٠'),(17,'١٣'),(18,'١٤'),(20,'١٦'),(21,'١٧'),(22,'١٨'),(23,'١٩')]:assert rows[r][29]==value
    # Update41 resolves two more shapes; remaining ambiguity is not filled by sequence.
    for r in (4,5,8,9,10,11,15,16):assert rows[r]==before[r]


@pytest.mark.parametrize('value',['00123','٠٠١٢٣','+12','-12','12.50','١٢٫٥٠','1/2','12%'])
def test_digit_refinement_preserves_codes_signs_decimals_fractions_and_units(original,value):
    rows,grid,readings,replay=digit_case();rows[17][29]=value
    G.refine_digits(original,grid,rows,readings,replay,O._png,'ara+eng',S.cell_content)
    assert rows[17][29]==value


@pytest.mark.parametrize('case,accepted',[
    ('agree',True),('disagree',False),('missing-second',False),('weak',False),
    ('strong-primary-weak-alternates',False),('strong-primary-agree',True),
    ('leading-zero',False),('decimal',False)])
def test_percent_requires_pixel_evidence_and_two_independent_segmentation_readings(original,case,accepted):
    # An original printed percentage mark, rather than a synthetic '%' character.
    with Image.open(ROOT/'tests/fixtures/update40/percent-cell.png') as source:patch=source.convert('RGB')
    image=Image.new('RGB',(patch.width,patch.height*5),'white')
    rows=[['%'] for _ in range(4)]+[['54']];readings=[]
    for r in range(5):
        image.paste(patch,(0,r*patch.height));bounds=(0,r*patch.height,patch.width,(r+1)*patch.height)
        readings.append((r,0,bounds,[{'text':rows[r][0],'conf':'95' if r<4 else '60'}]))
    if case.startswith('strong-primary'):readings[4][3][0]['conf']='95'
    if case=='leading-zero':rows[4][0]='0012'
    if case=='decimal':rows[4][0]='12.50'
    before=copy.deepcopy(rows);calls=[]
    def run(data,args):
        calls.append(args);second=args[args.index('--psm')+1]=='10'
        value='7' if case=='disagree' and second else '' if case=='missing-second' and second else '%'
        score=30 if case=='weak' else 80 if case=='strong-primary-weak-alternates' else 95
        return result(value,score)
    changed=G.refine_percent(image,rows,readings,run,O._png,lambda im:im)
    assert changed==int(accepted) and rows[4][0]==('%' if accepted else before[4][0])
    assert rows[:4]==before[:4]
    if accepted:assert [args[args.index('--psm')+1] for args in calls]==['6','10']


@pytest.mark.parametrize('case',['matching','different-ownership','render-failure'])
def test_higher_resolution_only_refines_matching_cell_ownership(monkeypatch,case):
    image=Image.new('RGB',(90,80),'white')
    grid={'columns':9,'rows':[[(c,c+1,(c*10,r*10,c*10+10,r*10+10)) for c in range(9)] for r in range(8)]}
    high=Image.new('RGB',(180,160),'white');higher=copy.deepcopy(grid)
    higher['rows']=[[(a,b,tuple(n*2 for n in bb)) for a,b,bb in row] for row in grid['rows']]
    if case=='different-ownership':higher['rows'][0][0]=(0,2,higher['rows'][0][0][2])
    monkeypatch.setattr(O,'cell_content',lambda im:im)
    monkeypatch.setattr(O,'best_ruled_grid',lambda im:(im,higher))
    seen=[]
    monkeypatch.setattr(G,'refine_digits',lambda im,*args:seen.append(im.size) or 0)
    monkeypatch.setattr(G,'refine_percent',lambda *args:0)
    def source():
        if case=='render-failure':raise OSError('Unavailable second render')
        return high
    rows,_=O._grid_transcription(image,grid,lambda *args:result('عنوان'),'ara',source)
    assert rows.ocr_review['glyph_resolution']==(300 if case=='matching' else 0)
    assert seen==[high.size if case=='matching' else image.size]
    assert rows.spans==[[(c,c+1) for c in range(9)] for _ in range(8)]
    assert all(value=='عنوان' for row in rows for value in row)


@pytest.mark.parametrize('angle',[90,180,270])
def test_second_pdf_render_follows_verified_scan_orientation(monkeypatch,angle):
    low=Image.new('RGB',(100,150),'white');high=Image.new('RGB',(200,300),'white')
    ImageDraw.Draw(high).rectangle((0,0,20,40),fill='red');seen=[]
    monkeypatch.setattr(O,'preflight',lambda *a:None)
    monkeypatch.setattr(O,'_tesseract',lambda *a:result())
    monkeypatch.setattr(O,'verified_orientation',lambda *a:(angle,16,True))
    monkeypatch.setattr(O,'best_ruled_grid',lambda im:(im,{'bbox':(0,0,50,50)}))
    def grid_read(im,grid,run,language,glyph_source):
        seen.append(glyph_source());return RuledRows([['نص']],[[(0,1)]]),[95]
    monkeypatch.setattr(O,'_grid_transcription',grid_read)
    O.transcribe(O._png(low),{'language':'ara','quality':'standard'},None,'Scan',rendered=True,glyph_source=lambda:high)
    expected=high.rotate(-angle,expand=True,fillcolor='white')
    assert seen[0].size==expected.size and seen[0].tobytes()==expected.tobytes()


@pytest.mark.parametrize('quality',['standard','high','quick'])
def test_legacy_font_training_uses_stable_models_without_mutating_quality(monkeypatch,quality):
    settings={'quality':quality,'language':'ara+eng'};before=dict(settings);checked=[];commands=[]
    monkeypatch.setattr(O,'preflight',lambda s:checked.append(dict(s)))
    monkeypatch.setattr(O,'_tesseract',lambda root,data,args,work,threads:commands.append(args) or result('نص'))
    assert F.ocr_words(b'pixels',settings,None,psm='7',origin=(10,20))
    assert settings==before and checked[0]['quality']=='standard' and commands[0][:2]==['-l','ara+eng']
    assert O.ocr_language({'quality':'high','language':'ara+eng'})=='ara_best+eng_best'


@pytest.mark.parametrize('revision',[None,39])
def test_existing_markdown_assessment_preserves_provenance(tmp_path,monkeypatch,revision):
    from scripts import assess_update40 as A
    from foldertomd import pdf as P
    markdown=tmp_path/'old.md';markdown.write_text('Existing incomplete result\n',encoding='utf-8');before=markdown.read_bytes()
    monkeypatch.setattr(P,'extract_pdf',lambda *a:pytest.fail('Existing Markdown must not be reconverted'))
    work=tmp_path/'assessment';args=['--markdown',str(markdown),'--work',str(work),'--quality','high']
    if revision is not None:args+=['--reported-revision',str(revision)]
    assert A.main(args)==1
    evidence=json.loads((work/'assessment.json').read_text(encoding='utf-8'))
    from foldertomd.engine import CONVERSION_REVISION
    assert evidence['conversion_revision']==revision and evidence['assessment_code_revision']==CONVERSION_REVISION
    assert evidence['assessment_mode']=='existing_markdown' and evidence['text_review_required']
    assert evidence['markdown_sha256']==hashlib.sha256(before).hexdigest() and markdown.read_bytes()==before
    with pytest.raises(RuntimeError,match='fresh'):A.main(args)
