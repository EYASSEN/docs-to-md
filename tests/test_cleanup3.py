from PIL import Image, ImageDraw
import random
from foldertomd.ocrclean import clean_scan, needs_cleanup, prefer_cleaned
from foldertomd.engine import timeout_message

def row(text,conf): return {'text':text,'conf':str(conf)}

def test_clean_scan_removes_specks_keeps_text():
    random.seed(1)
    im=Image.new('RGB',(800,600),'white'); d=ImageDraw.Draw(im)
    d.rectangle((100,200,700,260),fill='black')
    for _ in range(150):
        x,y=random.randrange(800),random.randrange(600)
        if not (90<x<710 and 190<y<270): d.point((x,y),fill='black')
    out=clean_scan(im).convert('L')
    assert out.getpixel((400,230))==0                       # real block kept
    dark=sum(1 for x in range(800) for y in range(600) if out.getpixel((x,y))<128 and not (90<x<710 and 190<y<270))
    assert dark<10                                          # isolated specks gone

def test_prefer_cleaned_rules():
    assert prefer_cleaned([],[row('a',60)]*6)
    assert not prefer_cleaned([],[row('a',20)]*6)            # junk-level confidence
    assert not prefer_cleaned([row('a',90)]*30,[row('a',90)]*30)
    assert prefer_cleaned([row('a',40)]*10,[row('a',55)]*10)
    assert not needs_cleanup([row('a',90)]*30) and needs_cleanup([row('a',90)]*3)

def test_timeout_message_gives_pages_and_limit():
    m=timeout_message(3600,767/969,969)
    assert '767' in m and '969' in m and 'seconds' in m
    assert '5400' in m or '6000' in m or '4800' in m
    assert 'No partial output' in timeout_message(10,0,1)
