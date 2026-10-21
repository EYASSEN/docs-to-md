# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Update34: numeric selection, table geometry, orientation and truthful completion."""
import io, json, sys, threading
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import pytest
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from foldertomd import ocr as O, ocrselect as S, progress as P
from foldertomd.context import Context


def word(value,x=10,y=10,conf=90,width=35,height=20,block='1',line='1'):
    return dict(text=value,left=str(x),top=str(y),width=str(width),height=str(height),
                conf=str(conf),block_num=block,par_num='1',line_num=line)


@pytest.mark.parametrize('old,new',[
    ('١٨٢ / ٢٠١٨','182 / 2018'),('٠٠١٢٣','00123'),('١٢٫٥٪','12.5%'),
    ('−٤٢','-42'),('١٬٢٣٤٫٥٠','1,234.50'),('4826 25 120.50','4826 25 120.50')])
def test_number_tokens_normalize_script_without_changing_value(old,new):
    assert S.number_tokens(old)==S.number_tokens(new)


@pytest.mark.parametrize('old,new',[
    ('00123','123'),('182','187'),('2018','٢٠١٦'),('120.50','12050'),
    ('12.5%','12.5'),('42 25','25 42'),('12',''),('1.5','15')])
def test_arabic_alternate_must_preserve_every_number(old,new):
    accepted,reason=S.prefer_arabic([word('مرحبا '+old,conf=60)],[word('مرحبا بالعالم '+new,conf=99)])
    assert not accepted and reason=='numbers'


def test_arabic_alternate_cannot_win_with_lower_confidence():
    assert S.prefer_arabic([word('مرحبا بالعالم',conf=95)],[word('مرحبا بالعالم',conf=70)])==(False,'confidence')
    assert S.prefer_arabic([word('Ls ys بالعالم',conf=70)],[word('مرحبا بالعالم',conf=80)])==(True,None)


def test_accepted_arabic_line_keeps_full_bbox_and_new_confidence():
    rows=[word('مرحبا',10,10,70),word('بالعالم',80,12,70,width=60)]
    S.collapse_line(rows,[word('مرحبا بالعالم',conf=95)])
    assert rows[0]['text']=='مرحبا بالعالم' and rows[1]['text']==''
    assert S.box(rows[0])==(10,10,140,32) and float(rows[0]['conf'])==95


@pytest.mark.parametrize('angle,conf,code,expected',[
    (180,0.1,0,0),(90,14.99,0,0),(90,15,0,90),(270,30,0,270),
    (180,40,1,0),(45,40,0,0),(0,30,0,0)])
def test_rotation_needs_valid_engine_result_and_orientation_confidence(angle,conf,code,expected):
    result=SimpleNamespace(returncode=code,stdout=f'Rotate: {angle}\nOrientation confidence: {conf}\n'.encode())
    assert S.orientation_angle(result)[0]==expected


def test_rotation_without_confidence_is_not_applied():
    assert S.orientation_angle(SimpleNamespace(returncode=0,stdout=b'Rotate: 180\n'))[0]==0


@pytest.mark.parametrize('better,expected',[(False,0),(True,90)])
def test_low_confidence_rotation_is_verified_by_independent_ocr(better,expected):
    import csv
    def result(ws):
        stream=io.StringIO();writer=csv.DictWriter(stream,list(word('x')),delimiter='\t')
        writer.writeheader();writer.writerows(ws)
        return SimpleNamespace(returncode=0,stdout=stream.getvalue().encode())
    reads=iter([result([word('upright',conf=20 if better else 95)]*6),
                result([word('rotated',conf=95 if better else 40)]*12)])
    osd=SimpleNamespace(returncode=0,stdout=b'Rotate: 90\nOrientation confidence: 2.0\n')
    angle,conf,verified=S.verified_orientation(Image.new('RGB',(100,200),'white'),osd,lambda *a:next(reads),O._png,'eng')
    assert angle==expected and verified==better


