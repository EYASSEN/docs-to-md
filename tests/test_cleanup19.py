# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cleanup19: the window shows the Yassin Labs brand; copyright and licence notices stay personal.
Each MSIX identity gets its own layout folder. The light theme is calm stone and slate, with no pure
white surfaces and no pure black text."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_window_brand_is_yassin_labs_and_copyright_is_personal():
    gui = (ROOT / 'foldertomd' / 'gui.py').read_text(encoding='utf-8')
    assert re.search(r"AUTHOR='Yassin Labs'", gui)
    assert "COPYRIGHT='Copyright (C) 2026 Yassin Abd El Aal'" in gui


def test_store_and_test_packages_use_separate_layout_folders():
    script = (ROOT / 'scripts' / 'make_msix.py').read_text(encoding='utf-8')
    assert "ROOT / 'build' / 'msix' / args.name" in script


def test_light_theme_is_soft_stone_and_slate():
    gui = (ROOT / 'foldertomd' / 'gui.py').read_text(encoding='utf-8')
    light = gui[gui.index(" 'light':dict("):]
    for key in ('WINDOW', 'PANEL', 'RAISED', 'OPTS', 'INSET', 'CHECK_OFF'):
        value = re.search(key + r"='(#[0-9a-f]{6})'", light).group(1)
        assert value != '#ffffff', key
    assert "TEXT='#22292b'" in light and "ACCENT='#4a5f6b'" in light
    assert "'#ffffff' if not t['dark']" not in gui and "if t['dark'] else '#ffffff'" not in gui
