# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
import json,os,shutil,sys,threading,time,zipfile
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from foldertomd.paths import output_path,prepare_output,marker,OutputLock,sha256
from foldertomd.engine import run_job
from foldertomd.dispatch import extract
from foldertomd.runtime import JobProcess,resources

def test_mapping_and_conflict(tmp_path):
    source=tmp_path/'Tender';source.mkdir()
    assert output_path(source)==source/'Tender_md'
    (source/'Tender_md').mkdir()
    with pytest.raises(RuntimeError,match='conflict'):prepare_output(source)

@pytest.mark.parametrize('full_page',[True,False])
def test_pdf_invisible_arabic_ocr_layer(tmp_path,full_page):
    import pymupdf as fitz
    from make_fixtures import make,hidden_ocr_pdf,HIDDEN_SENTINEL,HIDDEN_ARABIC
    corpus=make(tmp_path/'corpus');source=corpus/'hidden-ocr.pdf'
    hidden_ocr_pdf(source,(corpus/'scan.png').read_bytes(),full_page)
    with fitz.open(source) as doc:
        assert HIDDEN_SENTINEL in doc[0].get_text()
        assert any(span['type']==3 for span in doc[0].get_texttrace())
    work=tmp_path/'work';work.mkdir()
    extract({'source':str(source),'source_root':str(corpus),'relative':source.name,
             'work':str(work),'settings':{'language':'ara+eng','ocr':'auto'},'asset_link':'assets'})
    md=(work/'result.md').read_text(encoding='utf-8')
    response=json.loads((work/'response.json').read_text(encoding='utf-8'))
    assert response['status']=='partial',response
    assert 'مرحبا بالعالم' in md,md
    assert 'Invoice number 4826' in md
    assert HIDDEN_SENTINEL not in md
    assert HIDDEN_ARABIC not in md
    if not full_page:assert md.count('VISIBLE HEADER 6721')==1

def test_arabic_presentation_forms():
    from foldertomd.pdf import _fix_presentation_forms
    assert _fix_presentation_forms('\ufee3\ufeae\ufea3\ufe92\ufe8e')=='مرحبا'
    assert _fix_presentation_forms('\ufefb ① ABC')=='لا ① ABC'

@pytest.mark.parametrize('name',['control-text','control-block','rotated-image'])
def test_pdf_broken_text_and_rotation(tmp_path,name):
    import pymupdf as fitz
    from make_fixtures import broken_text_pdf,rotated_image_pdf
    from foldertomd.pdf import _unusable_text
    source=tmp_path/(name+'.pdf')
    if name=='rotated-image':rotated_image_pdf(source)
    else:broken_text_pdf(source,mixed=name=='control-block')
    with fitz.open(source) as doc:
        page=doc[0]
        if name.startswith('control'):
            assert any(ord(c)<32 and c not in '\n\r\t' for c in page.get_text())
            assert not page.get_images()  # genuinely vector text, not a disguised scan
            assert _unusable_text(page)==(name=='control-text')
        else:
            assert page.rotation==90
            assert (fitz.Rect(page.get_text('dict')['blocks'][0]['bbox']) & page.rect).is_empty
    work=tmp_path/'work';work.mkdir()
    extract({'source':str(source),'relative':source.name,'work':str(work),
             'settings':{'language':'ara+eng','ocr':'auto'},'asset_link':'assets'})
    md=(work/'result.md').read_text(encoding='utf-8')
    response=json.loads((work/'response.json').read_text(encoding='utf-8'))
    assert response['status']=='partial',response
    assert not any('extraction failed' in warning for warning in response['warnings']),response
    assert '\x01' not in md
    assert ('ROTATED IMAGE TEXT 7392' if name=='rotated-image' else 'RECOVERED FONT TEXT 4826') in md,md
    if name.startswith('control'):assert 'Annotation retained 7381' in md
    if name=='control-block':assert md.count('Readable native paragraph')==12

def test_pdf_garbled_with_ocr_off(tmp_path):
    from make_fixtures import broken_text_pdf
    source=tmp_path/'broken.pdf';broken_text_pdf(source)
    work=tmp_path/'work';work.mkdir()
    extract({'source':str(source),'relative':source.name,'work':str(work),
             'settings':{'language':'ara+eng','ocr':'off'},'asset_link':'assets'})
    md=(work/'result.md').read_text(encoding='utf-8')
    response=json.loads((work/'response.json').read_text(encoding='utf-8'))
    assert '\x01' not in md and '![Page 1]' in md
    assert any('OCR is disabled' in warning for warning in response['warnings'])

def test_pdf_text_quality():
    from foldertomd.pdf import _garbled
    assert _garbled('\x01\x02\x03 ¨¾¦')
    assert not _garbled('Français résumé déjà été. العربية 123 °±×÷©®µ·')

