# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cleanup2: stray fathatan between Arabic letters. Synthetic Arabic only; no document text."""
import re

from foldertomd import arabicfix, engine, pdf

FT = '\u064b'
WORDS = ['الشركة', 'العامة', 'للمشاريع', 'الهندسية', 'والمقاولات']


def clean(text):
    return arabicfix.drop_stray_tanween(text)


def test_style_a_mark_is_the_separator():
    assert clean(FT.join(WORDS)) == ' '.join(WORDS)


def test_style_b_mark_sits_after_the_first_letter_of_each_word():
    line = ' '.join(w[0] + FT + w[1:] for w in WORDS)
    assert clean(line) == ' '.join(WORDS)


def test_word_final_tanween_stays_in_both_spellings():
    for line in ('شكراً جزيلاً', 'شكرًا جدًا', 'مثلةً أولاً', 'جزءًا من الكل', 'عصىً'):
        assert clean(line) == line


def test_legitimate_tanween_survives_next_to_stray_marks():
    stray = ' '.join(w[0] + FT + w[1:] for w in WORDS[:3])
    assert clean(stray + ' جداً') == ' '.join(WORDS[:3]) + ' جداً'
    glued = FT.join(WORDS[:3]) + ' شكرًا'
    assert clean(glued) == ' '.join(WORDS[:3]) + ' شكرًا'


def test_numbers_latin_and_other_marks_are_untouched():
    for line in ('Item 12' + FT + ' 5', 'ABC' + FT + 'DEF', '١٢٣' + FT + ' ٤٥٦', FT + ' alone',                  'مدّ' + FT + 'ا', 'plain text with no mark'):
        assert clean(line) == line


def test_single_word_with_one_stray_mark_is_not_split():
    assert clean('ب' + FT + 'عض') == 'بعض'                      # mark after the first letter: deleted
    assert clean(WORDS[0] + FT + WORDS[1]) == WORDS[0] + ' ' + WORDS[1]   # two words glued by one mark: space


def test_a_few_ordinary_spaces_do_not_turn_a_glued_run_into_style_b():
    # two marks and one ordinary space: the token with several marks is still style A
    assert clean(FT.join(WORDS[:3]) + ' ' + WORDS[3]) == ' '.join(WORDS[:4])
    assert clean(WORDS[3] + ' ' + FT.join(WORDS[:3])) == ' '.join([WORDS[3]] + WORDS[:3])


def test_lines_are_judged_one_by_one_and_clean_lines_stay_identical():
    a = FT.join(WORDS)
    b = ' '.join(w[0] + FT + w[1:] for w in WORDS)
    c = 'سطر نظيف  فيه  مسافات مزدوجة'
    assert clean('\n'.join([a, b, c])) == '\n'.join([' '.join(WORDS), ' '.join(WORDS), c])


def test_repeated_marks_count_as_one_site_and_result_is_stable():
    assert clean(FT + FT) == ''                                   # marks alone on a line: noise (Cleanup2c)
    line = (FT * 2).join(WORDS)
    assert clean(line) == ' '.join(WORDS)
    assert clean(clean(line)) == clean(line)


def test_no_mark_means_the_same_object_comes_back():
    text = 'نص عادي بدون علامات'
    assert clean(text) is text
    assert clean('') == '' and clean(None) is None


def test_no_fathatan_is_left_between_two_letters_after_cleaning():
    for line in (FT.join(WORDS), ' '.join(w[0] + FT + w[1:] for w in WORDS)):
        assert not re.search('[\u0621-\u064a]' + FT + '[\u0621-\u064a]', clean(line))


def test_pdf_native_fix_applies_the_cleanup_and_keeps_digits_order():
    assert pdf._native_fix(FT.join(WORDS), False) == ' '.join(WORDS)
    assert pdf._native_fix('جداً', False) == 'جداً'


def test_other_file_types_do_not_get_the_cleanup():
    # fix_text is shared with text files; only native PDF lines and cells use the stray-mark cleanup
    assert FT in arabicfix.fix_text(FT.join(WORDS))


def test_converter_revision_changed_with_the_output():
    assert engine.CONVERSION_REVISION == 58


# ---- shorter report ------------------------------------------------------------------------------
def test_repeated_page_warning_becomes_one_line_with_ranges():
    warnings = [f'Page {n}: ruled table read cell by cell; review merged cells.' for n in (3, 4, 5, 9)]
    warnings += ['Page 7: low OCR confidence (41/100); review text and numbers.',
                 'Page 8: low OCR confidence (55/100); review text and numbers.',
                 'Page 12: scan orientation corrected by 90 degrees.',
                 '3 pages contain glyphs that could not be read; Pages: 1, 2, 3']
    result = engine.condense_warnings(warnings)
    assert result[0] == 'Pages 3\u20135, 9 (4): ruled table read cell by cell; review merged cells.'
    assert result[1] == 'Pages 7\u20138 (2): low OCR confidence (#/#); review text and numbers.'
    assert result[2] == 'Page 12: scan orientation corrected by 90 degrees.'      # a single page stays word for word
    assert result[3] == warnings[-1]                                              # not page-labelled: untouched
    assert len(result) == 4


def test_warning_condensing_keeps_images_and_units_apart_and_caps_long_lists():
    w = ['Page 2 image: x.', 'Page 3 image: x.', 'Page 4: x.', 'Slide 1: x.', 'Slide 2: x.']
    assert engine.condense_warnings(w) == ['Page images 2\u20133 (2): x.', 'Page 4: x.', 'Slides 1\u20132 (2): x.']
    many = [f'Page {n}: y.' for n in range(1, 200, 2)]                          # 100 separate pages
    line = engine.condense_warnings(many)[0]
    assert line.startswith('Pages 1, 3, 5') and '(+80 more groups)' in line and len(line) < 200


def test_report_condenses_details_and_marks_unchanged_files_with_warnings(tmp_path):
    import json
    meta = tmp_path / 'meta'; meta.mkdir()
    pages = [f'Page {n}: some repeated review note.' for n in range(1, 41)]
    engine.reports(tmp_path, meta, {'files': {
        'a.pdf': {'status': 'unchanged', 'output': 'a.md', 'warnings': pages},
        'b.pdf': {'status': 'unchanged', 'output': 'b.md', 'warnings': []},
        'c.pdf': {'status': 'partial', 'output': 'c.md', 'warnings': ['Page 1: one note.']}}, 'elapsed_seconds': 1})
    report = (meta / 'conversion_report.md').read_text(encoding='utf-8').splitlines()
    a = next(l for l in report if l.startswith('| a.pdf'))
    assert a == '| a.pdf | unchanged (with warnings) | Pages 1\u201340 (40): some repeated review note. |'
    assert next(l for l in report if l.startswith('| b.pdf')) == '| b.pdf | unchanged |  |'
    assert next(l for l in report if l.startswith('| c.pdf')) == '| c.pdf | partial | Page 1: one note. |'
    kept = json.loads((meta / 'manifest.json').read_text(encoding='utf-8'))['files']['a.pdf']['warnings']
    assert kept == pages                                       # the manifest keeps every warning
