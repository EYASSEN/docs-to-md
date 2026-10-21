# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cleanup12: a heading or introduction above an item belongs to that item. The previous item's
unit marks where it ends; the boundary is the first paragraph gap after it."""
from foldertomd.boqrows import split_item_rows


def w(text, top, height=20, conf=90):
    return {'text': text, 'top': str(top), 'height': str(height), 'left': '0', 'width': '40', 'conf': str(conf)}


def table(numbers, description, units, quantities):
    """Header row plus one tall body row: ITEM, DESCRIPTION, UNIT, QTY (left to right)."""
    head = [[w('ITEM', 0)], [w('DESCRIPTION', 0)], [w('UNIT', 0)], [w('QTY', 0)]]
    body = [numbers, description, units, quantities]
    rows = [[' '.join(x['text'] for x in c) for c in head], [' '.join(x['text'] for x in c) for c in body]]
    box = [(0, 0, 50, 40), (0, 0, 50, 900)]
    readings = [[r, c, box[r], ws] for r, cells in enumerate((head, body)) for c, ws in enumerate(cells)]
    offsets = {(r, c): 0 for r in (0, 1) for c in range(4)}
    return rows, [[(0, 1), (1, 2), (2, 3), (3, 4)]] * 2, readings, offsets


def split(*parts):
    rows, spans, readings, offsets = table(*parts)
    out, _, _, n = split_item_rows(rows, spans, {}, readings, offsets, 4)
    assert n == 1
    return out


def test_section_heading_above_an_item_moves_to_that_item():
    # BOQs 1 p38/p39: "Section 16440 / Switchboards ..." sits above item 3, after item 2's unit line;
    # the small gap under the underlined heading must not be taken as the item boundary.
    out = split([w('1', 100), w('2', 300), w('3', 490)],
                [w('Transformer', 100), w('complete', 130), w('documents', 160),
                 w('RMU', 300), w('scada', 330), w('ratings', 360),
                 w('Section', 420), w('16440', 420), w('Switchboards', 462),
                 w('Main', 490), w('Switchboard', 520)],
                [w('No.', 160), w('No.', 360), w('No.', 520)],
                [w('2', 160), w('2', 360), w('6', 520)])
    assert [r[0] for r in out[1:]] == ['1', '2', '3']
    assert out[2][1] == 'RMU scada ratings' and out[2][2] == 'No.'
    assert out[3][1] == 'Section 16440 Switchboards Main Switchboard' and out[3][3] == '6'


def test_introduction_paragraph_moves_to_the_item_it_introduces():
    # BOQs 1 p18: "بالعدد توريد وتركيب اكواع ... التالية :-" then a gap, then the elbow line beside number 2
    out = split([w('1', 100), w('2', 330)],
                [w('مساليب', 100), w('قطر', 125),
                 w('بالعدد', 180), w('توريد', 205), w('التالية', 230), w(':-', 255),
                 w('اكواع', 330), w('قطر', 355)],
                [w('عدد', 125), w('عدد', 355)],
                [w('3', 125), w('3', 355)])
    # Cleanup14: the introduction is a row of its own without a number, as printed
    assert out[1][1] == 'مساليب قطر'
    assert out[2][1] == 'بالعدد توريد التالية :-' and out[2][0] == ''
    assert out[3][1] == 'اكواع قطر' and out[3][0] == '2'


def test_unread_noise_in_the_unit_column_does_not_mark_an_item_end():
    # a stamp over the unit column reads as low-confidence fragments; only sure unit words count
    out = split([w('1', 100), w('2', 330)],
                [w('مساليب', 100), w('قطر', 125),
                 w('بالعدد', 180), w('توريد', 205), w(':-', 230),
                 w('اكواع', 330), w('قطر', 355)],
                [w('عدد', 125), w('ae', 250, conf=30), w('عدد', 355)],
                [w('3', 125), w('3', 355)])
    assert out[2][1].startswith('بالعدد')


def test_unit_on_the_number_line_keeps_the_nearest_gap():
    # a one-line item whose unit sits beside its number: no end marker below it, old rule applies
    out = split([w('1', 100), w('2', 300)],
                [w('Pipe', 100), w('note', 160), w('note', 185), w('Valve', 300), w('end', 325)],
                [w('m', 100), w('No.', 300)],
                [w('5', 100), w('2', 300)])
    assert out[1][1] == 'Pipe note note' and out[2][1] == 'Valve end'
