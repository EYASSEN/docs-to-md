# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cleanup2b: native table cells get the same stray-fathatan cleanup as plain lines. Synthetic Arabic only."""
import fitz

from foldertomd import pdf

FT = 'ً'
WORDS = ['الشركة', 'العامة', 'للمشاريع', 'الهندسية']


class _Row:
    def __init__(self, cells): self.cells = cells


class _Table:
    def __init__(self, rows): self.rows = [_Row(r) for r in rows]


def _block(text, x0, y0, x1, y1):
    n = len(text); w = (x1 - x0) / n
    chars = [{'c': ch, 'bbox': (x1 - (i + 1) * w, y0, x1 - i * w, y1), 'origin': (x1 - i * w, y1)} for i, ch in enumerate(text)]
    return {'type': 0, 'bbox': (x0, y0, x1, y1), 'lines': [{'spans': [{'size': 10, 'chars': chars}]}]}


def _cells(texts):
    blocks = [_block(t, 10 + 120 * i, 10, 120 + 120 * i, 22) for i, t in enumerate(texts)]
    cells = [(10 + 120 * i, 5, 125 + 120 * i, 30) for i in range(len(texts))]
    return pdf._table_rows(_Table([cells]), blocks, [])[0]


def test_table_cell_with_stray_marks_is_cleaned_and_clean_cell_is_unchanged():
    dirty = FT.join(WORDS[:3])
    out = _cells([dirty, 'بند 12'])
    assert FT not in out[0]
    assert out[1] == _cells(['بند 12'])[0]


def test_table_cell_keeps_a_real_word_final_tanween():
    assert FT in _cells(['شكرًا جزيلاً'])[0]


def test_table_cell_has_no_mark_between_two_letters():
    import re
    out = _cells([' '.join(w[0] + FT + w[1:] for w in WORDS)])[0]
    assert not re.search('[ء-ي]' + FT + '[ء-ي]', out)
