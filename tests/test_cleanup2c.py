# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cleanup2c: fathatan marks that are not a real tanween are removed. Synthetic Arabic only."""
from foldertomd import arabicfix

FT = 'ً'


def clean(text):
    return arabicfix.drop_stray_tanween(text)


def test_real_tanween_stays_in_every_normal_place():
    for line in ('جداً', 'مثلةً', 'عصىً', 'شكرًا', 'جزءًا من الكل', 'يومياً عن كل موقع'):
        assert clean(line) == line


def test_mark_after_space_bracket_or_non_final_letter_is_removed():
    assert clean('كلمة ' + FT + 'أخرى') == 'كلمة أخرى'
    assert clean('(' + FT + 'غرامة قدرها') == '(غرامة قدرها'
    assert clean('الاختباراتً الازمة') == 'الاختبارات الازمة'     # after a non-alef letter, then a space


def test_lines_with_only_marks_and_punctuation_are_cleaned():
    for junk in (FT, FT + '%', FT + ')', FT + ' ' + FT, FT + '/'):
        assert clean(junk) == junk.replace(FT, '')


def test_lines_with_digits_or_latin_keep_their_marks():
    for line in ('12' + FT + '5', 'ABC' + FT, '١٢٣' + FT):
        assert clean(line) == line


def test_many_marks_do_not_prove_font_noise():
    noisy = ' '.join(['غرامةً', 'علىً', 'حالةً', 'الجهةً']) + ' عادي'
    assert clean(noisy) == noisy
    mixed = 'عطوفاً ومهتماً' + ' غرامةً علىً'                      # four marks: the two real ones stay
    assert clean(mixed) == mixed


def test_tanween_stored_after_the_punctuation_moves_back_before_it():
    assert clean('مثلا،' + FT) == 'مثلاً،'
    assert clean('كاملا.' + FT) == 'كاملاً.'
    assert clean('أفعالا:' + FT) == 'أفعالاً:'
    assert clean('مثلا،') == 'مثلا،'                              # no mark: untouched


def test_a_few_marks_keep_only_the_real_ones():
    assert clean('جداً ' + FT + 'ثم الباقي') == 'جداً ثم الباقي'


def test_cleanup_is_stable_and_clean_lines_are_identical():
    text = 'نص نظيف' + '\n' + 'جداً'
    assert clean(text) == text
    once = clean('كلمة ' + FT + 'أخرى جداً')
    assert clean(once) == once


def test_typed_final_tanween_needs_two_letters_before_the_mark():
    for real in ('يومًا', 'فورًا', 'جزءًا من', 'وفقًا لما'):
        assert clean(real) == real
    assert clean('في لًا شيء') == 'في لا شيء'                      # two-letter words: the mark is noise
    assert clean('فًى') == 'فى' and clean('مًا') == 'ما'
