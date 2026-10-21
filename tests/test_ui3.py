# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""UI3: the original window again, light theme only, dark blue in place of green."""
from pathlib import Path

GUI = Path(__file__).resolve().parents[1] / 'foldertomd' / 'gui.py'


def test_light_theme_has_no_green():
    from foldertomd.gui import THEMES
    light = THEMES['light']
    colours = [v for v in light.values() if isinstance(v, str) and v.startswith('#')]
    colours += [c for pair in light['BADGES'].values() for c in pair] + list(light['TAGS'].values())
    for green in ('#059669', '#047857', '#065f46', '#10b981', '#34d399', '#6ee7b7', '#a7f3d0', '#d1fae5', '#ecfdf5', '#f0fdf4'):
        assert green not in colours, green
    assert light['ACCENT'] == '#4a5f6b'   # slate since Cleanup19 (was dark blue #1e3a6e)


def test_window_is_light_only_without_theme_switch():
    source = GUI.read_text(encoding='utf-8')
    assert "self.theme='light'" in source
    assert 'self.toggle' not in source
    assert "ui.json" not in source
