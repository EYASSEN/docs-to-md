# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Update18: Word/browser ligature order, visual-order lines, background images under real text.
Character boxes below are copied from real Word and browser-printed PDFs (no document content)."""
import sys, io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import pymupdf as fitz
from PIL import Image
from foldertomd import pdf as P

def span(chars,size=11):
    return [{'size':size,'bbox':(0,100,600,112),'chars':[{'c':c,'bbox':(x0,100,x1,112)} for c,x0,x1 in chars]}]

def test_word_ligature_letter_follows_its_glyph():
    # Word stores على as ع, zero-width ى, ل and تأخير as ت أ خ, zero-width ر, ي
    assert P._visual_line(span([('ع',460.4,467.5),('ى',460.4,460.4),('ل',447.8,460.4)]))=='على'
    assert P._visual_line(span([('ت',361.0,364.2),('أ',357.4,361.0),('خ',350.7,357.4),('ر',350.8,350.8),('ي',343.6,350.8)]))=='تأخير'

def test_diacritics_attach_to_the_glyph_they_sit_on():
    # أولًا: tanween on the lam edge, alef inside the lam-alef glyph; قصّر: shadda on the sad edge
    assert P._visual_line(span([('أ',519.8,523.6),('و',512.9,519.9),('ً',512.9,512.9),('ل',504.6,512.9),('ا',509.6,509.6)]))=='أولًا'
    assert P._visual_line(span([('ق',314.8,322.1),('ّ',314.8,314.8),('ص',301.3,314.8),('ر',308.5,308.5)]))=='قصّر'

def test_browser_ligature_letter_precedes_alef_and_absorbs_stray_space():
    # a browser stores كليًا as ك ل, a "space" where the ي is, zero-width ً and ي, then ا
    out=P._visual_line(span([('ك',465.4,469.8),('ل',463.0,465.4),(' ',460.2,463.0),('ً',460.2,460.2),('ي',460.2,460.2),('ا',457.7,460.3)]))
    assert out.replace('\u064b','')=='كليا' and ' ' not in out

def test_lam_alef_keeps_the_word_space_before_it():
    # ذلك لا : the zero-width alef of لا sits where the real space starts; the space stays
    out=P._visual_line(span([('ذ',480,486),('ل',476,480),('ك',470,476),(' ',467,470),('ا',467,467),('ل',461,467)]))
    assert out=='ذلك لا'

def test_line_stored_in_visual_order_is_detected():
    # one span, characters stored left to right as drawn: a jump right between Arabic letters
    chars=[('م',100,106),('ق',106,112),('ر',112,116),(' ',116,119),('ر',200,204),('ا',204,206),('ر',206,210),('ق',210,216)]
    assert P._needs_visual_order(span(chars))
    # the same words stored in reading order are left alone
    logical=[('ق',210,216),('ر',206,210),('ا',204,206),('ر',200,204),(' ',116,119),('ر',112,116),('ق',106,112),('م',100,106)]
    assert not P._needs_visual_order(span(logical))

def _png():
    b=io.BytesIO(); Image.new('RGB',(200,280),(250,250,250)).save(b,'PNG'); return b.getvalue()

def test_text_on_top_of_a_background_image_is_kept():
    doc=fitz.open(); page=doc.new_page(width=595,height=842)
    page.insert_image(page.rect,stream=_png())
    page.insert_text((60,100),'Visible text over letterhead 4471',fontsize=14)
    blocks=page.get_text('rawdict')['blocks']
    assert P._hidden_layer(page,blocks)==[]

def test_text_under_a_page_sized_scan_is_hidden():
    doc=fitz.open(); page=doc.new_page(width=595,height=842)
    page.insert_text((60,100),'Covered OCR layer 8812',fontsize=14)
    page.insert_image(page.rect,stream=_png())
    blocks=page.get_text('rawdict')['blocks']
    hidden=P._hidden_layer(page,blocks)
    assert hidden and any(r.contains(fitz.Point(80,95)) for r in hidden)
