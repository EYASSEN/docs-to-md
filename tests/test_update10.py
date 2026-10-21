# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Update10: Arabic line order, private-use ligatures, brackets and backwards digits (pure functions)."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from foldertomd.pdf import _balance_brackets, _reverse_digit_runs, _fix_presentation_forms, _visual_line, _needs_visual_order

def spans_from_visual(visual, size=10.0):
    """One span whose characters are laid out left to right as written in `visual`."""
    chars=[]; x=10.0
    for ch in visual:
        w=3.0 if ch==' ' else 5.0
        chars.append({'c':ch,'bbox':(x,100.0,x+w,100.0+size)}); x+=w
    return [{'size':size,'bbox':(10.0,100.0,x,100.0+size),'chars':chars}]

def logical_to_visual_arabic(word):
    return word[::-1]

def test_brackets_reversed_pairs_are_swapped():
    assert _balance_brackets(')اليونسكو(')=='(اليونسكو)'
    assert _balance_brackets(')١٩٦٧(، و٣٣٨ )١٩٧٣(')=='(١٩٦٧)، و٣٣٨ (١٩٧٣)'
    assert _balance_brackets('(A/RES/57/196) و )2002/5(')=='(A/RES/57/196) و (2002/5)'
    assert _balance_brackets(')الموئل\nالثاني(')=='(الموئل\nالثاني)'

def test_brackets_correct_text_is_left_alone():
    for t in ['(1514 (XV))','(a) b','١) تقديم التدريب (انظر الملحق)','أ) البند\nب) البند (ج)','a) b (c','لا أقواس هنا']:
        assert _balance_brackets(t)==t

def test_backwards_digits_reverse_whole_numbers():
    assert _reverse_digit_runs('٠٠٠٢')=='٢٠٠٠'
    assert _reverse_digit_runs('القرار ٣١/٧٥')=='القرار ٥٧/١٣'
    assert _reverse_digit_runs('٥٫١ م')=='١٫٥ م'
    assert _reverse_digit_runs('٧١ - ٨١')=='١٧ - ١٨'

def test_isolated_shadda_has_no_space():
    assert _fix_presentation_forms('توق\ufe7cع')=='توقّع'

def test_visual_line_ligature_and_number_order():
    # page shows (left to right): Arabic words reversed, a private-use "ته" ligature, and the paragraph number at the right
    visual=logical_to_visual_arabic('ا')+'\ue814'+logical_to_visual_arabic('اعتمد')+' - ٦١'
    spans=spans_from_visual(visual)
    assert _needs_visual_order(spans)
    assert _visual_line(spans)=='٦١ - اعتمدتها'

def test_visual_line_latin_run_with_brackets():
    visual=logical_to_visual_arabic('الصادر')+' (1514 (XV)) '+logical_to_visual_arabic('المتحدة')+'\ue825'
    assert _visual_line(spans_from_visual(visual))=='المتحدة (1514 (XV)) الصادر'

def test_visual_line_numbers_separated_by_spaces_stay_in_arabic_order():
    visual=logical_to_visual_arabic('مارس')+' ١٨ - ١٧ '+logical_to_visual_arabic('من')+'\ue820'
    assert _visual_line(spans_from_visual(visual))=='من ١٧ - ١٨ مارس'

def test_visual_line_decimal_and_resolution_number_kept_whole():
    visual='٥٧/١٣ '+logical_to_visual_arabic('القرار')+' ١٫٥ '+logical_to_visual_arabic('قطر')+'\ue820'
    assert _visual_line(spans_from_visual(visual))=='قطر ١٫٥ القرار ٥٧/١٣'

def test_plain_arabic_line_is_not_rebuilt():
    spans=[{'size':10,'bbox':(200,100,260,110),'chars':[{'c':'ب','bbox':(250,100,255,110)},{'c':'ا','bbox':(245,100,250,110)}]},
           {'size':10,'bbox':(100,100,160,110),'chars':[{'c':'ج','bbox':(150,100,155,110)}]}]
    assert not _needs_visual_order(spans)
