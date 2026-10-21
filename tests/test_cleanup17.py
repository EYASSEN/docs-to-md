# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cleanup17: Standard and High accuracy read scanned pages with the bundled ONNX OCR engine.
Tesseract keeps orientation, stamp removal and the noise verdict; Quick mode, a missing engine
or an engine failure keep the Tesseract reading."""
import sys
from pathlib import Path
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from foldertomd import ocr as O, ocrengine as E, engine as ENG
from test_cleanup11 import Engine as Tess, NOISE, READABLE


def _box(x0, y0, x1, y1):
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float32)


ENGINE_LINES = [
    (_box(100, 100, 400, 130), 'Basket Screen Height', 0.98),
    (_box(450, 100, 520, 130), 'mm', 0.97),
    (_box(560, 100, 700, 130), '1,700-1,740', 0.96),
    (_box(100, 160, 600, 190), 'Pumps shall be ATEX certified for ZONE 1', 0.95),
]


class FakeOnnx:
    def __init__(self, lines=ENGINE_LINES, fail=False):
        self.found, self.fail, self.calls = lines, fail, 0

    def read(self, image, language):
        self.calls += 1
        if self.fail:
            raise RuntimeError('model failed')
        return E.rows_from_lines(self.found)


def _run(monkeypatch, tess, onnx, settings):
    monkeypatch.setattr(O, 'preflight', lambda s=None: None)
    monkeypatch.setattr(O, '_tesseract', tess)
    monkeypatch.setattr(O.ocrengine, 'available', lambda: True)
    monkeypatch.setattr(O.ocrengine, 'engine', lambda threads=None: onnx)
    data = O._png(Image.new('RGB', (1240, 1754), 'white'))
    return O.transcribe(data, settings, None, 'Page 3', rendered=True)


def test_standard_scan_is_read_by_the_onnx_engine(monkeypatch):
    tess, onnx = Tess(READABLE, READABLE), FakeOnnx()
    value, warnings, confidence = _run(monkeypatch, tess, onnx, {'language': 'ara+eng', 'quality': 'standard', 'ocr_engine': 'onnx'})
    assert onnx.calls == 1
    assert 'Basket Screen Height mm 1,700-1,740' in str(value)
    assert 'Reinforced concrete' not in str(value)
    assert tess.calls.count('3') == 1 and '11' not in tess.calls     # probe only; no Tesseract text passes
    assert any('ONNX OCR engine' in w for w in warnings)
    assert confidence > 90


@pytest.mark.parametrize('settings', [{'language': 'ara+eng', 'quality': 'quick', 'ocr_engine': 'onnx'},
                                      {'language': 'ara+eng', 'quality': 'standard'},
                                      {'language': 'ara+eng', 'quality': 'standard', 'ocr_engine': 'tesseract'}])
def test_quick_mode_and_tesseract_setting_keep_tesseract(monkeypatch, settings):
    onnx = FakeOnnx()
    value, warnings, _ = _run(monkeypatch, Tess(READABLE, READABLE), onnx, settings)
    assert onnx.calls == 0 and 'Reinforced concrete' in str(value)


def test_engine_failure_falls_back_to_tesseract_with_a_warning(monkeypatch):
    onnx = FakeOnnx(fail=True)
    value, warnings, _ = _run(monkeypatch, Tess(READABLE, READABLE), onnx, {'language': 'ara+eng', 'quality': 'standard', 'ocr_engine': 'onnx'})
    assert onnx.calls == 1 and 'Reinforced concrete' in str(value)
    assert any('Tesseract was used instead' in w for w in warnings)


def test_missing_engine_keeps_tesseract(monkeypatch):
    onnx = FakeOnnx()
    tess = Tess(READABLE, READABLE)
    monkeypatch.setattr(O, 'preflight', lambda s=None: None)
    monkeypatch.setattr(O, '_tesseract', tess)
    monkeypatch.setattr(O.ocrengine, 'available', lambda: False)
    monkeypatch.setattr(O.ocrengine, 'engine', lambda threads=None: onnx)
    data = O._png(Image.new('RGB', (1240, 1754), 'white'))
    value, _, _ = O.transcribe(data, {'language': 'ara+eng', 'quality': 'standard', 'ocr_engine': 'onnx'}, None, 'Page 3', rendered=True)
    assert onnx.calls == 0 and 'Reinforced concrete' in str(value)


ARABIC_WORDS = ['رمل', 'متوسط', 'حرش', 'أصفر', 'اللون', 'زلط', 'رفيع', 'وحصى', 'جيرى', 'متدرج']


def test_noise_page_keeps_a_good_engine_reading_under_the_poor_scan_notice(monkeypatch):
    lines = [(_box(100, 100 + 40 * i, 600, 130 + 40 * i), w + ' ' + w, 0.9) for i, w in enumerate(ARABIC_WORDS)]
    value, warnings, _ = _run(monkeypatch, Tess([], NOISE, []), FakeOnnx(lines), {'language': 'ara+eng', 'quality': 'standard', 'ocr_engine': 'onnx'})
    assert value.parts[0] == ('text', O.POOR_SCAN_NOTICE)
    assert 'رمل رمل' in value.parts[1][1]
    assert any('ONNX OCR engine' in w and 'approximate' in w for w in warnings)


def test_noise_page_with_a_weak_engine_reading_stays_unreadable(monkeypatch):
    lines = [(_box(100, 100, 300, 130), 'ee', 0.4)]
    value, warnings, _ = _run(monkeypatch, Tess([], NOISE, []), FakeOnnx(lines), {'language': 'ara+eng', 'quality': 'standard', 'ocr_engine': 'onnx'})
    assert str(value) == O.UNREADABLE_NOTICE


def test_engine_lines_become_tesseract_style_rows_in_reading_order():
    rows = E.rows_from_lines(ENGINE_LINES)
    first = [r for r in rows if r['block_num'] == '1']
    assert [r['text'] for r in first] == ['Basket', 'Screen', 'Height', 'mm', '1,700-1,740']
    lefts = [int(r['left']) for r in first]
    assert lefts == sorted(lefts) and 100 <= lefts[0] < 110
    assert all(r['line_num'] == '1' and float(r['conf']) > 90 for r in rows)
    assert {r['block_num'] for r in rows} == {'1', '2'}


def test_arabic_line_lists_the_rightmost_box_and_word_first():
    rows = E.rows_from_lines([(_box(100, 100, 250, 130), 'عدد', 0.9), (_box(400, 100, 700, 130), 'وصلات فك و تركيب', 0.9)])
    assert [r['text'] for r in rows] == ['وصلات', 'فك', 'و', 'تركيب', 'عدد']
    assert int(rows[0]['left']) > int(rows[1]['left']) > int(rows[3]['left']) > int(rows[4]['left'])


def test_conversion_default_turns_the_engine_on():
    assert ENG.DEFAULTS['ocr_engine'] == 'onnx'


def test_geometry_helpers_match_a_known_rectangle():
    corners, short = E.min_area_rect(np.array([[10, 10], [110, 10], [110, 40], [10, 40], [60, 25]]))
    assert round(short) == 30
    box, side = E.mini_box(corners)
    assert box[0].tolist() == [10, 10] and box[2].tolist() == [110, 40]
    mask = np.zeros((20, 30), dtype=bool); mask[2:5, 3:9] = True; mask[10:15, 20:25] = True; mask[5, 9] = True
    assert len(E.components(mask)) == 2


@pytest.mark.skipif(not E.available(), reason='ONNX OCR models or onnxruntime not installed')
def test_bundled_models_read_a_printed_line():
    image = Image.new('RGB', (900, 160), 'white')
    try:
        font = ImageFont.truetype('arial.ttf', 48)
    except OSError:
        font = ImageFont.load_default(size=48)
    ImageDraw.Draw(image).text((30, 50), 'Flow capacity 990 l/s', fill='black', font=font)
    text = ' '.join(t for _, t, _ in E.engine().lines(image, 'ara+eng'))
    assert '990' in text and 'capacity' in text.lower()


def test_chinese_readings_of_icons_are_dropped_and_fullwidth_marks_normalised():
    assert E._latin_arabic('目') == ''
    assert E._latin_arabic('5 to 6.5 meters 一') == '5 to 6.5 meters '
    assert E._latin_arabic('１２０％') == '120%'
    assert E._latin_arabic('مرحبا ١٢٣') == 'مرحبا ١٢٣'


@pytest.mark.skipif(not E.available(), reason='ONNX OCR models or onnxruntime not installed')
def test_very_large_text_is_read_as_one_line():
    """A 2500 px render with 150 px capitals (acceptance control-text.pdf) split into overlapping
    boxes ("T4826") before the second, scaled detection."""
    image = Image.new('RGB', (2500, 2084), 'white')
    try:
        font = ImageFont.truetype('arial.ttf', 150)
    except OSError:
        font = ImageFont.load_default(size=150)
    ImageDraw.Draw(image).text((115, 880), 'RECOVERED FONT TEXT 4826', fill='black', font=font)
    lines = E.engine().lines(image, 'ara+eng')
    assert ' '.join(t for _, t, _ in lines).split() == ['RECOVERED', 'FONT', 'TEXT', '4826']
