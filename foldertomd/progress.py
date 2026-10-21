# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Overall progress by pages (Update21).

Page counts are read before the conversion starts. Office files are ZIP packages whose page, slide and
sheet counts sit in small XML parts, read here with the standard library. PDF page counts need PyMuPDF,
which runs only in the isolated worker process (mode "count"), like every other document parser.
Anything that cannot be counted gets an estimate from its file size.
"""
import json, os, re, time, zipfile
from pathlib import Path

PAGE_UNITS = {'Page', 'Slide', 'Sheet', 'Frame'}          # the main reading pass of a file
LEARN_UNITS = {'Sample page', 'Extra page', 'Line'}         # font learning before the reading pass
_XML_LIMIT = 4 << 20                                        # never inflate more than 4 MB of package XML

# rough bytes per page when nothing better is known
_BYTES_PER_PAGE = {'.pdf': 60000, '.doc': 25000, '.xls': 60000, '.ppt': 150000, '.docx': 30000, '.docm': 30000,
                   '.pptx': 200000, '.pptm': 200000, '.xlsx': 60000, '.xlsm': 60000,
                   '.txt': 3000, '.csv': 6000, '.tsv': 6000, '.md': 3000, '.html': 20000, '.htm': 20000}
IMAGES = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp'}


def estimate_pages(path):
    """Page estimate from the file size (at least 1)."""
    ext = Path(path).suffix.lower()
    if ext in IMAGES: return 1
    try: size = os.path.getsize(path)
    except OSError: return 1
    return max(1, min(100000, round(size / _BYTES_PER_PAGE.get(ext, 50000))))


def _part(z, name):
    info = z.getinfo(name)
    if info.file_size > _XML_LIMIT: raise ValueError('package part too large')
    return z.read(info).decode('utf-8', 'replace')


def count_package(path):
    """Pages of a DOCX, slides of a PPTX, sheets of an XLSX; None when the package says nothing."""
    ext = Path(path).suffix.lower()
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            if ext in ('.docx', '.docm'):
                if 'docProps/app.xml' in names:
                    m = re.search(r'<(?:\w+:)?Pages>\s*(\d+)\s*<', _part(z, 'docProps/app.xml'))
                    if m and int(m.group(1)) > 0: return int(m.group(1))
                if 'word/document.xml' in names:        # about 3,000 characters of XML per page
                    return max(1, round(z.getinfo('word/document.xml').file_size / 30000))
            elif ext in ('.pptx', '.pptm'):
                slides = [n for n in names if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)]
                if slides: return len(slides)
            elif ext in ('.xlsx', '.xlsm'):
                sheets = [n for n in names if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', n)]
                if sheets: return len(sheets)
    except (OSError, zipfile.BadZipFile, ValueError, KeyError, RuntimeError):
        return None
    return None


def count_in_process(path):
    """Counts that need no native document parser; None for PDFs and legacy binaries."""
    ext = Path(path).suffix.lower()
    if ext in ('.tif','.tiff'): return None   # multi-frame image parser stays in the worker
    if ext in IMAGES: return 1
    if ext in ('.docx', '.docm', '.pptx', '.pptm', '.xlsx', '.xlsm'): return count_package(path) or estimate_pages(path)
    if ext == '.pdf': return None
    return estimate_pages(path)


def count_pdf(path):
    """PDF page count with PyMuPDF (worker process only)."""
    import pymupdf as fitz
    try:
        with fitz.open(path) as doc: return max(1, doc.page_count)
    except Exception:
        # Long or unusual paths: let Python open the file and give PyMuPDF the bytes
        if os.path.getsize(path) > (300 << 20): return None
        with open(path, 'rb') as f: data = f.read()
        with fitz.open(stream=data, filetype='pdf') as doc: return max(1, doc.page_count)


def count_request(request):
    """Worker entry (mode "count"): write {path: pages} to request['out'], every few files."""
    from .paths import atomic_json
    out = Path(request['out']); counts = {}
    for i, path in enumerate(request['files']):
        try:
            if Path(path).suffix.lower() in ('.tif','.tiff'):
                from PIL import Image
                with Image.open(path) as image: n=max(1,getattr(image,'n_frames',1))
            else: n = count_pdf(path)
        except Exception: n = None
        if n: counts[path] = n
        if i % 20 == 19: atomic_json(out, counts)
    atomic_json(out, counts)


class FileProgress:
    """Fraction (0..1) of the current file done, from its stage steps; never goes back."""
    def __init__(self): self.fraction = 0.0

    def update(self, unit, step, steps, completed=None):
        if unit not in PAGE_UNITS or not steps or step is None: return self.fraction
        # A Reading page N event starts that page. Only N-1 pages are finished.
        completed=max(0,float(step)-1) if completed is None else float(completed)
        value=max(0.0,min(1.0,completed/float(steps)))
        self.fraction = max(self.fraction, value)
        return self.fraction


def format_pages(done, total):
    return f'Page {min(int(done), int(total)):,} of {int(total):,}'


def format_pages_progress(done, total):
    """Page count plus the overall percentage for the GUI's single progress line."""
    total = max(0, int(total))
    done = min(max(0, float(done)), float(total)) if total else 0.0
    percent = (100.0 * done / total) if total else 0.0
    return f'{format_pages(done, total)} — {percent:.1f}%'


def load_counts(path):
    try: return {k: int(v) for k, v in json.loads(Path(path).read_text(encoding='utf-8')).items() if int(v) > 0}
    except (OSError, ValueError, TypeError, AttributeError): return {}
