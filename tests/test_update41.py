# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Additional pixel evidence, non-recursive style learning, and assessment corrections."""
import copy,hashlib,json,io
from pathlib import Path
from types import SimpleNamespace
import pytest
from PIL import Image,ImageDraw
from foldertomd import scanglyphs as G,ocr as O
ROOT=Path(__file__).resolve().parents[1]


def cell_crop(row):
    data=json.loads((ROOT/'tests/fixtures/update40/digit-column.json').read_text(encoding='utf-8'))
    box=next(c['bounds'] for c in data['cells'] if c['row']==row)
    from foldertomd.scanlayout import cell_content
    with Image.open(ROOT/'tests/fixtures/update40/digit-cells.png') as image:return cell_content(image.crop(box))


def percent_patch():
    with Image.open(ROOT/'tests/fixtures/update40/percent-cell.png') as image:return image.convert('RGB')


def response(value='%',score=95):
    return SimpleNamespace(returncode=0,stdout=f'text\tconf\n{value}\t{score}\n'.encode())


def test_style_learning_requires_strong_multidigit_shapes_and_has_a_per_label_limit():
    refs=G.references()+[('١',G._norm(cell_crop(3)))]
    weak=cell_crop(6);strong=cell_crop(18)
    assert G.read_digits(weak,refs) is None
    assert G.style_references([weak],refs)==[]
    anchors=G.style_references([strong]*12+[weak],refs)
    assert len(anchors)==2 and all(ch=='٤' for ch,_ in anchors)
    assert G.read_digits(weak,refs+anchors)[0]=='٤'
    assert all(ch not in '٠١' for ch,_ in anchors)


def test_style_templates_do_not_cancel_an_accepted_original_reading():
    # The old reading of 19 was correct. A new local '9' template narrows the
    # first-digit margin, so the original accepted candidate must be preserved.
    refs=G.references()+[('١',G._norm(cell_crop(3)))]
    crop=cell_crop(23);candidate=G.read_digits(crop,refs,.12)
    assert candidate and candidate[0]=='١٩'
    anchors=G.style_references([cell_crop(r) for r in (14,18,19,20,21,22,23)],refs)
    assert G.read_digits(crop,refs+anchors,.12) is None
    from test_update40 import digit_case
    rows,grid,readings,replay=digit_case()
    with Image.open(ROOT/'tests/fixtures/update40/digit-cells.png') as image:
        from foldertomd.scanlayout import cell_content
        G.refine_digits(image.convert('RGB'),grid,rows,readings,replay,O._png,'ara+eng',cell_content)
    assert rows[23][29]=='١٩'


def test_symbol_compaction_removes_sparse_speckles_and_keeps_the_printed_mark():
    patch=percent_patch();image=Image.new('RGB',(80,120),'white');image.paste(patch,(25,40))
    ImageDraw.Draw(image).rectangle((2,2,3,3),fill='black')
    compact=G.compact_symbol(image)
    assert compact.width<=patch.width and compact.height<=patch.height
    assert G.ranked_shape(compact,G.references()+[('%',G._norm(patch))],G.DIGITS+'%')[0][0]=='%'
    assert sum(p<160 for p in compact.convert('L').tobytes())>=.92*sum(p<160 for p in image.convert('L').tobytes())


@pytest.mark.parametrize('shape',['zero','one','dash'])
def test_symbol_compaction_does_not_remove_substantial_numeric_strokes(shape):
    patch=percent_patch();image=Image.new('RGB',(90,60),'white');image.paste(patch,(45,15));draw=ImageDraw.Draw(image)
    if shape=='zero':draw.ellipse((20,20,26,26),fill='black')
    elif shape=='one':draw.rectangle((20,15,23,34),fill='black')
    else:draw.rectangle((15,25,30,26),fill='black')
    compact=G.compact_symbol(image)
    assert compact.width>patch.width+5
    assert sum(p<160 for p in compact.convert('L').tobytes())==sum(p<160 for p in image.convert('L').tobytes())


def symbol_case(value):
    patch=percent_patch();image=Image.new('RGB',(patch.width,patch.height*5),'white');rows=[['%'] for _ in range(4)]+[[value]];readings=[]
    for r in range(5):
        image.paste(patch,(0,r*patch.height));readings.append((r,0,(0,r*patch.height,patch.width,(r+1)*patch.height),[{'text':rows[r][0],'conf':'95'}]))
    return image,rows,readings


@pytest.mark.parametrize('value',['0012','0%','1%','12.50','-5','١٫٠٪'])
def test_percentage_alternates_preserve_numeric_codes_and_units(value):
    image,rows,readings=symbol_case(value);calls=[]
    changed=G.refine_percent(image,rows,readings,lambda *a:calls.append(a) or response(),O._png,lambda im:im)
    assert changed==0 and rows[4][0]==value and not calls


@pytest.mark.parametrize('second_agrees',[True,False])
def test_binarized_symbol_still_requires_both_segmentation_readings(second_agrees):
    image,rows,readings=symbol_case('weak');calls=[]
    def run(data,args):
        calls.append(args)
        if len(calls)==1:return response('noise',40)
        if len(calls)==3 and not second_agrees:return response('8',95)
        return response()
    changed=G.refine_percent(image,rows,readings,run,O._png,lambda im:im)
    assert changed==int(second_agrees) and rows[4][0]==('%' if second_agrees else 'weak')
    assert [a[a.index('--psm')+1] for a in calls]==['6','6','10']


def test_corrected_reference_records_the_original_source_and_three_separate_marks():
    truth=json.loads((ROOT/'tests/fixtures/update39/ground-truth.json').read_text(encoding='utf-8'))
    assert truth['reference_revision']==2 and len(truth['percent_markers'])==52
    assert all([18,c] in truth['percent_markers'] for c in (3,4,5))
    assert len(truth['regions'])==642 and truth['columns']==30 and truth['row_bands']==24
    proof=json.loads((ROOT/'tests/fixtures/update41/reference-correction.json').read_text(encoding='utf-8'))
    assert proof['source_pdf_sha256']==hashlib.sha256((ROOT/'tests/fixtures/update39/coefficient-table.pdf').read_bytes()).hexdigest()
    boxes=[v['bounds'] for v in proof['cells']]
    assert all(a[2]<b[0] for a,b in zip(boxes,boxes[1:]))


def test_assessment_scope_uses_the_actual_reference_count():
    from scripts.assess_update39 import assess
    truth=json.loads((ROOT/'tests/fixtures/update39/ground-truth.json').read_text(encoding='utf-8'))
    value=assess('No table',truth)
    assert value['percent_markers']['total']==52 and '52 literal percentage' in value['scope']
    assert value['text_review_required'] and not value['geometry']['passed']
