# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verify delivery bytes without executing the application; archive the source."""
from pathlib import Path
import hashlib,json,re,shutil,zipfile
from urllib.parse import unquote
ROOT=Path(__file__).resolve().parents[1]
def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    release=ROOT/'release';archive=release/'DocsToMD-Windows-x64-Portable.zip'
    moved=ROOT/'test-work'/'delivery relocation اختبار'
    moved.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        z.extractall(moved)
    app=moved/'DocsToMD'
    hashes=json.loads((app/'BUNDLE_SHA256.json').read_text())
    for rel,h in hashes.items():assert digest(app/rel)==h,rel
    required=['DocsToMD.exe','Launch_DocsToMD.bat','vendor/tesseract/tesseract.exe',
              'vendor/tesseract/tessdata/ara.traineddata','vendor/tesseract/tessdata/eng.traineddata',
              'vendor/tesseract/tessdata/osd.traineddata','vendor/jre/bin/java.exe',
              'vendor/poi/classes/LegacyReader.class','README.md','QUICKSTART_AR.md','ACCEPTANCE_REPORT.md']
    for rel in required:assert (app/rel).is_file(),rel
    acceptance=json.loads((ROOT/'test-results/source-pdf-fix-acceptance.json').read_text(encoding='utf-8'))
    output=moved/'relocated output مخرجات'
    shutil.copytree(Path(acceptance['first_run']['output']),output,dirs_exist_ok=True)
    checked=0
    for p in output.rglob('*.md'):
        if p.name=='conversion_report.md':continue
        for target in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
            assert (p.parent/unquote(target)).is_file(),(p,target)
            checked+=1
    assert checked
    packaged=ROOT/'test-results/packaged-pdf-fix-acceptance.json'
    packaged_result=json.loads(packaged.read_text(encoding='utf-8')) if packaged.exists() else None
    report={'portable_zip_crc':'passed','relocated_bundle_hashes_checked':len(hashes),
            'required_resources':required,'moved_output_image_links_checked':checked,
            'packaged_execution':({'passed':packaged_result['passed'],'failed':packaged_result['failed']} if packaged_result else 'No updated packaged result; consult acceptance report'),
            'clean_machine_offline_execution':'unverified'}
    (release/'delivery-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    source=release/'DocsToMD-Source.zip'
    files=[]
    for directory in ('foldertomd','java','scripts','tests','licenses','test-results'):
        files.extend(p for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    files.extend(p for p in ROOT.iterdir() if p.is_file() and (p.suffix in ('.py','.md','.txt','.json','.spec','.manifest','.ps1','.bat') or p.name in ('LICENSE','.gitignore')))
    files.extend(ROOT/name for name in ('build.log','unit-tests.log','source-rc3.log','source-pdf-fix.log','packaged-tests.log'))
    files.extend(release/name for name in ('package-metrics.json','delivery-verification.json'))
    with zipfile.ZipFile(source,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(set(files)):z.write(p,Path('DocsToMD-Source')/p.relative_to(ROOT))
    with zipfile.ZipFile(source) as z:
        assert z.testzip() is None
        count=len(z.infolist())
    sums=release/'SHA256SUMS.txt'
    sums.write_text(digest(archive)+'  '+archive.name+'\n'+digest(source)+'  '+source.name+'\n'+digest(app/'DocsToMD.exe')+'  DocsToMD/DocsToMD.exe\n',encoding='utf-8')
    report.update(source_zip_crc='passed',source_files=count,source_zip_bytes=source.stat().st_size,source_zip_sha256=digest(source))
    (release/'delivery-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
