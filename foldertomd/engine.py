# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import collections, json, os, re, shutil, subprocess, sys, threading, time, uuid
from datetime import datetime
import psutil
from . import __version__
from .paths import atomic_json, sha256, prepare_output, safe_destination, discover, OutputLock, long_path, display_path, short_work_root, copy_into, needs_long_paths
from .runtime import worker_command, resources, child_environment, JobProcess
from .dispatch import SUPPORTED
from .render import cell, url

HOMEPAGE='https://github.com/EYASSEN/docs-to-md'
CONVERSION_REVISION=58
DEFAULTS={'language':'ara+eng','ocr':'auto','timeout':3600,'quality':'standard','decode_fonts':True,'ocr_engine':'onnx'}

def code_fingerprint():
    import hashlib
    if getattr(sys,'frozen',False): return {'kind':'executable','sha256':sha256(Path(sys.executable))}
    sources={p.name:sha256(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
    return {'kind':'python-sources','sha256':hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()}

def signature(settings):
    import hashlib, importlib.metadata
    versions={}
    for name in ('PyMuPDF','Pillow','openpyxl','xlrd','lxml','markdownify','onnxruntime','numpy','pyclipper'):
        try: versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: versions[name]='bundled'
    models={p.name:sha256(p) for p in (resources()/'tesseract'/'tessdata').glob('*.traineddata')}
    from .ocrengine import fingerprint
    models.update(fingerprint())
    lock=resources().parent/'dependencies.lock.json'
    data={'app':__version__,'converter_revision':CONVERSION_REVISION,'code':code_fingerprint(),'settings':settings,'libraries':versions,'models':models,'artifact_lock':sha256(lock) if lock.exists() else 'missing'}
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest(),data

def validate_outputs(root,entry):
    hashes=entry.get('output_hashes',{})
    if not hashes: return False
    try:
        return all(safe_destination(root,rel).is_file() and sha256(root/rel)==digest for rel,digest in hashes.items())
    except OSError: return False

def edited_outputs(root,entry):
    for rel,digest in entry.get('output_hashes',{}).items():
        p=safe_destination(root,rel)
        if p.exists() and (not p.is_file() or sha256(p)!=digest): return True
    return False

_LABELLED=re.compile(r'^((?:Page|Slide|Sheet|Frame)) (\d+)( image)?: (.*)$',re.S)

def _page_ranges(numbers,limit=20):
    numbers=sorted(set(numbers)); spans=[]
    for n in numbers:
        if spans and n==spans[-1][1]+1: spans[-1][1]=n
        else: spans.append([n,n])
    shown=['%d'%a if a==b else '%d\u2013%d'%(a,b) for a,b in spans[:limit]]
    return ', '.join(shown)+(' \u2026 (+%d more groups)'%(len(spans)-limit) if len(spans)>limit else '')

def condense_warnings(warnings):
    """Report only (Cleanup2): the same warning on many pages becomes one line with the page ranges.
    Different wording stays separate; numbers inside a repeated message are shown as #. manifest.json keeps every warning."""
    order=[]; groups={}
    for w in warnings:
        m=_LABELLED.match(w)
        if not m: order.append(w); continue
        unit,number,image,text=m.group(1),int(m.group(2)),m.group(3) or '',m.group(4)
        key=(unit+image,re.sub(r'\d+(?:\.\d+)?','#',text))
        if key not in groups: groups[key]=[]; order.append(key)
        groups[key].append((number,w))
    out=[]
    for item in order:
        if isinstance(item,str): out.append(item); continue
        members=groups[item]
        if len(members)==1: out.append(members[0][1]); continue
        unit,template=item
        out.append(f'{unit}s {_page_ranges([n for n,_ in members])} ({len(members)}): {template}')
    return out

def reports(root,meta,manifest):
    entries=manifest['files']; counts=collections.Counter(e['status'] for e in entries.values())
    manifest['summary']=dict(counts)
    atomic_json(meta/'manifest.json',manifest)
    report=[f'Docs to MD {__version__} by Yassin Abd El Aal — {HOMEPAGE}','','# Conversion report','',f"Version: {__version__}",f"Elapsed: {manifest.get('elapsed_seconds',0):.2f} seconds",'','## Counts','']
    settings=manifest.get('settings',{})
    report[6:6]=[f'Converter revision: {CONVERSION_REVISION}',
                 'Settings: '+json.dumps(settings,ensure_ascii=False,sort_keys=True)]
    report += ['Finished at: '+manifest.get('finished_at','not finished'),
               'Job state: '+manifest.get('job_state','unknown'),
               'Code SHA-256: '+manifest.get('backend_versions',{}).get('code',{}).get('sha256','unavailable'),
               f"Files converted in parallel: up to {manifest.get('parallel_files',1)}",
               f"Completed units: {manifest.get('pages_done',0)} of {manifest.get('pages_total',0)} (PDF pages, image frames, slides, sheets; other formats estimated)",'']
    report += [f'- {k}: {v}' for k,v in sorted(counts.items())]
    report += ['','## Files','','| Source | Status | Details |','| --- | --- | --- |']
    index=['# Converted documents','','Only current, valid conversions are listed. See conversion_report.md for partial, stale, excluded, or failed items.','']
    for rel,e in entries.items():
        report.append('| '+cell(rel)+' | '+e['status']+(' (with warnings)' if e['status']=='unchanged' and e.get('warnings') else '')+(' (retained output stale)' if e.get('stale') else '')+' | '+cell('; '.join(condense_warnings(e.get('warnings',[]))))+' |')
        if e['status'] in ('converted','partial','unchanged') and not e.get('stale'):
            index.append(f"- [{cell(rel)}]({url('../'+e['output'])})"+(' — review warnings' if e.get('warnings') else ''))
    for name,lines in [('conversion_report.md',report),('INDEX.md',index)]:
        tmp=meta/(name+'.tmp'); tmp.write_text('\n'.join(lines)+'\n',encoding='utf-8'); os.replace(tmp,meta/name)

def count_pages(source,files,workroot,cancel,notify):
    """Pages of every file, for the overall progress (Update21). Office packages are read here with the
    standard library; PDF page counts come from one isolated worker (PyMuPDF is never run in this process).
    A file that cannot be counted gets an estimate from its size."""
    from .progress import count_in_process, estimate_pages, load_counts
    pages={}; pdfs=[]
    for rel in files:
        if cancel.is_set(): break
        if Path(rel).suffix.lower() not in SUPPORTED: pages[rel]=0; continue
        n=count_in_process(source/rel)
        if n is None: pdfs.append(rel)
        else: pages[rel]=n
    if pdfs and not cancel.is_set():
        notify({'stage':'Counting pages','discovered':len(files),'completed':0})
        work=workroot/('count-'+uuid.uuid4().hex[:12]); got={}
        try:
            work.mkdir()
            atomic_json(work/'request.json',{'mode':'count','files':[str(source/r) for r in pdfs],'out':str(work/'counts.json')})
            limit=min(300,30+0.5*len(pdfs)); log=(work/'worker.log').open('wb'); worker=None
            try:
                worker=JobProcess(worker_command(work/'request.json'),cwd=str(work),stdout=log,stderr=log,env=child_environment(work))
                began=time.monotonic()
                while worker.process.poll() is None:
                    if cancel.is_set() or time.monotonic()-began>limit: worker.stop(); break
                    time.sleep(.05)
                worker.process.wait(timeout=10)
            finally:
                if worker: worker.close()
                log.close()
            got=load_counts(work/'counts.json')
        except Exception: got={}            # counting is only for the progress bar; never fail a job over it
        finally: shutil.rmtree(work,ignore_errors=True)
        for rel in pdfs: pages[rel]=got.get(str(source/rel)) or estimate_pages(source/rel)
    for rel in files: pages.setdefault(rel,1)
    return pages

def timeout_message(elapsed,fraction,pages):
    """Explain a per-file time-out: how far it got and what limit would probably be enough (Cleanup3)."""
    text=f'Per-file time limit reached after {elapsed/60:.0f} min'
    if pages>1 and fraction>0.01:
        text+=f' with about {fraction*pages:.0f} of {pages} pages done'
        need=elapsed/fraction*1.25; text+=f'. Estimated time needed: about {need/60:.0f} min. Set "Time limit / file" in Options to at least {int(-(-need//600)*600)} seconds and run again'
    else: text+='. Raise "Time limit / file" in Options and run again'
    return text+'; files already converted are skipped. No partial output was written for this file.'

# ---- parallel files (Cleanup23) ------------------------------------------------------------------
# Files used to be converted strictly one after another. A scanned PDF already reads its pages in
# parallel, but a folder of many small files (Word, Excel, text PDFs, single images) kept one core busy
# and the rest of the PC idle. Now several "light" files run at the same time, each worker with a share
# of the cores. A "heavy" file (a PDF of HEAVY_UNITS pages or more, with OCR on) still runs alone with
# the full page-level parallelism it had before, so large scans are never slowed down.
HEAVY_UNITS=15
MAX_PARALLEL_FILES=3
WORKER_MEMORY=1536*1024*1024      # planning figure per worker; a busy OCR worker rarely needs more

def thread_budget():
    """Cores the job may keep busy: the same figure the page-level OCR pool uses (pdf._workers)."""
    return max(1,min(6,(os.cpu_count() or 2)-1))

def parallel_plan(available_memory=None,budget=None):
    """(parallel files, threads per light file). DOCSTOMD_PARALLEL_FILES overrides the file count;
    1 restores the old one-file-at-a-time behaviour exactly."""
    budget=budget or thread_budget()
    forced=os.environ.get('DOCSTOMD_PARALLEL_FILES','').strip()
    if forced.isdigit() and int(forced)>=1: slots=int(forced)
    else:
        slots=max(1,min(MAX_PARALLEL_FILES,budget))
        if available_memory is None:
            try: available_memory=psutil.virtual_memory().available
            except (psutil.Error,OSError): available_memory=None
        if available_memory: slots=max(1,min(slots,int(available_memory//WORKER_MEMORY)))
    return slots,max(1,budget//slots)

def is_heavy(rel,pages,settings):
    return settings.get('ocr')!='off' and Path(rel).suffix.lower()=='.pdf' and pages.get(rel,0)>=HEAVY_UNITS

class _Board:
    """Shared job state. Worker threads change it only under the lock; manifest values are replaced,
    never resized, so a checkpoint write never iterates a dict another thread is changing."""
    def __init__(self,notify,files,pages):
        self.lock=threading.RLock(); self._notify=notify; self.files=files; self.pages=pages
        self.completed=0; self.done_pages=0.0; self.skipped_pages=0
        self.parts={}; self.running=[]; self.shown=None
    def page_info(self):
        return {'pages_done':round(self.done_pages+sum(self.parts.values()),2),'pages_total':sum(self.pages.values()),'pages_skipped':self.skipped_pages}
    def focus(self):
        with self.lock: return self.running[0] if self.running else None
    def emit(self,rel,event):
        """The file panel follows one file (the oldest one still running); events of the others only
        move the overall bar. With one file at a time every event is a focus event, as before."""
        with self.lock:
            base={'discovered':len(self.files),'completed':self.completed,**self.page_info()}
            if len(self.running)>1: base['running']=len(self.running)
            if rel is None or rel==self.focus():
                self.shown=rel; self._notify({**event,**base})
            else:
                self._notify({'stage':event.get('stage',''),'background':True,**base})

def run_job(source,settings=None,cancel=None,notify=lambda x:None):
    source=Path(source).absolute()
    if not source.is_dir(): raise RuntimeError('Select an existing source folder.')
    # Extended-length paths only when some output path would pass the Windows limit (Update14)
    if needs_long_paths(source): source=long_path(source)
    settings={**DEFAULTS,**(settings or {})}; cancel=cancel or threading.Event()
    if settings['language'] not in ('ara','eng','ara+eng'): raise RuntimeError('Unsupported OCR language setting.')
    if settings['ocr'] not in ('auto','off'): raise RuntimeError('Unsupported OCR mode.')
    if settings.get('quality','standard') not in ('quick','standard','high'): raise RuntimeError('Unsupported OCR quality setting.')
    if settings.get('ocr_engine','onnx') not in ('onnx','tesseract'): raise RuntimeError('Unsupported OCR engine setting.')
    if not 0.05<=float(settings['timeout'])<=86400: raise RuntimeError('Per-file limit must be between 0.05 and 86400 seconds.')
    if settings['ocr']!='off':
        from .ocr import preflight
        preflight(settings)
    root,meta=prepare_output(source)
    with OutputLock(meta):
        start=time.monotonic(); sig,versions=signature(settings)
        old={}
        if (meta/'manifest.json').exists():
            try: old=json.loads((meta/'manifest.json').read_text(encoding='utf-8')).get('files',{})
            except (ValueError,OSError): raise RuntimeError('Saved manifest cannot be read. Restore it before reusing this output folder.')
        files,dirs,skipped=discover(source,root,cancel,notify)
        entries={r:{**old.get(r,{}),'source':r,'format':Path(r).suffix.lower(),'status':'pending','warnings':[]} for r in files}
        entries.update({e['source']:e for e in skipped})
        for rel,entry in old.items():
            if rel not in entries and entry.get('output'): entries[rel]={**entry,'status':'obsolete','stale':True,'warnings':['Source is no longer present; old output retained.']}
        manifest={'version':__version__,'settings':settings,'conversion_signature':sig,'backend_versions':versions,'files':entries,'elapsed_seconds':0,'peak_worker_tree_rss_bytes':0,'parallel_files':1}
        for rel in dirs:
            if rel==meta.name or rel.startswith(meta.name+'/'): raise RuntimeError('A source directory conflicts with the reserved output metadata namespace.')
            safe_destination(root,rel).mkdir(parents=True,exist_ok=True)
        atomic_json(meta/'manifest.json',manifest)
        shutil.rmtree(meta/'temporary',ignore_errors=True)   # workspaces from versions before Update14
        workroot=short_work_root(meta)
        # Only application-owned abandoned workspaces, under the locked metadata root.
        for orphan in workroot.iterdir():
            if orphan.is_dir() and orphan.name.startswith(('job-','count-')):
                shutil.rmtree(orphan,ignore_errors=True)
        # Overall progress by pages (Update21): pages of finished files plus the share of the running ones
        from .progress import FileProgress
        pages=count_pages(source,files,workroot,cancel,notify)
        board=_Board(notify,files,pages)
        slots,light_threads=parallel_plan()
        manifest['parallel_files']=slots

        def checkpoint():
            with board.lock:
                manifest['elapsed_seconds']=round(time.monotonic()-start,3)
                # A checkpoint only: if OneDrive still holds the file after the retries, keep converting;
                # the complete manifest in memory is written at the end of the job (Update19).
                try: atomic_json(meta/'manifest.json',manifest)
                except OSError: pass

        def convert(rel,threads):
            """One file, start to finish, in its own thread. `entry` is this thread's private copy;
            it is published to the manifest (under the lock) at the same points as before."""
            previous=old.get(rel,{})
            with board.lock: entry=dict(entries[rel])
            def publish():
                with board.lock: entries[rel]=dict(entry)
            tick=time.monotonic(); src=source/rel; share=FileProgress(); work=None
            board.emit(rel,{'stage':'Checking file','current':rel})
            if src.suffix.lower() not in SUPPORTED:
                entry.update(status='unsupported',warnings=['File extension is outside the supported format scope.'])
                with board.lock:
                    entries[rel]=entry; board.completed+=1; board.done_pages+=pages.get(rel,0); board.skipped_pages+=pages.get(rel,0)
                return
            work=workroot/('job-'+uuid.uuid4().hex[:12]); work.mkdir()
            final=safe_destination(root,rel+'.md')
            try:
                source_hash=sha256(src); entry['source_hash']=source_hash; entry['signature']=sig
                # A pending commit can be recovered from its verified expected hashes after a crash.
                if previous.get('source_hash')==source_hash and previous.get('signature')==sig and previous.get('status') in ('converted','partial','unchanged','committing') and validate_outputs(root,previous):
                    entry={**previous,'status':'unchanged','stale':False}
                    return
                if previous and edited_outputs(root,previous): raise RuntimeError('Generated output or an asset was manually edited. Preserve or move it before converting again; it was not overwritten.')
                if final.exists() and not previous.get('output_hashes'): raise RuntimeError('Output exists without an ownership record; it was not overwritten.')
                generation=uuid.uuid4().hex
                assetrel=meta.name+'/assets/'+generation
                assetlink=os.path.relpath(root/assetrel,final.parent).replace('\\','/')
                # Converters (PyMuPDF, Tesseract, Java) read a copy with a short English name, so no external
                # tool ever sees a long or Arabic path (Update14).
                local=work/('source'+src.suffix.lower()); shutil.copyfile(src,local)
                request={'source':str(local),'original_dir':str(src.parent),'source_root':str(source),'relative':rel,'work':str(work),'settings':settings,'asset_link':assetlink}
                atomic_json(work/'request.json',request)
                env=child_environment(work,threads)
                log=(work/'worker.log').open('wb')
                worker=None
                try:
                    worker=JobProcess(worker_command(work/'request.json'),cwd=str(work),stdout=log,stderr=log,env=env)
                    proc=psutil.Process(worker.process.pid)
                    last_stage=None
                    while worker.process.poll() is None:
                        if cancel.is_set(): worker.stop(); entry.update(status='cancelled',warnings=['Cancelled during conversion.']); break
                        if time.monotonic()-tick>float(settings['timeout']):
                            worker.stop(); entry.update(status='failed',warnings=[timeout_message(time.monotonic()-tick,share.fraction,pages.get(rel,0))],reason='timeout'); break
                        try:
                            rss=sum(p.memory_info().rss for p in [proc]+proc.children(recursive=True) if p.is_running())
                            with board.lock: manifest['peak_worker_tree_rss_bytes']=max(manifest['peak_worker_tree_rss_bytes'],rss)
                        except (psutil.Error,OSError): pass
                        try:
                            info=json.loads((work/'stage.json').read_text(encoding='utf-8'))
                            key=(info['stage'],info.get('step'),info.get('steps'),info.get('unit_completed'))
                            # A file that has just become the followed one is shown at once.
                            if key!=last_stage or (board.shown!=rel and board.focus()==rel):
                                part=share.update(info.get('unit'),info.get('step'),info.get('steps'),info.get('unit_completed'))*pages.get(rel,0)
                                with board.lock: board.parts[rel]=part
                                board.emit(rel,{'stage':info['stage'],'current':rel,
                                                **{k:info[k] for k in ('step','steps','unit','unit_completed') if k in info}}); last_stage=key
                        except (OSError,ValueError): pass
                        time.sleep(.08)
                    worker.process.wait(timeout=10)
                finally:
                    if worker: worker.close()
                    log.close()
                if entry['status'] in ('cancelled','failed'): return
                response=work/'response.json'
                if not response.exists(): raise RuntimeError('Worker exited without a result. No final output was replaced.')
                result=json.loads(response.read_text(encoding='utf-8')); entry.update(result)
                if entry['status']=='failed': return
                if sha256(src)!=source_hash:
                    entry.update(status='failed',warnings=['Source changed during extraction. Previous output retained; rerun to retry.']); return
                final.parent.mkdir(parents=True,exist_ok=True)
                # Check again immediately before commit, so concurrent manual edits are preserved.
                if previous and edited_outputs(root,previous): raise RuntimeError('Output changed during conversion; replacement was cancelled.')
                assets=work/'assets'; asset_files=list(assets.iterdir())
                hashes={rel+'.md':sha256(work/'result.md')}
                if asset_files:
                    dest=safe_destination(root,assetrel); dest.parent.mkdir(parents=True,exist_ok=True)
                    for p in asset_files: hashes[assetrel+'/'+p.name]=sha256(p)
                    copy_into(assets,dest)            # the workspace may be on another drive (Update14)
                entry.update(output=rel+'.md',output_hashes=hashes,stale=False)
                status=entry['status']; entry['status']='committing'; publish()
                with board.lock: atomic_json(meta/'manifest.json',manifest)
                copy_into(work/'result.md',final)
                entry['status']=status
            except Exception as e:
                # Show the real error (Update14); the old generic text hid the cause
                entry.update(status='failed',warnings=[str(e) if isinstance(e,RuntimeError) else f"{type(e).__name__}: {str(e).replace(chr(92)*2+'?'+chr(92)+'UNC'+chr(92),chr(92)*2).replace(chr(92)*2+'?'+chr(92),'')} Could not read or write the file."])
            finally:
                if entry['status'] in ('failed','cancelled') and previous.get('output'):
                    entry.update(output=previous['output'],output_hashes=previous.get('output_hashes',{}),stale=True)
                entry['elapsed_seconds']=round(time.monotonic()-tick,3)
                # Read the final stage even when the worker finished between polls.
                try:
                    info=json.loads((work/'stage.json').read_text(encoding='utf-8'))
                    share.update(info.get('unit'),info.get('step'),info.get('steps'),info.get('unit_completed'))
                except (OSError,ValueError,TypeError): pass
                successful=entry['status'] in ('converted','partial','unchanged')
                fraction=1.0 if successful else share.fraction
                entry['units_processed']=round(fraction*pages.get(rel,0),2)
                with board.lock:
                    entries[rel]=entry; board.parts.pop(rel,None)
                    if entry['status']!='cancelled': board.completed+=1
                    board.done_pages+=fraction*pages.get(rel,0)
                    if entry['status']=='unchanged': board.skipped_pages+=pages.get(rel,0)
                shutil.rmtree(work,ignore_errors=True)
                checkpoint()
                board.emit(rel,{'stage':'File finished','current':rel,'status':entry['status'],'file_fraction':fraction})

        def run(rel,threads,errors):
            try: convert(rel,threads)
            except BaseException as e: errors.append(e)
            finally:
                with board.lock:
                    if rel in board.running: board.running.remove(rel)

        # Scheduler: files start in folder order. A light file takes one slot; a heavy file waits until
        # nothing else runs and then takes the whole PC, exactly as every file did before Cleanup23.
        queue=collections.deque(files); active={}; errors=[]
        while queue or active:
            if cancel.is_set() and queue:
                with board.lock:
                    for rel in queue:
                        entries[rel]={**entries[rel],'status':'cancelled','stale':bool(entries[rel].get('output')),'warnings':['Cancelled before processing.']}
                queue.clear()
            while queue and not errors and not cancel.is_set():
                rel=queue[0]; heavy=slots>1 and is_heavy(rel,pages,settings)
                cost=slots if heavy else 1
                if active and sum(active.values())+cost>slots: break
                queue.popleft()
                threads=None if heavy or slots==1 else light_threads
                with board.lock: board.running.append(rel)
                t=threading.Thread(target=run,args=(rel,threads,errors),name='file-'+uuid.uuid4().hex[:6],daemon=True)
                active[t]=cost; t.start()
            if errors and queue:
                queue.clear()
            for t in [t for t in active if not t.is_alive()]:
                t.join(); del active[t]
            if active: time.sleep(.03)
        if errors: raise errors[0]
        completed=board.completed
        manifest['cancelled']=cancel.is_set()
        manifest['elapsed_seconds']=round(time.monotonic()-start,3)
        manifest.update(board.page_info(),finished_at=datetime.now().astimezone().isoformat(timespec='seconds'),
                        files_processed=completed,files_total=len(files))
        manifest['timed_out']=[r for r,e in entries.items() if e.get('status')=='failed' and e.get('reason')=='timeout']
        manifest['job_state']='cancelled' if manifest['cancelled'] else 'completed_with_errors' if any(e['status']=='failed' for e in entries.values()) else 'completed'
        reports(root,meta,manifest)
        result={'output':display_path(root),'report':display_path(meta/'conversion_report.md'),'manifest':display_path(meta/'manifest.json'),'summary':manifest['summary'],'elapsed_seconds':manifest['elapsed_seconds'],'peak_worker_tree_rss_bytes':manifest['peak_worker_tree_rss_bytes'],
                **{k:manifest[k] for k in ('timed_out','finished_at','cancelled','job_state','pages_done','pages_total','pages_skipped','files_processed','files_total','parallel_files')}}
        notify({'stage':'Finished','completed':completed,'discovered':len(files),'result':result,**board.page_info()})
        return result
