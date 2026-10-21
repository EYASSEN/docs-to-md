# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Consistency checks added by Cleanup1: documented defaults and names must agree."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_cli_timeout_default_matches_the_engine_default():
    from foldertomd.engine import DEFAULTS
    main_source = (ROOT / 'main.py').read_text(encoding='utf-8')
    cli = re.search(r"'--timeout',type=float,default=(\d+)", main_source)
    assert cli and float(cli.group(1)) == float(DEFAULTS['timeout'])


def test_readme_states_the_real_default_timeout():
    from foldertomd.engine import DEFAULTS
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    assert f"default {int(DEFAULTS['timeout'])} seconds" in readme


def test_report_header_uses_the_same_author_spelling_as_the_copyright():
    engine = (ROOT / 'foldertomd' / 'engine.py').read_text(encoding='utf-8')
    gui = (ROOT / 'foldertomd' / 'gui.py').read_text(encoding='utf-8')
    spelling = re.search(r'COPYRIGHT=.Copyright \(C\) 2026 (.+?)\'', gui).group(1)
    header = re.search(r"by Yassin (Abd E[l]? Aal) — ", engine).group(1)
    assert 'Yassin ' + header == spelling


def test_private_fixture_folders_are_not_published():
    ignore = (ROOT / '.gitignore').read_text(encoding='utf-8')
    assert 'tests/fixtures/update*/' in ignore
    assert '!tests/fixtures/**' not in ignore


def test_git_publishes_only_synthetic_fixtures(tmp_path):
    """Run real git on a scratch copy of the ignore rules (skipped when git is missing)."""
    import shutil
    if shutil.which('git') is None:
        return
    (tmp_path / '.gitignore').write_text((ROOT / '.gitignore').read_text(encoding='utf-8'), encoding='utf-8')
    names = ['tests/fixtures/arabic_table.pdf', 'tests/fixtures/hidden-ocr.pdf', 'tests/fixtures/pdf/hidden-ocr.pdf',
             'tests/fixtures/legacy/legacy.doc', 'tests/fixtures/update38/arSuppSpec.pdf',
             'tests/fixtures/update39/coefficient-table.pdf', 'tests/fixtures/update40/digit-cells.png',
             'tests/fixtures/update39/ground-truth.json', 'reports/run/result.md', 'old-result.zip']
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'x')
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True)
    listed = subprocess.run(['git', 'ls-files', '-o', '--exclude-standard'], cwd=tmp_path,
                            capture_output=True, text=True, check=True).stdout.split()
    assert {'tests/fixtures/arabic_table.pdf', 'tests/fixtures/hidden-ocr.pdf',
            'tests/fixtures/pdf/hidden-ocr.pdf', 'tests/fixtures/legacy/legacy.doc'} <= set(listed)
    assert not [n for n in listed if '/update' in n or n.startswith('reports/') or n.endswith('.zip')]
