# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build-only dependency acquisition. First acquisition records TLS source hashes;
subsequent builds MUST match dependencies.lock.json. No runtime downloads."""
from pathlib import Path
import concurrent.futures, hashlib, json, shutil, subprocess, urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'build-cache'
VENDOR = ROOT / 'vendor'
URLS = {
    '7zr.exe': 'https://www.7-zip.org/a/7zr.exe',
    '7z2409-x64.exe': 'https://www.7-zip.org/a/7z2409-x64.exe',
    'tesseract.exe': 'https://github.com/tesseract-ocr/tesseract/releases/download/5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe',
    **{f'{lang}.traineddata': f'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/{lang}.traineddata' for lang in ('ara', 'eng', 'osd')},
    'tessdata-LICENSE': 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/LICENSE',
    'AGPL-3.0.txt': 'https://raw.githubusercontent.com/pymupdf/PyMuPDF/1.26.7/COPYING',
}

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    CACHE.mkdir(exist_ok=True); VENDOR.mkdir(exist_ok=True)
    lockpath = ROOT / 'dependencies.lock.json'
    lock = json.loads(lockpath.read_text()) if lockpath.exists() else {}
    def fetch(item):
        name, url = item; dest = CACHE / name
        if not dest.exists():
            print('Downloading', name, flush=True)
            tmp = dest.with_suffix('.part')
            with urllib.request.urlopen(url, timeout=90) as r, tmp.open('wb') as w:
                shutil.copyfileobj(r, w)
            tmp.replace(dest)
        sha = digest(dest)
        if name in lock and lock[name]['sha256'] != sha:
            raise RuntimeError('Checksum mismatch: ' + name)
        print('Verified', name, sha, flush=True)
        return name, {'url': url, 'sha256': sha, 'bytes': dest.stat().st_size}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for name, record in pool.map(fetch, URLS.items()):
            lock[name] = record
            lockpath.write_text(json.dumps(lock, indent=2), encoding='utf-8')
    seven = CACHE / '7zip' / '7z.exe'
    if not seven.exists():
        subprocess.run([str(CACHE/'7zr.exe'), 'x', str(CACHE/'7z2409-x64.exe'), '-o'+str(seven.parent), '-y'], check=True)
    tess = VENDOR / 'tesseract'
    if not (tess/'tesseract.exe').exists():
        subprocess.run([str(seven), 'x', str(CACHE/'tesseract.exe'), '-o'+str(tess), '-y'], check=True)
    (tess/'tessdata').mkdir(exist_ok=True)
    for lang in ('ara', 'eng', 'osd'):
        shutil.copy2(CACHE/f'{lang}.traineddata', tess/'tessdata')
    shutil.copy2(CACHE/'tessdata-LICENSE', tess/'tessdata'/'LICENSE')
    shutil.copy2(CACHE/'AGPL-3.0.txt', ROOT/'LICENSE')
    from acquire_java import main as java
    java()
    print('Dependencies ready', flush=True)

if __name__ == '__main__': main()
