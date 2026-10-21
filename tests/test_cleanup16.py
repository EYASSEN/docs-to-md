# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cleanup16: the 7z repack must hold exactly the files listed in BUNDLE_SHA256.json."""
import hashlib, json, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.make_7z import check_tree, SEVEN_ARGS


def bundle(top, files):
    top.mkdir(parents=True)
    for name, data in files.items():
        p = top / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
    listed = {n: hashlib.sha256(d).hexdigest() for n, d in files.items()}
    (top / 'BUNDLE_SHA256.json').write_text(json.dumps(listed), encoding='utf-8')
    return top


def test_matching_tree_passes(tmp_path):
    top = bundle(tmp_path / 'DocsToMD', {'DocsToMD.exe': b'exe', 'vendor/jre/bin/java.exe': b'java'})
    assert check_tree(top) == 2


@pytest.mark.parametrize('change', ['missing', 'extra', 'changed'])
def test_any_difference_stops_the_repack(tmp_path, change):
    top = bundle(tmp_path / 'DocsToMD', {'DocsToMD.exe': b'exe', 'README.md': b'readme'})
    if change == 'missing': (top / 'README.md').unlink()
    if change == 'extra': (top / 'stray.txt').write_bytes(b'x')
    if change == 'changed': (top / 'README.md').write_bytes(b'edited')
    with pytest.raises(RuntimeError):
        check_tree(top)


def test_archive_settings_are_plain_7z_lzma2():
    assert SEVEN_ARGS[:4] == ['a', '-t7z', '-mx=9', '-m0=lzma2']
