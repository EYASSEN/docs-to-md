# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import hashlib, json, os, shutil, stat, tempfile, time, uuid

MAGIC = 'FolderToMD-output-v1'

def long_path(p):
    """Windows only: the extended-length path prefix lets Python use paths longer than 260 characters
    without any system setting or admin rights (Update14). Idempotent; unchanged elsewhere."""
    s = str(p)
    if os.name != 'nt' or s.startswith('\\\\?\\'): return Path(s)
    s = os.path.abspath(s)
    if s.startswith('\\\\'): return Path('\\\\?\\UNC\\' + s[2:])
    return Path('\\\\?\\' + s)

OUTPUT_EXTRA = len('.foldertomd-data-') + 32 + len('/assets/') + 32 + len('/visual-00000.png') + 2
TMP_SUFFIX = 13          # '.xxxxxxxx.tmp' added by copy_into
LIMIT = 250              # stay under the 260-character Windows limit with a margin

def output_too_long(source_len, name_len, rel_lens):
    """True when some output path would pass the Windows limit. Output root is <source>/<name>_md;
    each file becomes <root>/<rel>.md, written first as a temporary file next to it (Update14)."""
    root = source_len + 1 + name_len + 3
    if root + 1 + OUTPUT_EXTRA > LIMIT: return True
    return any(root + 1 + n + 3 + TMP_SUFFIX > LIMIT for n in rel_lens)

def needs_long_paths(source):
    """Only use extended-length paths when this folder needs them, so ordinary folders behave exactly
    as before Update14."""
    if os.name != 'nt': return False
    source = Path(source)
    base = len(str(source))
    rels = []
    for b, dirs, files in os.walk(long_path(source)):
        prefix = len(display_path(b)) - base
        rels.extend(prefix + 1 + len(n) for n in files + dirs)
    return output_too_long(base, len(source.name), rels)

def display_path(p):
    """A path for people and for Explorer, without the extended-length prefix."""
    s = str(p)
    if s.startswith('\\\\?\\UNC\\'): return '\\\\' + s[8:]
    if s.startswith('\\\\?\\'): return s[4:]
    return s

def short_work_root(meta):
    """Per-output workspace root on a short, local path. A new process cannot start in a working
    directory longer than about 258 characters, so workspaces no longer live inside the output
    folder (Update14). One folder per output root, so the output lock also guards its cleanup."""
    base = os.environ.get('LOCALAPPDATA') or tempfile.gettempdir()
    root = Path(base)/'DocsToMD'/'work'/Path(str(meta)).name[-12:]
    root.mkdir(parents=True, exist_ok=True)
    return root

def copy_into(src, dest, retries=6):
    """Place a copy of src at dest, even when they are on different drives (Update14).
    A folder is copied straight to dest: its name is always new, so it needs no rename, and renaming a
    folder whose new files an antivirus is still scanning fails with Access denied (Update16).
    A file is copied next to dest first and then renamed, retrying briefly while it is locked."""
    dest = Path(dest)
    if Path(src).is_dir():
        try: shutil.copytree(src, dest)
        except BaseException:
            shutil.rmtree(dest, ignore_errors=True); raise
        return
    tmp = dest.with_name(dest.name + '.' + uuid.uuid4().hex[:8] + '.tmp')
    try:
        shutil.copyfile(src, tmp)
        for attempt in range(retries):
            try: os.replace(tmp, dest); break
            except PermissionError:
                if attempt == retries - 1: raise
                time.sleep(0.25 * (attempt + 1))
    finally:
        if tmp.exists(): tmp.unlink(missing_ok=True)

