# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Update19: manifest writes survive a briefly locked file (OneDrive sync)."""
import sys, os, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from foldertomd import paths

def test_atomic_json_retries_while_locked(tmp_path, monkeypatch):
    target=tmp_path/'manifest.json'; target.write_text('{"old": 1}',encoding='utf-8')
    real=os.replace; calls={'n':0}
    def locked(src,dst):
        calls['n']+=1
        if calls['n']<=3: raise PermissionError(5,'Access is denied')
        return real(src,dst)
    monkeypatch.setattr(paths.os,'replace',locked); monkeypatch.setattr(paths.time,'sleep',lambda s:None)
    paths.atomic_json(target,{'new':2})
    assert json.loads(target.read_text(encoding='utf-8'))=={'new':2} and calls['n']==4
    assert not list(tmp_path.glob('*.tmp'))

def test_atomic_json_gives_up_and_keeps_old_file(tmp_path, monkeypatch):
    target=tmp_path/'manifest.json'; target.write_text('{"old": 1}',encoding='utf-8')
    def always(src,dst): raise PermissionError(5,'Access is denied')
    monkeypatch.setattr(paths.os,'replace',always); monkeypatch.setattr(paths.time,'sleep',lambda s:None)
    try: paths.atomic_json(target,{'new':2}); raised=False
    except PermissionError: raised=True
    assert raised and json.loads(target.read_text(encoding='utf-8'))=={'old':1} and not list(tmp_path.glob('*.tmp'))
