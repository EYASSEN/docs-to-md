# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
from PIL import Image, ImageDraw
from foldertomd.scanlayout import _edge_covered, best_ruled_grid


def _table(break_left=None):
    image = Image.new('RGB', (900, 1200), 'white')
    draw = ImageDraw.Draw(image)
    top, bottom, xs = 100, 1000, (60, 260, 460, 840)
    for y in (top, 180, bottom):
        draw.line([(xs[0], y), (xs[-1], y)], fill='black', width=3)
    for x in xs:
        if x == xs[0] and break_left:
            a, b = break_left
            draw.line([(x, top), (x, a)], fill='black', width=3)
            draw.line([(x, b), (x, bottom)], fill='black', width=3)
        else:
            draw.line([(x, top), (x, bottom)], fill='black', width=3)
    return image


def test_whole_stroke_is_covered():
    assert _edge_covered([(50, 100, 50, 1000)], 50, 100, 1000)


def test_small_break_is_tolerated():
    vertical = [(50, 100, 50, 500), (50, 540, 50, 1000)]
    assert _edge_covered(vertical, 50, 100, 1000)


def test_large_break_is_rejected():
    vertical = [(50, 100, 50, 400), (50, 700, 50, 1000)]
    assert not _edge_covered(vertical, 50, 100, 1000)


def test_missing_edge_is_rejected():
    assert not _edge_covered([(300, 100, 300, 1000)], 50, 100, 1000)


def test_grid_found_with_small_break_in_outer_border():
    _, grid = best_ruled_grid(_table(break_left=(200, 230)), tolerant=True)
    assert grid and grid['columns'] == 3


def test_small_break_is_not_tolerated_by_default():
    _, grid = best_ruled_grid(_table(break_left=(200, 230)))
    assert grid is None


def test_grid_not_found_when_border_mostly_missing():
    _, grid = best_ruled_grid(_table(break_left=(300, 800)), tolerant=True)
    assert not grid or grid['columns'] != 3


def test_strict_mode_rejects_broken_edge():
    assert not _edge_covered([(50, 100, 50, 500), (50, 540, 50, 1000)], 50, 100, 1000, tolerant=False)