def test_sparse_read_can_recover_ten_without_duplicate_or_silent_change():
    rows=[word('6',100,10,78,width=13)];warnings=[]
    S.merge_sparse(rows,[word('10',87,10,96,width=26)],warnings,'Test')
    assert len(rows)==1 and rows[0]['text']=='10' and warnings


def test_sparse_pass_cannot_replace_a_strong_existing_number():
    rows=[word('4826',100,10,96,width=60)];warnings=[]
    S.merge_sparse(rows,[word('4828',100,10,99,width=60)],warnings,'Test')
    assert rows[0]['text']=='4826' and not warnings


def test_sparse_line_overlapping_primary_is_not_duplicated():
    rows=[word('Invoice',10,10,96,width=60),word('4826',100,10,96,width=60)];warnings=[]
    extra=[word('Invoice',10,10,96,width=60),word('4826',100,10,96,width=60)]
    S.merge_sparse(rows,extra,warnings,'Test')
    assert len(rows)==2


def test_two_column_numeric_table_keeps_values_attached():
    ws=[]
    for n,(a,b) in enumerate([('250','10'),('300','8'),('350','7'),('400','7')]):
        ws += [word(a,10,40*n),word(b,300,40*n)]
    rows,used=O._table_rows(ws,'eng')
    assert [cells for _,cells in rows]==[['250','10'],['300','8'],['350','7'],['400','7']]
    assert used==set(map(id,ws))


def test_two_prose_columns_are_not_guessed_to_be_a_table():
    ws=[]
    for n in range(4): ws += [word('paragraph',10,40*n),word('text',300,40*n)]
    assert O._table_rows(ws,'eng')==([],set())


def test_a_thin_misread_colon_does_not_create_a_numeric_column():
    ws=[]
    for n,(a,b,delimiter,c) in enumerate([('600','6','5','3'),('900','4',':','2'),('1200','3',':','1.5')]):
        ws += [word(a,10,40*n),word(b,300,40*n),word(delimiter,420,40*n,54,width=4),word(c,540,40*n)]
    rows,used=O._table_rows(ws,'eng')
    assert [cells for _,cells in rows]==[['600','6','3'],['900','4','2'],['1200','3','1.5']]
    assert used==set(map(id,ws))


def test_legitimate_five_column_is_not_removed_without_delimiter_evidence():
    ws=[]
    for n in range(3): ws += [word('600',10,40*n),word('6',300,40*n),word('5',420,40*n,54,width=4),word('3',540,40*n)]
    assert all(cells==['600','6','5','3'] for _,cells in O._table_rows(ws,'eng')[0])


def test_learning_and_page_start_do_not_claim_completed_pages():
    f=P.FileProgress()
    assert f.update('Sample page',40,40)==0
    assert f.update('Line',100,100)==0
    assert f.update('Page',1,640,completed=0)==0
    assert f.update('Page',4,640,completed=3)==3/640
    assert f.update('Page',640,640,completed=639)==639/640
    assert f.update('Page',640,640,completed=640)==1


def test_context_publishes_completed_units_after_processing(tmp_path):
    ctx=Context(dict(source=str(tmp_path/'a.pdf'),work=str(tmp_path),settings={},relative='a.pdf',asset_link='assets'))
    ctx.stage('Reading page',1,2,'Page');ctx.stage('Reading image text')
    assert json.loads((tmp_path/'stage.json').read_text())['unit_completed']==0
    ctx.complete_unit()
    assert json.loads((tmp_path/'stage.json').read_text())['unit_completed']==1
    assert ctx.counts['pages_processed']==1
    ctx.stage('Reading page',2,2,'Page');ctx.complete_unit();ctx.close()
    assert ctx.counts['pages_processed']==2


