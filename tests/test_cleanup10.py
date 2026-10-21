# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cleanup10: invisible (fully transparent) PDF text never reaches the output, even when its
text-block box is larger than the trace boxes used to find the hidden OCR layer."""
import io, sys
from pathlib import Path
from types import SimpleNamespace
import pymupdf as fitz
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from foldertomd import pdf as P
from foldertomd.context import Context


def _ctx(tmp_path, source):
    work = tmp_path / 'work'; work.mkdir()
    ctx = Context({'source': str(source), 'work': str(work), 'asset_link': 'assets', 'relative': 'source.pdf',
                   'settings': {'language': 'ara+eng', 'ocr': 'auto', 'quality': 'standard', 'decode_fonts': False}})
    return ctx, work


def _scan_png():
    im = Image.new('RGB', (1240, 1754), 'white'); ImageDraw.Draw(im).rectangle((100, 100, 300, 160), fill='black')
    data = io.BytesIO(); im.save(data, 'PNG'); return data.getvalue()


def test_invisible_layer_missed_by_trace_boxes_is_still_hidden(tmp_path, monkeypatch):
    # VOL 1.1 pages 510/928: the scanner's OCR layer is invisible, but some of its spans have text-block
    # boxes whose centres fall outside every trace box, so ~30 letters of noise were exported as the page.
    source = tmp_path / 'source.pdf'; doc = fitz.open(); page = doc.new_page(width=595, height=842)
    page.insert_text((60, 100), 'LEAKED NOISE transmittersfetfefl chambers Landsberger', fontsize=12, render_mode=3)
    page.insert_image(page.rect, stream=_scan_png())
    doc.save(source)
    monkeypatch.setattr(P, '_hidden_layer', lambda page, blocks: [])     # trace boxes miss every span
    seen = []
    def recognized(image, ctx, label, **kwargs):
        seen.append(label); return 'PAGE READ BY OCR'
    monkeypatch.setattr(P, 'recognize', recognized)
    ctx, work = _ctx(tmp_path, source)
    P.extract_pdf(ctx); ctx.close()
    result = (work / 'result.md').read_text(encoding='utf-8')
    assert 'LEAKED' not in result and 'chambers' not in result
    assert seen == ['Page 1'] and 'PAGE READ BY OCR' in result


def test_invisible_watermark_box_does_not_hide_real_text_under_it(tmp_path, monkeypatch):
    # An invisible 72 pt watermark has a tall text-block box (font ascender); a visible line inside that
    # box, above the watermark's own glyphs, must stay (Annex 3 offer letter: the "Form" watermark).
    source = tmp_path / 'source.pdf'; doc = fitz.open(); page = doc.new_page(width=595, height=842)
    page.insert_text((60, 200), 'WATERMARK', fontsize=72, render_mode=3)
    page.insert_text((70, 138), 'Visible tender clause 2210 stays', fontsize=11)
    doc.save(source)
    monkeypatch.setattr(P, 'recognize', lambda *a, **k: (_ for _ in ()).throw(AssertionError('no OCR expected')))
    ctx, work = _ctx(tmp_path, source)
    P.extract_pdf(ctx); ctx.close()
    result = (work / 'result.md').read_text(encoding='utf-8')
    assert 'Visible tender clause 2210 stays' in result and 'WATERMARK' not in result


def _span(text, x0, y0, alpha):
    chars = [{'c': c, 'bbox': (x0 + 6 * i, y0, x0 + 6 * i + 6, y0 + 12), 'origin': (x0 + 6 * i, y0 + 10)}
             for i, c in enumerate(text)]
    return {'text': text, 'size': 11, 'alpha': alpha, 'bbox': (x0, y0, x0 + 6 * len(text), y0 + 12), 'chars': chars}


def test_visible_text_and_lines_skip_transparent_spans():
    line = {'dir': (1, 0), 'spans': [_span('SECRET', 10, 10, 0), _span('Shown', 60, 10, 255)]}
    blocks = [{'type': 0, 'bbox': (10, 10, 200, 22), 'lines': [line]}]
    assert P._visible_text(None, blocks, []) == 'Shown'
    assert P._line_text(line, [], False) == 'Shown'


def test_table_cells_skip_transparent_characters():
    line = {'dir': (1, 0), 'spans': [_span('GHOST', 10, 10, 0), _span('Cell', 60, 10, 255)]}
    blocks = [{'type': 0, 'bbox': (10, 10, 200, 22), 'lines': [line]}]
    table = SimpleNamespace(rows=[SimpleNamespace(cells=[(0, 0, 300, 40)])])
    assert P._table_rows(table, blocks, []) == [['Cell']]
