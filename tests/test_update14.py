# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Update14: long and Arabic paths (pure helpers; the Windows-only parts are checked with Windows path rules)."""
import sys, ntpath, types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from foldertomd import paths

def _win(monkeypatch):
    monkeypatch.setattr(paths,'os',types.SimpleNamespace(name='nt',path=ntpath,environ=paths.os.environ))
    monkeypatch.setattr(paths,'Path',str)

def test_long_path_prefix(monkeypatch):
    _win(monkeypatch)
    assert paths.long_path('C:\\Users\\x\\ملفات\\a.pdf')=='\\\\?\\C:\\Users\\x\\ملفات\\a.pdf'
    assert paths.long_path('\\\\server\\share\\b.pdf')=='\\\\?\\UNC\\server\\share\\b.pdf'
    assert paths.long_path('\\\\?\\C:\\done.pdf')=='\\\\?\\C:\\done.pdf'          # idempotent
    assert paths.long_path('C:\\a\\..\\b.pdf')=='\\\\?\\C:\\b.pdf'                  # normalised

def test_display_path_removes_prefix():
    assert paths.display_path('\\\\?\\C:\\a\\b')=='C:\\a\\b'
    assert paths.display_path('\\\\?\\UNC\\server\\share\\x')=='\\\\server\\share\\x'
    assert paths.display_path('C:\\plain')=='C:\\plain'

def test_short_work_root_is_short_and_per_output(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    a=paths.short_work_root(Path('X:/very/long/'+'مجلد'*60+'/.foldertomd-data-0123456789abcdef0123456789abcdef'))
    b=paths.short_work_root(Path('X:/other/.foldertomd-data-ffffffffffffffffffffffffffffffff'))
    assert a!=b and a.is_dir() and len(str(a))<len(str(tmp_path))+40

def test_copy_into_replaces_atomically(tmp_path):
    src=tmp_path/'s.md'; src.write_text('new',encoding='utf-8')
    dest=tmp_path/'مجلد'/'ملف.md'; dest.parent.mkdir(); dest.write_text('old',encoding='utf-8')
    paths.copy_into(src,dest)
    assert dest.read_text(encoding='utf-8')=='new' and not list(dest.parent.glob('*.tmp'))
    d=tmp_path/'assets'; d.mkdir(); (d/'a.png').write_bytes(b'x')
    paths.copy_into(d,tmp_path/'out'/'gen') if (tmp_path/'out').mkdir() is None else None
    assert (tmp_path/'out'/'gen'/'a.png').read_bytes()==b'x'

def test_output_too_long_threshold():
    # short test folders: ordinary paths, exactly as before Update14
    assert not paths.output_too_long(60, 6, [10, 40])
    # a deep Arabic tree under a long OneDrive folder: extended-length paths needed
    assert paths.output_too_long(140, 19, [120])
    # a long source folder alone is enough, because of the asset folder path
    assert paths.output_too_long(200, 19, [])

def test_needs_long_paths_is_off_outside_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(paths.os, 'name', 'posix')
    (tmp_path/('م'*60)).mkdir()
    assert paths.needs_long_paths(tmp_path) is False
