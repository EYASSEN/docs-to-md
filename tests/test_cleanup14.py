# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cleanup14: an introduction shared by the items below it is a row of its own without a number."""
from test_cleanup12 import split, w


def test_introduction_ending_with_colon_is_its_own_row_even_without_a_wide_gap():
    # BOQs 1 p18 valve: only a narrow gap separates "... التالية :-" from the item line beside number 3
    out = split([w('1', 100), w('2', 272)],
                [w('مساليب', 100), w('قطر', 125),
                 w('بالعدد', 180), w('توريد', 205), w('التالية', 230), w(':-', 230),
                 w('محبس', 272), w('فراشة', 295)],
                [w('عدد', 125), w('عدد', 295)],
                [w('3', 125), w('3', 295)])
    assert out[1][1] == 'مساليب قطر'
    assert out[2][1] == 'بالعدد توريد التالية :-' and out[2][2] == '' and out[2][3] == ''
    assert out[3][1] == 'محبس فراشة' and out[3][2] == 'عدد'


def test_section_heading_separated_by_a_gap_is_its_own_row():
    out = split([w('1', 100), w('2', 330)],
                [w('Pump', 100), w('complete', 130), w('Section', 200), w('16060', 200), w('Valve', 330)],
                [w('No.', 130), w('No.', 330)],
                [w('2', 130), w('4', 330)])
    assert [r[0] for r in out[1:]] == ['1', '', '2']
    assert out[2][1] == 'Section 16060' and out[3][1] == 'Valve'
