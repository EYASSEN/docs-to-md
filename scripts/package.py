# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Copy only release files, include notices, hash every bundled file, and ZIP."""
from pathlib import Path
import argparse,hashlib,importlib.metadata,json,os,shutil,sys,zipfile,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from foldertomd import __version__

def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def prepare_evidence(app,revision):
    """The verification folder of the package. build.ps1 ends with an unversioned package step that copies
    the September release-candidate logs into it; a versioned release must ship only its own evidence,
    so that folder is emptied first (Cleanup13)."""
    evidence=app/'verification'
    if revision and evidence.exists():shutil.rmtree(evidence)
    evidence.mkdir(exist_ok=True)
    return evidence

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--app',type=Path,default=ROOT/'dist'/'DocsToMD')
    parser.add_argument('--release',type=Path,default=ROOT/'release')
    parser.add_argument('--revision',type=int)
    args=parser.parse_args()
    app=args.app.resolve();release=args.release.resolve();release.mkdir(parents=True,exist_ok=True)
    if not (app/'DocsToMD.exe').is_file():raise RuntimeError('Build Windows executable first')
    for name in ('jre','poi'):
        shutil.copytree(ROOT/'vendor'/name,app/'vendor'/name,dirs_exist_ok=True)
    # Cleanup17: ONNX OCR models and their licences travel with the source in ocr-models.
    shutil.copytree(ROOT/'ocr-models',app/'vendor'/'ocr-onnx',dirs_exist_ok=True)
    from ocr_closure import closure
    tess=ROOT/'vendor'/'tesseract';target=app/'vendor'/'tesseract';target.mkdir(parents=True,exist_ok=True)
    needed,system=closure(tess)
    for name in needed:
        src=next(p for p in tess.iterdir() if p.name.lower()==name);shutil.copy2(src,target/src.name)
    if args.revision:
        # This versioned build may have been provisioned with the complete
        # installer tree for testing. Ship only the verified runtime closure.
        for extra in target.iterdir():
            if extra.is_file() and extra.name.lower() not in needed: extra.unlink()
    shutil.copytree(tess/'tessdata',target/'tessdata',dirs_exist_ok=True)
    shutil.copytree(tess/'doc',target/'doc',dirs_exist_ok=True)
    # The installer support DLLs and training tools are not runtime dependencies.
    plugins=app/'vendor'/'tesseract'/'$PLUGINSDIR'
    if plugins.exists():shutil.rmtree(plugins)
    for name in ('Launch_DocsToMD.bat','README.md','QUICKSTART_AR.md','SUPPORTED_FORMATS.md','THIRD_PARTY_NOTICES.md','LICENSE','dependencies.lock.json','requirements.lock.txt','ACCEPTANCE_REPORT.md'):
        if (ROOT/name).exists():shutil.copy2(ROOT/name,app/name)
    evidence=prepare_evidence(app,args.revision)
    evidence_names=(f'revision{args.revision}-unit.xml',f'revision{args.revision}-exe-acceptance.json') if args.revision else ('source-rc3-acceptance.json','source-pdf-fix-acceptance.json','packaged-pdf-fix-acceptance.json','source-unit.xml','windows-code-integrity.json','packaged-blocked.json')
    for name in evidence_names:
        if (ROOT/'test-results'/name).exists():shutil.copy2(ROOT/'test-results'/name,evidence/name)
    if args.revision:
        acceptance=json.loads((ROOT/'test-results'/f'revision{args.revision}-exe-acceptance.json').read_text(encoding='utf-8'))
        suite=ET.parse(ROOT/'test-results'/f'revision{args.revision}-unit.xml').getroot().find('testsuite')
        assert acceptance['failed']==0 and acceptance['expected_converter_revision']==args.revision
        assert acceptance['converter_identity']['code']['sha256']==digest(app/'DocsToMD.exe')
        assert all(int(suite.attrib[k])==0 for k in ('errors','failures','skipped'))
        targeted=''
        regression=release/'regression-verification.json'
        if args.revision==49:
            result=json.loads(regression.read_text(encoding='utf-8'))
            assert result['failed']==0 and result['exe_sha256']==digest(app/'DocsToMD.exe')
            shutil.copy2(regression,evidence/regression.name)
            shutil.copy2(release/'REVIEW_CONCLUSION.md',app/'REVIEW_CONCLUSION.md')
            targeted=f"Targeted conversion: {result['pages_completed']} selected pages completed; {result['passed']} content gates passed. Other reviewed OCR errors remain unresolved.\n\n"
        (app/'ACCEPTANCE_REPORT.md').write_text(
            f"# Revision {args.revision} validation\n\nFull source suite: {suite.attrib['tests']} passed, zero failed or skipped; private fixtures required.\n\n"
            f"Packaged executable: {acceptance['passed']} checks passed, {acceptance['failed']} failed; expected converter revision enforced.\n\n"
            +targeted+
            "Offline runtimes were exercised with PATH stripped, invalid external cache paths and blocked proxy settings. A clean-machine offline run remains unverified.\n\n"
            f"See RELEASE_NOTES_{args.revision}.md for fixes and remaining corpus accuracy limitations.\n",encoding='utf-8')
        for name in (f'revision{args.revision}-unit.log',f'revision{args.revision}-build.log'):
            shutil.copy2(ROOT/'test-results'/name,evidence/name)
    for name in (() if args.revision else ('unit-tests.log','source-rc3.log','source-pdf-fix.log','packaged-tests.log','build.log')):
        if (ROOT/name).exists():shutil.copy2(ROOT/name,evidence/name)
    notices=app/'licenses';notices.mkdir(exist_ok=True)
    if (ROOT/'licenses').exists():shutil.copytree(ROOT/'licenses',notices,dirs_exist_ok=True)
    (notices/'ocr-native-imports.json').write_text(json.dumps({'bundled':needed,'windows_system_apis':system},indent=2),encoding='utf-8')
    packages=[]
    for dist in importlib.metadata.distributions():
        name=dist.metadata['Name'];packages.append({'name':name,'version':dist.version,'license':dist.metadata.get('License-Expression') or dist.metadata.get('License','See accompanying license'),'homepage':dist.metadata.get('Home-page','')})
        for file in dist.files or []:
            if ('dist-info' in str(file) and any(t in str(file).lower() for t in ('license','copying','notice'))) or (name=='Pillow' and file.name=='LICENSE'):
                src=Path(dist.locate_file(file))
                if src.is_file():
                    target=notices/name/Path(str(file).split('.dist-info/')[-1]);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
    pythonlicense=Path(sys.base_prefix)/'LICENSE.txt'
    if pythonlicense.exists():shutil.copy2(pythonlicense,notices/'Python-LICENSE.txt')
    for path in (Path(sys.base_prefix)/'tcl').glob('*/license.terms'):
        shutil.copy2(path,notices/(path.parent.name+'-license.txt'))
    (notices/'python-build-environment.json').write_text(json.dumps(packages,ensure_ascii=False,indent=2),encoding='utf-8')
    if args.revision:
        notes=ROOT/f'RELEASE_NOTES_{args.revision}.md'
        if notes.exists(): shutil.copy2(notes,app/notes.name)
    checksums={p.relative_to(app).as_posix():digest(p) for p in sorted(app.rglob('*')) if p.is_file() and 'data' not in p.relative_to(app).parts and p.name!='BUNDLE_SHA256.json'}
    (app/'BUNDLE_SHA256.json').write_text(json.dumps(checksums,indent=2),encoding='utf-8')
    archive=release/(f'DocsToMD-{__version__}-revision{args.revision}-Windows-x64-Portable.zip' if args.revision else 'DocsToMD-Windows-x64-Portable.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(app.rglob('*')):
            if p.is_file() and 'data' not in p.relative_to(app).parts:z.write(p,p.relative_to(app.parent))
    metrics={'zip_bytes':archive.stat().st_size,'extracted_bytes':sum(p.stat().st_size for p in app.rglob('*') if p.is_file() and 'data' not in p.relative_to(app).parts),'files':len(checksums)+1,'zip_sha256':digest(archive),'exe_sha256':digest(app/'DocsToMD.exe')}
    (release/'package-metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    (release/'SHA256SUMS.txt').write_text(metrics['zip_sha256']+'  '+archive.name+'\n'+metrics['exe_sha256']+'  DocsToMD/DocsToMD.exe\n',encoding='utf-8')
    print(json.dumps(metrics,indent=2))

if __name__=='__main__':main()