def test_pdf_page_completion_includes_decoded_early_continue(tmp_path,monkeypatch):
    import pymupdf as fitz
    from foldertomd import pdf as F
    doc=fitz.open();doc.new_page();doc.new_page();source=tmp_path/'a.pdf';doc.save(source)
    monkeypatch.setattr(F,'_decode_legacy_fonts',lambda *a:{0:[('text','DECODED')],1:[('text','SECOND')]})
    ctx=Context(dict(source=str(source),work=str(tmp_path),relative='a.pdf',asset_link='assets',
        settings=dict(language='eng',ocr='off',quality='standard',decode_fonts=True)))
    F.extract_pdf(ctx);ctx.close()
    assert ctx.counts['pages_processed']==2
    assert json.loads((tmp_path/'stage.json').read_text())['unit_completed']==2


def test_worker_counts_all_tiff_frames(tmp_path):
    source=tmp_path/'three.tiff';frames=[Image.new('RGB',(80,90),c) for c in ('red','green','blue')]
    frames[0].save(source,save_all=True,append_images=frames[1:])
    assert P.count_in_process(source) is None and P.estimate_pages(source)==1
    out=tmp_path/'counts.json';P.count_request({'files':[str(source)],'out':str(out)})
    assert json.loads(out.read_text())[str(source)]==3


def test_conversion_signature_tracks_the_actual_source_code(tmp_path,monkeypatch):
    import foldertomd.engine as E
    package=tmp_path/'foldertomd';package.mkdir();(package/'engine.py').write_text('x=1\n')
    monkeypatch.setattr(E,'__file__',str(package/'engine.py'))
    monkeypatch.setattr(E,'resources',lambda:tmp_path/'resources')
    first,data=E.signature({'ocr':'off'})
    assert data['converter_revision']==E.CONVERSION_REVISION and data['code']['kind']=='python-sources'
    (package/'engine.py').write_text('x=2\n')
    assert E.signature({'ocr':'off'})[0]!=first


def test_cancelled_worker_does_not_count_unread_pages_or_remaining_files(tmp_path,monkeypatch):
    import foldertomd.engine as E
    source=tmp_path/'input';source.mkdir()
    for name in ('a.pdf','b.pdf'): (source/name).write_bytes(b'PDF test')
    cancel=threading.Event();events=[]
    monkeypatch.setattr(E,'OutputLock',lambda meta:nullcontext())
    monkeypatch.setattr(E,'short_work_root',lambda meta:tmp_path/'work')
    (tmp_path/'work').mkdir()
    monkeypatch.setattr(E,'count_pages',lambda *a:{'a.pdf':10,'b.pdf':30})
    monkeypatch.setattr(E,'signature',lambda settings:('signature',{}))
    class Worker:
        def __init__(self,*a,**kwargs):
            self.process=self;self.pid=1;self.stopped=False
            Path(kwargs['cwd'],'stage.json').write_text(json.dumps(dict(stage='Reading page',unit='Page',step=3,steps=10,unit_completed=2)))
        def poll(self): return 0 if self.stopped else None
        def stop(self): self.stopped=True
        def close(self): pass
        def wait(self,**k): return 0
    monkeypatch.setattr(E,'JobProcess',Worker)
    monkeypatch.setattr(E.psutil,'Process',lambda pid:SimpleNamespace(is_running=lambda:False,children=lambda **k:[]))
    monkeypatch.setattr(E.time,'sleep',lambda seconds:cancel.set())
    result=E.run_job(source,{'ocr':'off'},cancel,events.append)
    assert result['pages_done']==2 and result['pages_total']==40
    assert result['files_processed']==0 and result['files_total']==2
    assert result['pages_skipped']==0 and result['job_state']=='cancelled'
    assert result['summary']['cancelled']==2
    assert events[-1]['completed']==0 and events[-1]['pages_done']==2
    manifest=json.loads(Path(result['manifest']).read_text())
    assert manifest['finished_at']==result['finished_at']


class Widget:
    def __init__(self): self.values={'text':'','mode':'determinate'}
    def configure(self,**kwargs): self.values.update(kwargs)
    def cget(self,key): return self.values.get(key,'')


