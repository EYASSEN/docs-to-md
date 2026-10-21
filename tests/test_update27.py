# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Original raster preservation under invisible PDF OCR layers."""
import io,sys
from pathlib import Path
import pymupdf as fitz
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from foldertomd import pdf as P,ocr as O
from foldertomd.context import Context

def test_single_stretched_scan_keeps_pixels_and_excludes_hidden_text(tmp_path,monkeypatch):
    im=Image.new('RGB',(800,300),'white');ImageDraw.Draw(im).rectangle((50,50,80,90),fill='black')
    data=io.BytesIO();im.save(data,'PNG')
    source=tmp_path/'source.pdf';doc=fitz.open();page=doc.new_page(width=600,height=700)
    page.insert_image(page.rect,stream=data.getvalue(),keep_proportion=False)
    page.insert_text((50,70),'HIDDEN SENTINEL',render_mode=3);doc.save(source)
    work=tmp_path/'work';work.mkdir();seen=[]
    def recognized(image,ctx,label,**kwargs):
        seen.append(image.copy());return 'READABLE RESULT'
    monkeypatch.setattr(P,'recognize',recognized)
    ctx=Context({'source':str(source),'work':str(work),'asset_link':'assets','relative':'source.pdf',
                 'settings':{'language':'ara+eng','ocr':'auto','quality':'standard','decode_fonts':False}})
    P.extract_pdf(ctx);ctx.close()
    assert len(seen)==1 and seen[0].size==im.size
    assert seen[0].tobytes()==im.tobytes()
    result=(work/'result.md').read_text()
    assert 'READABLE RESULT' in result and 'HIDDEN SENTINEL' not in result

def test_mixed_pass_recovers_a_short_arabic_line(monkeypatch):
    from types import SimpleNamespace
    fields=['level','left','top','width','height','conf','text','block_num','par_num','line_num']
    import csv
    def tsv(words):
        out=io.StringIO();w=csv.DictWriter(out,fields,delimiter='\t');w.writeheader()
        for x in words:w.writerow(x)
        return out.getvalue().encode()
    english={'level':'5','left':'10','top':'10','width':'80','height':'20','conf':'90','text':'Hello','block_num':'1','par_num':'1','line_num':'1'}
    bad={'level':'5','left':'10','top':'50','width':'130','height':'20','conf':'70','text':'Ls ys بالعالم','block_num':'1','par_num':'1','line_num':'2'}
    good={'level':'5','left':'10','top':'50','width':'130','height':'20','conf':'80','text':'مرحبا بالعالم','block_num':'1','par_num':'1','line_num':'2'}
    calls=[]
    def run(data,args):
        calls.append(args)
        return type('R',(),{'returncode':0,'stdout':tsv([english,bad] if '-l' in args and args[args.index('-l')+1]=='ara+eng' else [good]),'stderr':b''})()
    monkeypatch.setattr(O,'preflight',lambda s:None);monkeypatch.setattr(O,'_tesseract',lambda *a:run(a[1],a[2]))
    value,_,_=O.transcribe(O._png(Image.new('RGB',(300,100),'white')),{'language':'ara+eng','quality':'standard'},None,'Synthetic',rendered=True)
    assert 'مرحبا بالعالم' in value and 'Hello' in value
