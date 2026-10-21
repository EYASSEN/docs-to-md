"""Regression gates for the defects reproduced in the revision 47 review."""
import csv, io, subprocess
from pathlib import Path
from unittest.mock import patch
import fitz
import pytest
from PIL import Image
from foldertomd import ocr, pdf
from foldertomd.ocrclean import prefer_cleaned

ROOT=Path(__file__).resolve().parents[1]

def rows(amount, confidence):
    terms=['The','total','amount','due','for','the','contract','is',amount,'USD']
    return [dict(level='5',page_num='1',block_num='1',par_num='1',line_num='1',word_num=str(i+1),
                 left=str(20+i*40),top='20',width='35',height='15',conf=str(confidence),text=t)
            for i,t in enumerate(terms)]

@pytest.mark.parametrize('base,alternate', [('100.00','1000.00'),('00123','123'),('-100','100'),
                                           ('1.50','150'),('100',''),('','100')])
def test_cleanup_cannot_change_numbers(base,alternate):
    assert not prefer_cleaned(rows(base,40),rows(alternate,55))

def test_cleanup_accepts_improvement_with_equivalent_digit_scripts():
    assert prefer_cleaned(rows('١٠٠٫٠٠',40),rows('100.00',55))

def test_transcribe_retains_original_numeric_reading_and_warns():
    base=rows('100.00',40); cleaned=rows('1000.00',55); calls=[]
    def result(words,code=0):
        buf=io.StringIO(); writer=csv.DictWriter(buf,fieldnames=list(base[0]),delimiter='\t')
        writer.writeheader(); writer.writerows(words)
        return subprocess.CompletedProcess([],code,buf.getvalue().encode(),b'')
    def run(root,data,args,work,threads):
        calls.append(args)
        if 'osd' in args: return result([],1)
        if '11' in args: return result([])
        return result(base if sum('3' in a for a in calls)==1 else cleaned)
    data=ocr._png(Image.new('RGB',(500,500),'white'))
    with patch.object(ocr,'preflight',return_value=ROOT), patch.object(ocr,'_tesseract',side_effect=run), \
         patch.object(ocr,'remove_color_stamps',side_effect=lambda im:(im,False)), \
         patch.object(ocr,'best_ruled_grid',side_effect=lambda im:(im,None)), \
         patch.object(ocr,'remove_pixel_separators'), patch.object(ocr,'refine_latin_tables'), \
         patch.object(ocr,'reread_numeric_columns'):
        value,warnings,_=ocr.transcribe(data,{'language':'eng','quality':'standard'},ROOT,'Synthetic page',rendered=True)
    assert '100.00' in str(value) and '1000.00' not in str(value)
    assert any('disagrees on numbers' in w for w in warnings)

def test_native_arabic_preserves_four_valid_final_marks():
    text='رأيت مدرسةً جميلةً وحديقةً واسعةً'
    assert pdf._native_fix(text,False)==text

def test_reviewed_prime_table_columns_and_punctuation():
    with fitz.open(ROOT/'tests/fixtures/update48/prime-page8.pdf') as doc:
        page=doc[0]; table=pdf._native_tables(page)[-1]
        assert (table.row_count,table.col_count)==(2,7)
        values=pdf._table_rows(table,page.get_text('rawdict')['blocks'],[])
        assert 'Last Date' in values[0][4]
        assert values[1][4]=='14/09/2023'
        assert values[1][5]=='30/10/2023'
        assert values[1][6]=='180 Days'
        assert values[1][0]=='T/2460879/\n2023'
        assert 'R.O. 2500/-' in values[1][3]
        assert '(Plus 5%' in values[1][3]

def test_pale_filled_rules_without_matching_background_are_retained():
    with fitz.open() as doc:
        page=doc.new_page()
        for x in (50,150,250):
            page.draw_rect(fitz.Rect(x,50,x+0.5,150),color=None,fill=(0.9,0.9,0.9))
        for y in (50,100,150):
            page.draw_rect(fitz.Rect(50,y,250,y+0.5),color=None,fill=(0.9,0.9,0.9))
        for x,y,value in ((60,70,'A'),(160,70,'B'),(60,120,'1'),(160,120,'2')):
            page.insert_text((x,y),value)
        table=pdf._native_tables(page)[0]
        assert (table.row_count,table.col_count)==(2,2)