def test_lock(tmp_path):
    with OutputLock(tmp_path):
        with pytest.raises(RuntimeError,match='already'): 
            with OutputLock(tmp_path):pass

def test_values_only(tmp_path):
    from make_fixtures import make
    corpus=make(tmp_path/'corpus');work=tmp_path/'work';work.mkdir()
    extract({'source':str(corpus/'same.xlsx'),'source_root':str(corpus),'relative':'same.xlsx','work':str(work),'settings':{'language':'ara+eng','ocr':'off'},'asset_link':'assets'})
    result=json.loads((work/'response.json').read_text());assert result['status']=='partial',result
    md=(work/'result.md').read_text(encoding='utf-8')
    for expected in ['00123','42','Saved value unavailable','$1,234.50','12.5%','2026-09-22','00007','Hidden saved value','Very hidden saved value','Far sparse value','colspan="3"','=literal text','#DIV/0!']:
        assert expected in md,expected
    for forbidden in ['SUM(40,2)','SUM(500,600)','=1/0','VBA_SENTINEL']:assert forbidden not in md
    assert len(md)<10000

def test_job_state(tmp_path):
    source=tmp_path/'Tender';source.mkdir();(source/'nested'/'empty').mkdir(parents=True);(source/'legitimate_md').mkdir();(source/'legitimate_md'/'a.txt').write_text('one')
    note=source/'notes.md';note.write_bytes(b'# unchanged\r\n');(source/'bad.bin').write_bytes(b'x')
    before=sha256(note);a=run_job(source,{'ocr':'off'});root=Path(a['output']);m=json.loads(Path(a['manifest']).read_text())
    assert (root/'nested'/'empty').is_dir();assert (root/'legitimate_md'/'a.txt.md').exists()
    assert (root/'notes.md.md').read_bytes()==note.read_bytes();assert sha256(note)==before
    assert m['files']['bad.bin']['status']=='unsupported'
    b=run_job(source,{'ocr':'off'});assert b['summary']['unchanged']==2
    note.write_text('changed');c=run_job(source,{'ocr':'off'});assert c['summary']['converted']==1
    (root/'notes.md.md').write_text('manual edit');note.write_text('changed again')
    d=run_job(source,{'ocr':'off'});assert d['summary']['failed']==1;assert (root/'notes.md.md').read_text()=='manual edit'
    m=json.loads(Path(d['manifest']).read_text());assert m['files']['notes.md']['stale']
    note.unlink();e=run_job(source,{'ocr':'off'});assert e['summary']['obsolete']==1
    parent=run_job(tmp_path,{'ocr':'off'});pm=json.loads(Path(parent['manifest']).read_text());assert not any('Tender_md/' in k and not k.endswith('/') for k in pm['files'])

def test_timeout_and_recovery(tmp_path):
    (tmp_path/'file.txt').write_text('recoverable content')
    a=run_job(tmp_path,{'ocr':'off','timeout':.05});assert a['summary']['failed']==1
    b=run_job(tmp_path,{'ocr':'off'});assert b['summary']['converted']==1

def test_cancel_and_resume(tmp_path):
    for i in range(6):(tmp_path/f'{i}.txt').write_text('Contents '+str(i))
    cancel=threading.Event()
    def notify(e):
        if e.get('completed',0)>=1:cancel.set()
    a=run_job(tmp_path,{'ocr':'off'},cancel,notify);assert a['summary']['converted']==1;assert a['summary']['cancelled']==5
    b=run_job(tmp_path,{'ocr':'off'});assert b['summary']['unchanged']==1;assert b['summary']['converted']==5

def test_failed_replace_retains_output(tmp_path,monkeypatch):
    source=tmp_path/'source';source.mkdir();f=source/'a.txt';f.write_text('original');a=run_job(source,{'ocr':'off'});out=Path(a['output'])/'a.txt.md';old=out.read_bytes();f.write_text('new contents')
    real=os.replace
    def denied(src,dst):
        if Path(dst)==out:raise PermissionError('fixture replacement denied')
        return real(src,dst)
    monkeypatch.setattr(os,'replace',denied)
    b=run_job(source,{'ocr':'off'});assert b['summary']['failed']==1;assert out.read_bytes()==old
    manifest=json.loads(Path(b['manifest']).read_text());assert manifest['files']['a.txt']['stale']

