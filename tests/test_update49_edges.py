from PIL import Image,ImageDraw
from foldertomd.scanlayout import cell_content

def test_broken_edge_rule_does_not_expand_quantity_crop():
    im=Image.new('RGB',(80,1000),'white'); draw=ImageDraw.Draw(im)
    for y in (0,200,400,600,800): draw.rectangle((0,y,1,y+70),fill='black')
    draw.rectangle((35,930,39,950),fill='black'); draw.rectangle((45,947,48,950),fill='black')
    crop=cell_content(im)
    assert crop.size==(14,21)
    assert crop.getpixel((11,19))==(0,0,0)  # small zero-sized dot is retained

def test_isolated_edge_stroke_is_retained_as_text():
    im=Image.new('RGB',(80,200),'white'); ImageDraw.Draw(im).rectangle((0,80,2,140),fill='black')
    crop=cell_content(im)
    assert crop.size==(3,61)
