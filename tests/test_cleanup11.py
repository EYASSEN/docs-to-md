# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cleanup11: a scan that reads as noise gets a smoothed re-read or a clear notice, never noise.
Pages with readable text keep the normal reading path, with no extra layout pass."""
import csv, io, sys
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from foldertomd import ocr as O, ocrclean as C

FIELDS = ['level', 'page_num', 'block_num', 'par_num', 'line_num', 'word_num', 'left', 'top', 'width', 'height', 'conf', 'text']


def _word(text, conf, line=1, left=10, top=10):
    return {'level': '5', 'page_num': '1', 'block_num': '1', 'par_num': '1', 'line_num': str(line), 'word_num': '1',
            'left': str(left), 'top': str(top), 'width': '40', 'height': '20', 'conf': str(conf), 'text': text}


def _tsv(words):
    out = io.StringIO(); w = csv.DictWriter(out, FIELDS, delimiter='\t'); w.writeheader()
    for x in words: w.writerow(x)
    return out.getvalue().encode()


NOISE = [_word(t, 30, line=i, top=10 + 25 * i) for i, t in enumerate(['ee', 'a', '|', '=', '2%', 'oe', 'he', 'ل'] * 6)]
READABLE = [_word(t, 92, line=i // 4, left=10 + 60 * (i % 4), top=10 + 30 * (i // 4)) for i, t in enumerate(
    'Reinforced concrete foundation shall comply with the drawings and the specification for every pump station'.split())]
SMOOTHED = ([_word(t, 88, line=i // 3, left=10 + 50 * (i % 3), top=10 + 30 * (i // 3)) for i, t in
             enumerate(['رمل', 'متوسط', 'حرش', 'أصفر', 'اللون', 'زلط', 'رفيع', 'وحصى', 'متر', 'يلي'])]
            + [_word('xx', 20, line=9, top=400)])


class Engine:
    """Fake Tesseract: answers by pass (layout, sparse, smoothed layout) and records the calls."""
    def __init__(self, layout, sparse, smoothed=()):
        self.layout, self.sparse, self.smoothed, self.calls = layout, sparse, list(smoothed), []

    def __call__(self, root, data, args, work, threads):
        psm = args[args.index('--psm') + 1]
        self.calls.append(psm)
        if psm == '0':
            return type('R', (), {'returncode': 1, 'stdout': b'', 'stderr': b''})()
        layout_calls = self.calls.count('3')
        rows = self.sparse if psm == '11' else (self.layout if layout_calls == 1 else self.smoothed)
        return type('R', (), {'returncode': 0, 'stdout': _tsv(rows), 'stderr': b''})()


def _run(monkeypatch, engine):
    monkeypatch.setattr(O, 'preflight', lambda s=None: None)
    monkeypatch.setattr(O, '_tesseract', engine)
    data = O._png(Image.new('RGB', (1240, 1754), 'white'))
    return O.transcribe(data, {'language': 'ara+eng', 'quality': 'standard'}, None, 'Page 9', rendered=True)


def test_noise_page_becomes_a_clear_notice(monkeypatch):
    value, warnings, confidence = _run(monkeypatch, Engine([], NOISE, []))
    assert str(value) == O.UNREADABLE_NOTICE and value.parts == [('text', O.UNREADABLE_NOTICE)]
    assert confidence is None and any('unreadable scan' in w for w in warnings)


def test_noise_page_with_a_readable_smoothed_copy_keeps_that_text_under_a_notice(monkeypatch):
    value, warnings, confidence = _run(monkeypatch, Engine([], NOISE, SMOOTHED))
    assert value.parts[0] == ('text', O.POOR_SCAN_NOTICE)
    body = value.parts[1][1]
    assert 'رمل متوسط حرش' in body and 'xx' not in body
    assert any('smoothed copy' in w for w in warnings)


def test_readable_page_keeps_the_normal_path_without_an_extra_layout_pass(monkeypatch):
    engine = Engine(READABLE, READABLE)
    value, warnings, confidence = _run(monkeypatch, engine)
    assert 'Reinforced concrete' in str(value) and O.UNREADABLE_NOTICE not in str(value)
    assert engine.calls.count('3') == 1          # the probe reading is reused
    assert not any('unreadable' in w or 'smoothed' in w for w in warnings)


def test_sparse_page_with_few_fragments_is_not_called_unreadable():
    # a blank page or a drawing with a few labels: too few fragments to call it noise
    assert not C.looks_unreadable([], NOISE[:10])
    # many fragments but enough confident words: a real sparse page
    labelled = NOISE + [_word(t, 90) for t in ('Settlement', 'maximum', 'stage', 'immediate', 'total', 'curve', 'Analysis', 'Description')]
    assert not C.looks_unreadable([], labelled)
    # labels read with fair confidence (a drawing): not noise even with few confident words
    drawing = [_word(t, 70) for t in ['SWL', '52.40', 'DN1000', 'PS3', 'L1', 'A-A'] * 5] + [_word('PUDDLE', 85)]
    assert not C.looks_unreadable([], drawing)
    assert C.looks_unreadable([], NOISE)
    # Geotechnical Report page 4 on the Windows build: 100 fragments, 7 confident, mean 48.6
    page4 = [_word('ee', 45)] * 93 + [_word('العكرة', 85)] * 7
    assert C.looks_unreadable([], page4)


def test_descreen_merges_dots_into_strokes():
    im = Image.new('RGB', (120, 60), 'white'); px = im.load()
    for x in range(20, 100):
        for y in range(20, 40):
            if (x + y) % 2 == 0: px[x, y] = (0, 0, 0)         # a dotted bar (half the pixels)
    out = C.descreen(im, 300).convert('L')
    assert out.getpixel((60, 30)) == 0 and out.getpixel((60, 31)) == 0 and out.getpixel((5, 5)) == 255
