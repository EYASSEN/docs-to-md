# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Repack a released portable ZIP as a smaller 7z archive with identical contents (Cleanup16).

The ZIP is not changed. Its files are checked against BUNDLE_SHA256.json, packed with the
build-cache 7-Zip, then extracted again with the Windows built-in tar.exe (the same archive
library File Explorer uses) and checked against BUNDLE_SHA256.json a second time."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile, zipfile

ROOT = Path(__file__).resolve().parents[1]
SEVEN = ROOT / 'build-cache' / '7zip' / '7z.exe'
SEVEN_ARGS = ['a', '-t7z', '-mx=9', '-m0=lzma2', '-md=64m', '-ms=on', '-mmt=on', '-bd', '-bso0']

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def check_tree(top):
    """Every file under top must be listed in BUNDLE_SHA256.json with the same hash, and every
    listed file must exist. Returns the number of checked files."""
    listed = json.loads((top / 'BUNDLE_SHA256.json').read_text(encoding='utf-8'))
    found = {p.relative_to(top).as_posix() for p in top.rglob('*') if p.is_file()} - {'BUNDLE_SHA256.json'}
    missing = sorted(set(listed) - found)
    extra = sorted(found - set(listed))
    wrong = sorted(n for n in set(listed) & found if digest(top / n) != listed[n])
    if missing or extra or wrong:
        raise RuntimeError('Contents differ from BUNDLE_SHA256.json: missing %s, extra %s, changed %s'
                           % (missing[:5], extra[:5], wrong[:5]))
    return len(listed)

def windows_tar():
    tar = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'tar.exe'
    return tar if tar.is_file() else None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--zip', type=Path, required=True)
    args = parser.parse_args()
    source = args.zip.resolve()
    if not source.is_file():
        raise SystemExit('ZIP not found: ' + str(source))
    if not SEVEN.is_file():
        raise SystemExit('7-Zip not found at ' + str(SEVEN) + '. Run scripts/acquire.py once.')
    target = source.with_suffix('.7z')
    if target.exists():
        raise SystemExit('Refusing to replace existing ' + target.name + '. Move it away first.')
    zip_sha = digest(source)
    work = ROOT / 'build-cache'
    with tempfile.TemporaryDirectory(dir=work) as a, tempfile.TemporaryDirectory(dir=work) as b:
        with zipfile.ZipFile(source) as z:
            z.extractall(a)
        top = Path(a) / 'DocsToMD'
        count = check_tree(top)
        print('ZIP contents verified:', count, 'files', flush=True)
        partial = target.with_name(target.name + '.part')
        partial.unlink(missing_ok=True)
        subprocess.run([str(SEVEN)] + SEVEN_ARGS + [str(partial), 'DocsToMD'], cwd=a, check=True)
        subprocess.run([str(SEVEN), 't', '-bd', '-bso0', str(partial)], check=True)
        tar = windows_tar()
        if tar:
            subprocess.run([str(tar), '-xf', str(partial), '-C', b], check=True)
            reader = 'Windows tar.exe'
        else:
            subprocess.run([str(SEVEN), 'x', '-bd', '-bso0', '-o' + b, str(partial)], check=True)
            reader = '7-Zip (Windows tar.exe not found)'
        check_tree(Path(b) / 'DocsToMD')
        print('7z contents verified with', reader, flush=True)
        partial.replace(target)
    if digest(source) != zip_sha:
        raise RuntimeError('The source ZIP changed during repacking')
    sha = digest(target)
    target.with_name(target.name + '.sha256').write_text(sha + '  ' + target.name + '\n', encoding='utf-8')
    print(json.dumps({'zip_bytes': source.stat().st_size, 'zip_sha256': zip_sha,
                      '7z_bytes': target.stat().st_size, '7z_sha256': sha,
                      'files': count + 1, 'verified_with': reader}, indent=2))
    return 0

if __name__ == '__main__':
    sys.exit(main())