def sha256(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def atomic_json(path, data, retries=12):
    """Write JSON atomically. OneDrive (and antivirus) briefly lock a file they are syncing or
    scanning; the rename is retried with growing waits, about 15 seconds in total (Update19)."""
    path = Path(path)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with tmp.open('w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2); f.flush(); os.fsync(f.fileno())
        for attempt in range(retries):
            try: os.replace(tmp, path); break
            except PermissionError:
                if attempt == retries - 1: raise
                time.sleep(min(0.25 * (attempt + 1), 2.0))
    finally:
        tmp.unlink(missing_ok=True)

def is_link(path):
    try:
        s = Path(path).lstat()
        return stat.S_ISLNK(s.st_mode) or bool(getattr(s, 'st_file_attributes', 0) & 0x400)
    except OSError:
        return False

def marker(root):
    if is_link(root): return None
    try:
        for p in root.glob('.foldertomd-owner-*.json'):
            if p.is_file() and p.stat().st_size < 4096:
                d = json.loads(p.read_text(encoding='utf-8'))
                if d.get('magic') == MAGIC and d.get('metadata', '').startswith('.foldertomd-data-') and '/' not in d['metadata'] and '\\' not in d['metadata']:
                    return d
    except (OSError, ValueError): pass
    return None

def output_path(source):
    source = Path(source).absolute()
    name = source.name
    if not name:
        name = source.anchor.rstrip('\\/').replace(':', '').replace('\\', '_') or 'root'
    return source / (name + '_md')

def prepare_output(source):
    root = output_path(source)
    if root.exists():
        owner = marker(root)
        if not owner:
            raise RuntimeError(f'Output conflict: {root} exists but is not owned by FolderToMD. Rename that folder first.')
    else:
        root.mkdir()
        ident = uuid.uuid4().hex
        owner = {'magic': MAGIC, 'metadata': '.foldertomd-data-' + ident}
        atomic_json(root / ('.foldertomd-owner-' + ident + '.json'), owner)
    meta = root / owner['metadata']
    if is_link(meta): raise RuntimeError('Output metadata is a link; refusing to write.')
    meta.mkdir(exist_ok=True)
    return root, meta

def safe_destination(root, relative):
    p = root / relative
    if not p.absolute().is_relative_to(root.absolute()): raise RuntimeError('Unsafe relative output path')
    current = root
    for segment in Path(relative).parts:
        current /= segment
        if is_link(current): raise RuntimeError('Output path contains a link: ' + str(relative))
    return p

def discover(source, output, cancel, notify):
    files, dirs, skipped = [], [], []
    def error(exc):
        skipped.append({'source': os.path.relpath(exc.filename, source), 'status': 'failed', 'warnings': ['Directory could not be read: ' + type(exc).__name__]})
    for base, names, fnames in os.walk(source, followlinks=False, onerror=error):
        if cancel.is_set(): break
        base = Path(base)
        keep = []
        for name in sorted(names, key=str.casefold):
            p = base/name; rel = p.relative_to(source).as_posix()
            if p == output or marker(p):
                skipped.append({'source': rel+'/', 'status': 'excluded', 'warnings': ['Application-generated output root']})
            elif is_link(p):
                skipped.append({'source': rel+'/', 'status': 'excluded', 'warnings': ['Symbolic link or junction not followed']})
            else:
                keep.append(name); dirs.append(rel)
        names[:] = keep
        for name in sorted(fnames, key=str.casefold):
            p = base/name; rel = p.relative_to(source).as_posix()
            if is_link(p) or name.startswith('~$'):
                skipped.append({'source': rel, 'status': 'excluded', 'warnings': ['Link not followed' if is_link(p) else 'Office temporary lock file']})
            else: files.append(rel)
        notify({'stage': 'Finding files', 'discovered': len(files), 'completed': 0})
    return files, dirs, skipped

class OutputLock:
    def __init__(self, meta): self.path = meta/'job.lock'
    def __enter__(self):
        import msvcrt
        self.f = self.path.open('a+b')
        if self.path.stat().st_size == 0: self.f.write(b'0'); self.f.flush()
        self.f.seek(0)
        try: msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.f.close(); raise RuntimeError('Another job is already using this output folder.')
        return self
    def __exit__(self, *args):
        import msvcrt
        self.f.seek(0); msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1); self.f.close()
