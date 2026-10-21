# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cleanup9: blue rubber-stamp blocks are removed before OCR; black text under them stays."""
from PIL import Image, ImageDraw
from foldertomd import scanlayout as S

STAMP = (70, 95, 205)


def _page():
    return Image.new('RGB', (1400, 2000), 'white')


def _stamp(draw, x, y, w=420, h=230):
    draw.rectangle((x, y, x + w, y + h), outline=STAMP, width=5)
    for i in range(4):
        draw.rectangle((x + 30, y + 30 + i * 48, x + w - 40, y + 52 + i * 48), fill=STAMP)


def test_rectangular_blue_stamp_is_removed_and_black_text_under_it_kept():
    im = _page(); d = ImageDraw.Draw(im)
    _stamp(d, 800, 900)
    d.rectangle((760, 1000, 1300, 1012), fill=(0, 0, 0))            # black text line crossing the stamp
    d.rectangle((900, 1040, 1100, 1050), fill=(25, 25, 70))         # black ink printed under blue ink
    cleaned, changed = S.remove_color_stamps(im)
    assert changed
    assert cleaned.getpixel((802, 950)) == (255, 255, 255)          # stamp border
    assert cleaned.getpixel((850, 945)) == (255, 255, 255)          # stamp text
    assert cleaned.getpixel((1000, 1006)) == (0, 0, 0)
    assert cleaned.getpixel((1000, 1045)) == (25, 25, 70)


def test_blue_heading_line_and_small_blue_handwriting_are_untouched():
    im = _page(); d = ImageDraw.Draw(im)
    d.rectangle((100, 100, 1200, 130), fill=STAMP)                  # one blue heading line
    d.line((200, 600, 240, 560, 280, 600), fill=STAMP, width=6)     # small handwritten mark
    cleaned, changed = S.remove_color_stamps(im)
    assert not changed and cleaned.tobytes() == im.tobytes()


def test_red_block_is_not_a_blue_stamp():
    im = _page(); d = ImageDraw.Draw(im)
    for i in range(5):
        d.rectangle((300, 300 + i * 50, 800, 320 + i * 50), fill=(200, 40, 40))
    cleaned, changed = S.remove_color_stamps(im)
    assert not changed and cleaned.tobytes() == im.tobytes()
