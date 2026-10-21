# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cleanup13: a versioned release ships only its own verification evidence."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.package import prepare_evidence


def test_versioned_package_starts_with_an_empty_verification_folder(tmp_path):
    stale = tmp_path / 'verification'; stale.mkdir()
    for name in ('source-rc3.log', 'packaged-tests.log', 'windows-code-integrity.json'):
        (stale / name).write_text('September release candidate', encoding='utf-8')
    evidence = prepare_evidence(tmp_path, 54)
    assert evidence == stale and evidence.is_dir() and not any(evidence.iterdir())


def test_unversioned_package_keeps_its_evidence(tmp_path):
    folder = tmp_path / 'verification'; folder.mkdir()
    (folder / 'build.log').write_text('log', encoding='utf-8')
    assert (prepare_evidence(tmp_path, None) / 'build.log').exists()
