# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Update35: short scan tables and separators misread as high-confidence digits."""
import csv, io, sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from foldertomd import ocr as O, ocrtable as T


def word(value,x,y,width=20,height=20,conf=97):
    return dict(text=value,left=str(x),top=str(y),width=str(width),height=str(height),
        conf=str(conf),block_num='1',par_num='1',line_num=str(y))


def tsv(group):
    out=io.StringIO();writer=csv.DictWriter(out,list(word('x',0,0)),delimiter='\t')
    writer.writeheader();writer.writerows(group)
    return SimpleNamespace(returncode=0,stdout=out.getvalue().encode(),stderr=b'')


def colon_image():
    im=Image.new('RGB',(500,200),'white');draw=ImageDraw.Draw(im);rows=[]
    for y in (25,75,125):
        draw.rectangle((203,y+3,207,y+7),fill='black');draw.rectangle((203,y+17,207,y+21),fill='black')
        rows.extend([word('6',100,y,height=25),word('5',203,y+3,width=5,height=19,conf=99),word('3',300,y,height=25)])
    return im,rows


def test_colon_pixels_come_from_the_scan_not_the_guessed_digit():
    im,rows=colon_image();warnings=[]
    T.remove_pixel_separators(rows,im,warnings,'Test')
    assert [w['text'] for w in rows if w['left']=='203']==['','','']
    assert all(w['text'] for w in rows if w['left']!='203') and warnings


def test_connected_digit_is_never_deleted_as_a_colon():
    im,rows=colon_image();draw=ImageDraw.Draw(im)
    for y in (25,75,125): draw.rectangle((203,y+3,207,y+21),fill='black')
    warnings=[];T.remove_pixel_separators(rows,im,warnings,'Test')
    assert all(w['text']=='5' for w in rows if w['left']=='203') and not warnings


def test_colon_in_a_sentence_is_retained():
    im,rows=colon_image()
    for w in rows:
        if w['left']=='100': w['text']='Label'
    T.remove_pixel_separators(rows,im,[],'Test')
    assert all(w['text']=='5' for w in rows if w['left']=='203')


@pytest.mark.parametrize('first,second,score,expected',[
    ('3','3',96,'3'),('3','5',96,'5'),('3','3',50,'5'),('5','5',96,'5')])
def test_three_row_table_reread_handles_confident_wrong_digits(first,second,score,expected):
    rows=[]
    for y,label in zip((30,80,130),('Alpha','Beta','Gamma')):
        rows.extend([word(label,30,y,width=70),word('5',330,y)])
    warnings=[];calls=[]
    def read(data,args):
        calls.append(args)
        if args[args.index('--psm')+1]=='6': return tsv([])
        with Image.open(io.BytesIO(data)) as crop: binary=crop.mode=='L'
        return tsv([word(second if binary else first,26,26,conf=score)])
    T.refine_latin_tables(rows,Image.new('RGB',(500,200),'white'),read,O._png,warnings,'Test','ara+eng',O._table_rows)
    assert [w['text'] for w in rows if w['text'] in ('3','5')]==[expected]*3
    assert [w['text'] for w in rows if w['text'] in ('Alpha','Beta','Gamma')]==['Alpha','Beta','Gamma']
    assert all(args[args.index('-l')+1]=='eng' for args in calls)
    if first!=second: assert any('disagreed' in x for x in warnings)


@pytest.mark.parametrize('old,new',[
    ('00123','123'),('12.5','125'),('-42','42'),('12.5%','12.5'),('1,234','1234')])
def test_cell_reread_preserves_leading_zeroes_decimal_sign_and_percent(old,new):
    assert not T._format_preserved(old,new)


def test_integer_recovery_is_not_blocked_by_three_rows_or_digit_script():
    assert T._format_preserved('over 600 and up to 0','over 600 and up to 900')
    assert T._format_preserved('5','3')


def test_english_reread_is_not_applied_to_arabic_tables():
    rows=[]
    for y,label in zip((30,80,130),('أول','ثاني','ثالث')): rows.extend([word(label,30,y,width=70),word('5',330,y)])
    def unexpected(*a): raise AssertionError('Arabic table sent to English OCR')
    T.refine_latin_tables(rows,Image.new('RGB',(500,200),'white'),unexpected,O._png,[],'Test','ara+eng',O._table_rows)
    assert [w['text'] for w in rows if w['text']=='5']==['5']*3


def test_high_quality_table_rereads_keep_the_best_english_model():
    rows=[]
    for y,label in zip((30,80,130),('Alpha','Beta','Gamma')): rows.extend([word(label,30,y,width=70),word('5',330,y)])
    calls=[]
    def read(data,args):
        calls.append(args)
        return tsv([] if args[args.index('--psm')+1]=='6' else [word('3',26,26,conf=96)])
    T.refine_latin_tables(rows,Image.new('RGB',(500,200),'white'),read,O._png,[],'Test','ara_best+eng_best',O._table_rows)
    assert all(args[args.index('-l')+1]=='eng_best' for args in calls)
    assert sum(w['text']=='3' for w in rows)==3


def test_number_in_a_description_needs_context_when_crop_confidence_drops():
    first=[word('over',0,0,conf=97),word('600',50,0,conf=96),word('and',100,0,conf=96),word('900',150,0,conf=64)]
    second=[word('over',0,0,conf=96),word('600',50,0,conf=87),word('and',100,0,conf=96),word('900',150,0,conf=86)]
    context=[word('over',0,0,conf=97),word('600',50,0,conf=96),word('and',100,0,conf=96),word('900',150,0,conf=92)]
    assert T._confirmed(first,second,context)
    assert not T._confirmed(first,second,[])
    context[-1]['text']='0'
    assert not T._confirmed(first,second,context)