def test_child_tree_termination(tmp_path):
    child=tmp_path/'child.py';child.write_text('import subprocess,sys,time\np=subprocess.Popen([sys.executable,"-c","import time;time.sleep(120)"])\nopen(sys.argv[1],"w").write(str(p.pid))\ntime.sleep(120)\n')
    pidfile=tmp_path/'pid';job=JobProcess([sys.executable,str(child),str(pidfile)])
    try:
        for _ in range(100):
            if pidfile.exists():break
            time.sleep(.05)
        import psutil
        pid=int(pidfile.read_text());assert psutil.pid_exists(pid);job.stop();job.process.wait(timeout=10)
        for _ in range(100):
            if not psutil.pid_exists(pid):break
            time.sleep(.05)
        assert not psutil.pid_exists(pid)
    finally:job.close()

def test_locked_input_is_accountable(tmp_path):
    import ctypes
    from ctypes import wintypes as W
    a=tmp_path/'locked.txt';a.write_text('locked content');(tmp_path/'readable.txt').write_text('readable')
    k=ctypes.WinDLL('kernel32',use_last_error=True);k.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,ctypes.c_void_p,W.DWORD,W.DWORD,W.HANDLE];k.CreateFileW.restype=W.HANDLE;k.CloseHandle.argtypes=[W.HANDLE]
    h=k.CreateFileW(str(a),0x80000000,0,None,3,0,None)
    assert h!=ctypes.c_void_p(-1).value
    try:
        result=run_job(tmp_path,{'ocr':'off'});assert result['summary']['failed']==1;assert result['summary']['converted']==1
    finally:k.CloseHandle(h)

def test_cancel_during_workbook_and_ocr(tmp_path):
    import xlsxwriter
    from PIL import Image,ImageDraw,ImageFont
    source=tmp_path/'source';source.mkdir();(source/'0-complete.txt').write_text('Keep this completed file')
    workbook=xlsxwriter.Workbook(source/'1-large.xlsx',{'constant_memory':True});s=workbook.add_worksheet()
    for r in range(70000):s.write_row(r,0,[r,'row',r+1])
    workbook.close()
    cancel=threading.Event()
    def cancel_sheet(e):
        if e.get('stage','').startswith('Reading worksheet'):cancel.set()
    first=run_job(source,{'ocr':'off'},cancel,cancel_sheet);assert first['summary']['cancelled']==1;assert first['summary']['converted']==1
    assert not (Path(first['output'])/'1-large.xlsx.md').exists()
    second=run_job(source,{'ocr':'off'});assert second['summary']['unchanged']==1;assert second['summary']['converted']==1
    image=Image.new('RGB',(2000,2400),'white');draw=ImageDraw.Draw(image);font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',48)
    for i in range(25):draw.text((70,50+i*80),'Cancellation OCR test 123456789',font=font,fill='black')
    image.save(source/'2-image.png');cancel.clear()
    def cancel_ocr(e):
        if e.get('stage','').startswith('Reading image text'):cancel.set()
    third=run_job(source,{'ocr':'auto'},cancel,cancel_ocr);assert third['summary']['cancelled']==1
    assert not (Path(third['output'])/'2-image.png.md').exists()
    fourth=run_job(source,{'ocr':'auto'});assert fourth['summary']['unchanged']==2;assert fourth['summary']['partial']==1

def test_settings_and_changed_during_read(tmp_path,monkeypatch):
    import foldertomd.engine as engine
    f=tmp_path/'test.txt';f.write_text('version one');a=run_job(tmp_path,{'ocr':'off'})
    b=run_job(tmp_path,{'ocr':'off','language':'eng'});assert b['summary']['converted']==1
    f.write_text('version two');real=engine.sha256;calls=0
    def changed(path):
        nonlocal calls
        if Path(path)==f:
            calls+=1
            if calls==2:f.write_text('changed while being read')
        return real(path)
    monkeypatch.setattr(engine,'sha256',changed)
    c=run_job(tmp_path,{'ocr':'off','language':'eng'});assert c['summary']['failed']==1
    assert 'version one' in (Path(a['output'])/'test.txt.md').read_text()

def test_reserved_namespace_conflict(tmp_path):
    root,meta=prepare_output(tmp_path);(tmp_path/meta.name).mkdir()
    with pytest.raises(RuntimeError,match='reserved'):run_job(tmp_path,{'ocr':'off'})

def test_offline_legacy_permission_gate(tmp_path):
    from foldertomd.context import Context
    from foldertomd.legacy import events
    source=tmp_path/'input.doc';source.write_bytes(b'not parsed by this test');work=tmp_path/'work';work.mkdir()
    ctx=Context({'source':str(source),'work':str(work),'relative':'input.doc','settings':{'ocr':'off'},'asset_link':'assets'})
    try:
        result=list(events(ctx,'network-test'));assert result[0]['text']=='Network permission denied before parsing'
        assert 'SocketPermission' not in (work/'legacy'/'offline.policy').read_text()
    finally:ctx.close()
