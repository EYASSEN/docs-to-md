# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cleanup22: ruled-table cells are read by the ONNX OCR engine as well as Tesseract, and each
cell keeps the engine reading unless it is empty, in another script, Latin where Tesseract read
Arabic, or missing digit groups Tesseract found."""
import json, re, subprocess, sys
from pathlib import Path
import pytest
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from foldertomd import ocr as O, ocrengine as E

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'pdf' / 'boq-sample.pdf'
AMOUNTS = ['4,850', '18.50', '89,725.00', '3,920', '22.00', '86,240.00', '1,260', '410.00', '516,600.00',
           '385', '1,150.00', '442,750.00', '2,140', '27.50', '58,850.00', '46', '3,800.00', '174,800.00',
           '120', '950.00', '114,000.00', '12.00', '15,120.00', '1,498,085.00']


def _w(*texts):
    return [{'text': t, 'conf': '95'} for t in texts]


@pytest.mark.parametrize('engine,tesseract,keep', [
    (_w('86,240.00'), _w('000100'), True),             # number cell: engine number wins
    (_w('1,260'), _w('1.260'), True),
    ([], _w('م3'), False),                              # engine found nothing
    (_w('3ρ'), _w('م3'), False),                        # Greek letter for an Arabic unit
    (_w('3e'), _w('م3'), False),                        # Latin letters where Tesseract read Arabic
    (_w('aiell', '(ربال'), _w('الفئة', '(ريال)'), False),
    (_w('قطر', 'مم', 'شاملة'), _w('قطر', '600', 'مم', 'شاملة'), False),   # lost Latin digits in Arabic text
    (_w('قطر', '600', 'مم', 'شاملة'), _w('قطر', '600', 'مم', 'شامله'), True),
    (_w('Basket', 'Screen'), _w('Baskct', 'Scrccn'), True),
])
def test_cell_choice(engine, tesseract, keep):
    assert O.choose_engine_cell(engine, tesseract) is keep


class Run:
    """Tesseract stand-in: returns the next queued cell reading as TSV."""
    def __init__(self, texts):
        self.texts = list(texts)

    def __call__(self, data, args):
        text = self.texts.pop(0) if self.texts else ''
        body = 'level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'
        for i, word in enumerate(text.split()):
            body += f'5\t1\t1\t1\t1\t{i + 1}\t{10 + 40 * i}\t10\t30\t20\t60\t{word}\n'
        return subprocess.CompletedProcess(args, 0, body.encode('utf-8'), b'')


def test_grid_cells_take_engine_numbers_and_keep_tesseract_units(monkeypatch):
    monkeypatch.setattr(O, 'cell_content', lambda sub, *a: (sub, None))
    image = Image.new('RGB', (600, 120), 'white')
    grid = {'columns': 3, 'rows': [[(0, 0, (0, 0, 200, 100)), (1, 1, (200, 0, 400, 100)), (2, 2, (400, 0, 600, 100))]]}
    engine_cells = iter([E.rows_from_lines([(E_box(), '86,240.00', 0.97)]),
                         E.rows_from_lines([(E_box(), '3e', 0.9)]),
                         E.rows_from_lines([(E_box(), 'Excavation works', 0.95)])])
    rows, _ = O._grid_transcription(image, grid, Run(['000100', 'م3', 'Excavatlon works']), 'eng',
                                    engine_reader=lambda cell: next(engine_cells))
    assert rows[0] == ['86,240.00', 'م3', 'Excavation works']
    assert rows.ocr_review['engine_cells'] == 2


def E_box():
    import numpy as np
    return np.array([[10, 10], [190, 10], [190, 40], [10, 40]], dtype=np.float32)


def test_without_engine_the_grid_reads_as_before(monkeypatch):
    monkeypatch.setattr(O, 'cell_content', lambda sub, *a: (sub, None))
    image = Image.new('RGB', (400, 120), 'white')
    grid = {'columns': 2, 'rows': [[(0, 0, (0, 0, 200, 100)), (1, 1, (200, 0, 400, 100))]]}
    rows, _ = O._grid_transcription(image, grid, Run(['12.00', 'Item']), 'eng')
    assert rows[0] == ['12.00', 'Item'] and rows.ocr_review['engine_cells'] == 0


def _resources_ready():
    try:
        O.preflight({})
    except RuntimeError:
        return False
    return E.available()


@pytest.mark.skipif(not _resources_ready(), reason='bundled Tesseract and ONNX OCR models are needed')
def test_synthetic_scanned_boq_keeps_every_amount(tmp_path):
    """Invented 8-item Arabic BOQ, degraded like a photocopy. Revision 57 lost three amounts in
    the ruled table (86,240.00, 58,850.00 and 1,260) and the grand total's decimals."""
    from foldertomd.dispatch import extract
    source = tmp_path / 'source.pdf'
    source.write_bytes(FIXTURE.read_bytes())
    extract({'source': str(source), 'original_dir': str(tmp_path), 'source_root': str(tmp_path),
             'relative': 'boq-sample.pdf', 'work': str(tmp_path), 'asset_link': 'assets',
             'settings': {'language': 'ara+eng', 'ocr': 'auto', 'timeout': 3600, 'quality': 'standard',
                          'decode_fonts': True, 'ocr_engine': 'onnx'}})
    text = (tmp_path / 'result.md').read_text(encoding='utf-8')
    cells = re.findall(r'<td[^>]*>([^<]*)</td>', text)
    missing = [a for a in AMOUNTS if a not in cells]
    assert not missing, missing
    assert any('read by the ONNX OCR engine' in w for w in json.loads((tmp_path / 'response.json').read_text(encoding='utf-8'))['warnings'])
