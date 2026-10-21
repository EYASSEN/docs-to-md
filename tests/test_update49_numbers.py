"""Real source-pixel regression and conservative inline-number negative cases."""
import copy,json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageOps
import pytest
from foldertomd import ocr,scannumbers

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=ROOT/'tests/fixtures/update49'


def private_cell():
    image=Image.open(FIXTURES/'boq1-page3-description.png').convert('RGB')
    trace=json.loads((FIXTURES/'boq1-page3-words.json').read_text('utf8'))
    return image,trace['words']


def no_ocr(*args):
    raise AssertionError('Ambiguous and protected readings must not invoke OCR')


def test_reviewed_inline_numeric_failures_recover_from_real_pixels(tmp_path):
    image,primary=private_cell();before=copy.deepcopy(primary);calls=[]
    root=ocr.preflight({'language':'ara+eng','quality':'standard'})
    def run(data,args):
        calls.append(args)
        return ocr._tesseract(root,data,args,tmp_path,1)
    assert scannumbers.refine_numeric_words(image,primary,run,ocr._png)==2
    assert primary[25]['text']=='16،)'
    assert primary[252]['text']=='٢٥'
    assert primary[253]['text']==before[253]['text']  # retained unit ownership
    assert len(calls)==2 and all('-c' not in args for args in calls)
    assert all(a==b for n,(a,b) in enumerate(zip(primary,before)) if n not in (25,252))
    assert all(primary[n][key]==before[n][key] for n in (25,252)
               for key in ('left','top','width','height','conf'))


def test_actual_latin_letters_compete_with_arabic_digits():
    # Use the built-in font in Pillow, so the check runs without system fonts.
    font=ImageFont.load_default(size=32)
    for value in ('YO','Yo','TO','ON','NO','AB','18','00'):
        image=Image.new('RGB',(130,70),'white')
        ImageDraw.Draw(image).text((10,10),value,font=font,fill='black')
        assert scannumbers._shape_number(image) is None


def test_latin_candidate_without_nearby_unit_is_retained():
    image,primary=private_cell();words=[copy.deepcopy(primary[252])]
    for n in (249,250,251,254,255):words.append(copy.deepcopy(primary[n]))
    for word in words[1:]:
        if scannumbers.UNIT.fullmatch(scannumbers.plain(word['text'])):word['text']='وصف'
    before=copy.deepcopy(words)
    assert scannumbers.refine_numeric_words(image,words,no_ocr,ocr._png)==0
    assert words==before


@pytest.mark.parametrize('value', ['00160','-160','+160','1.60','16/0','16%','١٦','٢٥'])
def test_formats_and_arabic_readings_are_not_reinterpreted(value):
    image,primary=private_cell();words=copy.deepcopy(primary)
    words[25]['text']=value;words[252]['text']='٢٥'
    assert scannumbers.refine_numeric_words(image,words,no_ocr,ocr._png)==0
    assert words[25]['text']==value


def test_strong_and_ambiguous_latin_candidates_stay_unchanged():
    image,primary=private_cell();primary=copy.deepcopy(primary)
    primary[25]['conf']='95';primary[252]['conf']='95'
    before=copy.deepcopy(primary)
    assert scannumbers.refine_numeric_words(image,primary,no_ocr,ocr._png)==0
    assert primary==before
    primary[25]['conf']='95';primary[252]['conf']='54'
    before=copy.deepcopy(primary)
    blank=Image.new('RGB',image.size,'white')
    assert scannumbers.refine_numeric_words(blank,primary,no_ocr,ocr._png)==0
    assert primary==before
