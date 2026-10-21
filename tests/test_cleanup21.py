# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cleanup21: the published documents describe the current release and the public repository
contains the Java source of the legacy Office reader."""
import shutil, subprocess, sys
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from foldertomd import __version__
from foldertomd.engine import CONVERSION_REVISION

DOCS = ('README.md', 'QUICKSTART_AR.md', 'SUPPORTED_FORMATS.md')


def test_readme_and_quick_start_name_the_current_version():
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    assert f'Version {__version__} (conversion revision {CONVERSION_REVISION})' in readme
    assert __version__ in (ROOT / 'QUICKSTART_AR.md').read_text(encoding='utf-8')
    assert 'rc3' not in readme and 'Release candidate' not in readme


@pytest.mark.parametrize('name', DOCS)
def test_published_documents_do_not_point_to_the_unpublished_acceptance_report(name):
    assert 'ACCEPTANCE_REPORT' not in (ROOT / name).read_text(encoding='utf-8')


def test_readme_names_the_store_page_website_and_licence():
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    for text in ('https://apps.microsoft.com/detail/9P14JB03S057', 'https://eyassen.github.io/docs-to-md/',
                 'GNU Affero General Public License', 'java/LegacyReader.java'):
        assert text in readme


def test_git_publishes_the_legacy_reader_source_only(tmp_path):
    if shutil.which('git') is None:
        pytest.skip('git is not installed')
    (tmp_path / '.gitignore').write_text((ROOT / '.gitignore').read_text(encoding='utf-8'), encoding='utf-8')
    for name in ('java/LegacyReader.java', 'java/LegacyReader.class', 'java/notes.txt'):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(b'x')
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True)
    listed = subprocess.run(['git', 'ls-files', '-o', '--exclude-standard'], cwd=tmp_path,
                            capture_output=True, text=True, check=True).stdout.split()
    assert [n for n in listed if n.startswith('java/')] == ['java/LegacyReader.java']
