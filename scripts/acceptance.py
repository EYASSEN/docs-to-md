# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run inspectable black-box checks against the source entry or frozen executable."""
from pathlib import Path
import argparse,hashlib,json,os,platform,re,shutil,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tests'));sys.path.insert(0,str(ROOT))
from foldertomd.paths import output_path,marker

def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def source_hashes(source):
    """Hash original inputs, excluding only this corpus's marked output root.

    An ordinary _md folder or an unmarked same-name folder remains an input.
    Do not delete prior results: repeat-run acceptance must exercise their reuse.
    """
    source=Path(source).absolute();output=output_path(source);hashes={}
    for base,directories,files in os.walk(source):
        base=Path(base)
        directories[:]=[name for name in directories
                        if not (base/name==output and marker(base/name) is not None)]
        for name in files:
            path=base/name
            if path.is_file():hashes[path.relative_to(source).as_posix()]=digest(path)
    return hashes

def input_changes(before,after):
    return {'added':sorted(after.keys()-before.keys()),'removed':sorted(before.keys()-after.keys()),
            'changed':sorted(name for name in before.keys()&after.keys() if before[name]!=after[name])}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--exe',type=Path);parser.add_argument('--name',default='packaged');parser.add_argument('--work',type=Path);parser.add_argument('--expected-revision',type=int);args=parser.parse_args()
    work=(args.work or ROOT/'test-work'/('acceptance-'+args.name)).resolve();work.mkdir(parents=True,exist_ok=True)
    from make_fixtures import make
    corpus=make(work/'Tender اختبار',large=True)
    # Binary legacy fixtures produced once using the compatibility path are retained for replay.
    for file in (ROOT/'tests'/'fixtures'/'legacy').glob('*'):
        shutil.copy2(file,corpus/file.name)
    command=[str(args.exe.resolve())] if args.exe else [sys.executable,str(ROOT/'main.py')]
    hashes=source_hashes(corpus)
    env=os.environ.copy();env.update({'PATH':os.environ['SystemRoot']+'\\System32','PYTHONPATH':'','TESSDATA_PREFIX':str(work/'NONEXISTENT'),'HF_HOME':str(work/'NO_MODELS'),'HTTP_PROXY':'http://127.0.0.1:9','HTTPS_PROXY':'http://127.0.0.1:9'})
    def run(extra,result_name):
        result=work/result_name
        t=time.monotonic();p=subprocess.run(command+['--convert',str(corpus),'--result',str(result),'--timeout','90']+extra,cwd=os.environ['SystemRoot'],env=env,timeout=900)
        if p.returncode:raise RuntimeError(result.read_text() if result.exists() else 'Packaged process failed: '+str(p.returncode))
        data=json.loads(result.read_text(encoding='utf-8'));data['wall_seconds']=time.monotonic()-t;return data
    first=run([],'first.json');manifest=json.loads(Path(first['manifest']).read_text(encoding='utf-8'));out=Path(first['output'])
    checks=[]
    def check(name,condition,detail=''):
        checks.append({'check':name,'passed':bool(condition),'detail':detail});print(('PASS ' if condition else 'FAIL ')+name,flush=True)
    def md(name):
        p=out/(name+'.md');return p.read_text(encoding='utf-8') if p.exists() else ''
    hashes_after=source_hashes(corpus);changes=input_changes(hashes,hashes_after)
    check('Input hashes unchanged',hashes==hashes_after,json.dumps(changes,ensure_ascii=False) if hashes!=hashes_after else '')
    if args.expected_revision is not None:
        actual_revision=manifest.get('backend_versions',{}).get('converter_revision')
        check('Expected converter revision',actual_revision==args.expected_revision,
              f'Expected {args.expected_revision}; actual {actual_revision}')
    check('Empty hierarchy and legitimate _md folder',(out/'nested'/'empty').is_dir() and (out/'genuine_md'/'keep.txt.md').exists())
    check('Same-basename outputs distinct',all((out/('same.'+ext+'.md')).is_file() for ext in ('pdf','docx','xlsx')))
    check('Markdown byte identity',(out/'notes.md.md').read_bytes()==(corpus/'notes.md').read_bytes())
    excel=md('same.xlsx');xlsm=md('macro.xlsm')
    for expected in ['00123','$1,234.50','12.5%','2026-09-22','00007','42','Saved value unavailable','Hidden saved value','Very hidden saved value','Far sparse value','colspan="3"','#DIV/0!','=literal text']:
        check('Spreadsheet content: '+expected,expected in excel and expected in xlsm)
    check('Formula expressions and VBA absent',all(s not in excel+xlsm+json.dumps(manifest) for s in ['SUM(40,2)','SUM(500,600)','=1/0','VBA_SENTINEL']))
    check('Legacy XLS cached value','42' in md('legacy.xls') and '40+2' not in md('legacy.xls'))
    check('Native PDF and numeric table',all(s in md('same.pdf') for s in ('Native heading 7612','125','250','|')))
    check('Native header and scanned body',all(s in md('mixed.pdf') for s in ('NATIVE HEADER 9031','ENGLISH SCANNED BODY','4826')))
    check('No duplicated native header',md('mixed.pdf').count('NATIVE HEADER 9031')==1)
    check('Rotated scan read','ENGLISH SCANNED BODY' in md('mixed.pdf').split('## Page 2')[-1])
    check('Arabic OCR logical phrase','مرحبا بالعالم' in md('scan.png'),'Actual: '+md('scan.png').split('OFFLINE DOCUMENT CONVERSION')[-1].strip())
    check('ONNX OCR engine used',any('ONNX OCR engine' in w for w in manifest['files']['scan.png'].get('warnings',[])))
    check('Arabic scanned PDF','مرحبا بالعالم' in md('scanned.pdf'),'Actual: '+md('scanned.pdf').split('OFFLINE DOCUMENT CONVERSION')[-1].split('[Page')[0].strip())
    from make_fixtures import HIDDEN_SENTINEL,HIDDEN_ARABIC
    check('Invisible OCR layer replaced by clean Arabic OCR',
          'مرحبا بالعالم' in md('hidden-ocr.pdf') and HIDDEN_SENTINEL not in md('hidden-ocr.pdf') and HIDDEN_ARABIC not in md('hidden-ocr.pdf'))
    for name in ('control-text.pdf','control-block.pdf'):
        check('Unreadable native font: '+name,'RECOVERED FONT TEXT 4826' in md(name) and '\x01' not in md(name))
    check('Rotated page image clip','ROTATED IMAGE TEXT 7392' in md('rotated-image.pdf') and not any('extraction failed' in w for w in manifest['files']['rotated-image.pdf'].get('warnings',[])))
    check('Multi-page TIFF','SECOND TIFF PAGE 7392' in md('multipage.tiff') and '## Image frame 2' in md('multipage.tiff'))
    check('Word heading/list/table/header/footer',all(s in md('same.docx') for s in ('6394','First list item','12.50','4139','8217','ENGLISH SCANNED BODY')))
    check('PowerPoint title/table/notes/image text',all(s in md('slides.pptx') for s in ('5908','876','2178','ENGLISH SCANNED BODY')))
    check('Macro Office containers read',all(s in md('macro.docm') for s in ('6394','4139')) and '2178' in md('macro.pptm'))
    check('HTML scripts and network images excluded','SECRET_SCRIPT' not in md('page.html') and 'javascript:' not in md('page.html') and 'https://invalid.example' not in md('page.html'))
    check('CSV escaping','A\\|B' in md('table.csv') and 'line 1<br>line 2' in md('table.csv'))
    check('Corrupt/protected/unsupported accountable',manifest['files']['broken.docx']['status']=='failed' and manifest['files']['protected.pdf']['status']=='failed' and manifest['files']['unsupported.bin']['status']=='unsupported')
    check('Large workbook complete','49999' in md('large.xlsx') and 'Row 49999' in md('large.xlsx'))
    links=[]
    for p in out.rglob('*.md'):
        if p.name=='conversion_report.md':continue
        from urllib.parse import unquote
        for target in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
            links.append((p.parent/unquote(target)).is_file())
    check('Generated asset links resolve',bool(links) and all(links))
    for name,expected in [('legacy.doc','6394'),('legacy.ppt','5908')]:
        check('Required legacy '+Path(name).suffix,expected in md(name),manifest['files'].get(name,{}).get('warnings',['Fixture not yet generated']))
    second=run([],'second.json');check('Repeat run skips completed conversions',second['summary'].get('unchanged',0)>=25)
    source=corpus/'nested'/'ملاحظات.txt';source.write_text('changed Arabic filename content',encoding='utf-8')
    third=run([],'changed.json');check('Changed source refreshes','changed Arabic filename content' in md('nested/ملاحظات.txt'))
    report={'environment':{'platform':platform.platform(),'python_for_test_driver':sys.version,'processor':platform.processor(),'ordinary_user':True,'network_disconnected':False,'clean_machine':False,'path_stripped':True,'external_cache_paths_invalid':True},'command':command,'first_run':first,'second_run':second,'changed_run':third,'checks':checks,'passed':sum(c['passed'] for c in checks),'failed':sum(not c['passed'] for c in checks),'manifest_snapshot':manifest,
            'input_hashes_before':hashes,'input_hashes_after':hashes_after,'input_changes':changes,
            'expected_converter_revision':args.expected_revision,'converter_identity':manifest.get('backend_versions',{})}
    dest=ROOT/'test-results'/(args.name+'-acceptance.json');dest.parent.mkdir(exist_ok=True);dest.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if not report['failed'] else 2

if __name__=='__main__':raise SystemExit(main())