def fake_app():
    from foldertomd.gui import App
    app=object.__new__(App)
    app.t={'TEXT':'black','SOFT':'gray','MUTED':'gray','TAGS':{}}
    for name in ('progress','file_progress','files_text','files_count','step_text','percent','status',
                 'tag','timing','completion_text','open_button','report_button'): setattr(app,name,Widget())
    app.pages=None;app.running=True
    app.finish=lambda:setattr(app,'running',False)
    app._bar=lambda bar,value=None,maximum=None:bar.configure(value=value,maximum=maximum)
    app._show_name=lambda name,colour:setattr(app,'name',name)
    app._badge_row=lambda parts:None;app._fit=lambda:None
    app._state=lambda state,colour:setattr(app,'state',(state,colour))
    return app


def test_cancelled_gui_keeps_actual_percentage_and_fixed_timestamp_on_replay():
    app=fake_app()
    event=dict(stage='Finished',completed=0,discovered=8,pages_done=3,pages_total=640,
        result=dict(summary={'cancelled':8},cancelled=True,finished_at='2026-10-02T08:00:00+00:00'))
    app.handle(event)
    assert app.progress.cget('value')==3 and app.progress.cget('maximum')==640
    assert app.files_text.cget('text')=='Page 3 of 640 — 0.5%'
    assert app.files_count.cget('text')=='0 of 8 files'
    assert app.state==('Stopped','FAIL') and app.name=='Conversion stopped'
    before=app.completion_text.cget('text');app.handle(event,replay=True)
    assert before==app.completion_text.cget('text') and '02/10/2026 08:00:00' in before


def test_completed_gui_keeps_percentage_on_the_same_page_line():
    app=fake_app();app.handle(dict(stage='Finished',completed=8,discovered=8,pages_done=640,pages_total=640,
        result=dict(summary={'converted':8},finished_at='2026-10-02T08:00:00+00:00')))
    assert app.files_text.cget('text')=='Page 640 of 640 — 100.0%'
    assert app.files_count.cget('text')=='8 of 8 files' and app.state==('Finished','DONE')


@pytest.mark.skipif(sys.platform!='win32',reason='Bundled Windows Tesseract; real pages are also checked separately on Linux.')
def test_original_two_and_three_column_tables_with_bundled_ocr(tmp_path,monkeypatch):
    from foldertomd.pdf import extract_pdf
    launch=O._tesseract;trace=[]
    def record(root,data,args,work,threads):
        result=launch(root,data,args,work,threads)
        trace.append({'args':args,'returncode':result.returncode,
            'stdout':result.stdout.decode('utf-8','replace'),'stderr':result.stderr.decode('utf-8','replace')})
        return result
    monkeypatch.setattr(O,'_tesseract',record)
    source=ROOT/'tests/fixtures/update34/electro-table-pages.pdf'
    expected=json.loads((source.parent/'ground-truth.json').read_text(encoding='utf-8'))
    ctx=Context(dict(source=str(source),work=str(tmp_path),relative=source.name,asset_link='assets',
        settings=dict(language='ara+eng',ocr='auto',quality='standard',decode_fonts=False)))
    try: extract_pdf(ctx)
    finally:
        ctx.close()
        (tmp_path/'tesseract-trace.json').write_text(json.dumps(trace,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Original-table OCR diagnostics: '+str(tmp_path))
    md=(tmp_path/'result.md').read_text(encoding='utf-8')
    import re
    parts=re.split(r'^## Page \d+\s*$',md,flags=re.M)[1:]
    assert len(parts)==2
    for page,part in zip(expected['pages'],parts):
        rows=[[c.strip() for c in line.split('|')[1:-1]] for line in part.splitlines()
              if line.startswith('|') and not re.fullmatch(r'[|\s:-]+',line)]
        if page['fixture_page']==2: rows=rows[1:]  # the visible header row
        assert rows==page['rows']
