# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Update21: page counts and time left for the overall progress, report header, output comparison.
All files are built by the tests themselves."""
import json, sys, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'scripts'))
from foldertomd import progress as P


def _zip(path, parts):
    with zipfile.ZipFile(path, 'w') as z:
        for name, data in parts.items(): z.writestr(name, data)
    return path


def test_office_packages_are_counted_without_a_document_parser(tmp_path):
    docx = _zip(tmp_path / 'a.docx', {'docProps/app.xml': '<Properties><Pages>12</Pages></Properties>', 'word/document.xml': 'x'})
    pptx = _zip(tmp_path / 'b.pptx', {f'ppt/slides/slide{i}.xml': '<p/>' for i in range(1, 8)} | {'ppt/slides/_rels/slide1.xml.rels': ''})
    xlsx = _zip(tmp_path / 'c.xlsx', {'xl/worksheets/sheet1.xml': '', 'xl/worksheets/sheet2.xml': ''})
    nopages = _zip(tmp_path / 'd.docx', {'word/document.xml': 'x' * 90000})
    assert P.count_in_process(docx) == 12
    assert P.count_in_process(pptx) == 7
    assert P.count_in_process(xlsx) == 2
    assert P.count_in_process(nopages) == 3                     # estimated from the document part
    assert P.count_in_process(tmp_path / 'e.pdf') is None       # PDFs are counted in the worker only
    broken = tmp_path / 'f.docx'; broken.write_bytes(b'not a zip' * 10000)
    assert P.count_in_process(broken) >= 1                      # falls back to a size estimate


def test_size_estimates():
    assert P.estimate_pages('missing.pdf') == 1
    assert P.estimate_pages('photo.jpg') == 1


def test_pdf_count_in_worker_mode(tmp_path):
    import pymupdf as fitz
    from foldertomd.dispatch import extract
    doc = fitz.open()
    for _ in range(5): doc.new_page()
    doc.save(tmp_path / 'five.pdf')
    (tmp_path / 'bad.pdf').write_bytes(b'%PDF-1.4 broken')
    out = tmp_path / 'counts.json'
    extract({'mode': 'count', 'files': [str(tmp_path / 'five.pdf'), str(tmp_path / 'bad.pdf')], 'out': str(out)})
    counts = json.loads(out.read_text(encoding='utf-8'))
    assert counts[str(tmp_path / 'five.pdf')] == 5
    assert str(tmp_path / 'bad.pdf') not in counts


def test_count_pages_falls_back_when_the_worker_cannot_start(tmp_path, monkeypatch):
    import foldertomd.engine as engine
    (tmp_path / 'a.txt').write_text('x')
    (tmp_path / 'b.pdf').write_bytes(b'x' * 120000)
    (tmp_path / 'c.xyz').write_text('x')
    def fail(*a, **k): raise OSError('no worker here')
    monkeypatch.setattr(engine, 'JobProcess', fail)
    import threading
    pages = engine.count_pages(tmp_path, ['a.txt', 'b.pdf', 'c.xyz'], tmp_path, threading.Event(), lambda e: None)
    assert pages == {'a.txt': 1, 'b.pdf': 2, 'c.xyz': 0}
    assert not any(p.name.startswith('count-') for p in tmp_path.iterdir())    # workspace removed


def test_file_progress_learning_then_reading_never_goes_back():
    f = P.FileProgress()
    assert f.update('Sample page', 20, 40) == 0
    assert f.update('Extra page', 1, 16) == 0                 # font learning is not completed document pages
    assert abs(f.update('Page', 38, 76) - 37/76) < 1e-9
    assert f.update('Page', 38, 76, completed=38) == 0.5
    assert f.update('Step', 1, 2) == f.fraction                  # unknown units do not move it
    g = P.FileProgress()
    assert g.update('Page', 3, 4) == 0.5                         # third page is still being read


def test_page_count_text():
    assert P.format_pages(1240.6, 3860) == 'Page 1,240 of 3,860'


def test_middle_shortening():
    from foldertomd.gui import _middle
    class Font:                                                  # one pixel per character
        def measure(self, text): return len(text)
    name = 'Example Project/02 Technical/Electromechanical specifications.pdf'
    short = _middle(name, Font(), 30)
    assert len(short) <= 30 and short.startswith('Example') and short.endswith('.pdf') and '…' in short
    assert _middle('short.pdf', Font(), 30) == 'short.pdf'


def test_report_starts_with_name_version_and_link(tmp_path):
    from foldertomd import __version__
    from foldertomd.engine import reports, HOMEPAGE
    meta = tmp_path / 'meta'; meta.mkdir()
    reports(tmp_path, meta, {'files': {'a.txt': {'status': 'converted', 'output': 'a.txt.md'}}, 'elapsed_seconds': 1})
    first = (meta / 'conversion_report.md').read_text(encoding='utf-8').splitlines()[0]
    assert first == f'Docs to MD {__version__} by Yassin Abd El Aal — {HOMEPAGE}'
    assert __version__ == '1.1.0'


def test_compare_outputs(tmp_path, capsys):
    import compare_outputs
    old = tmp_path / 'old'; new = tmp_path / 'new'; old.mkdir(); new.mkdir()
    (old / 'x.pdf.md').write_text('في اليأام الفاصلة ![Page 1](.data/a.png)', encoding='utf-8')
    (new / 'x.pdf.md').write_text('في الأيام الفاصلة ![Page 1](.data/b.png)', encoding='utf-8')
    (old / 'gone.md').write_text('a', encoding='utf-8')
    compare_outputs.main([str(old), str(new), '--out', str(tmp_path / 'c.md')])
    out = (tmp_path / 'c.md').read_text(encoding='utf-8')
    assert '| x.pdf.md | 3 | 3 | 1 | 66.7% |' in out
    assert '| 1 | اليأام | الأيام |' in out
    assert '| gone.md | - | missing | - | - |' in out
