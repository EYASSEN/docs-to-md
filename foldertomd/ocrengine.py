# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cleanup17: offline text detection and recognition with PP-OCR ONNX models, without OpenCV.

Follows the RapidOCR 3.10 pipeline (Apache-2.0): DB text detection, perspective crop of each
box, CTC line recognition. OpenCV calls are replaced by NumPy, Pillow and pyclipper so the
Windows package does not have to ship OpenCV. Models live in vendor/ocr-onnx:
det.onnx (PP-OCRv6 det small, int8), rec_en.onnx (PP-OCRv6 rec small), rec_ar.onnx
(arabic PP-OCRv5 rec mobile, int8). read() returns words in the Tesseract TSV row format so the
existing layout, table and output steps work unchanged. From source, the models are read from ocr-models.
"""
import math
import threading
import numpy as np
import pyclipper
from PIL import Image
from .runtime import resources, app_root


def session(path, threads=None):
    import onnxruntime as ort
    ort.disable_telemetry_events()   # Cleanup17b: the app is offline; no ONNX Runtime telemetry events
    options = ort.SessionOptions()
    options.log_severity_level = 3
    if threads:
        options.intra_op_num_threads = threads
    return ort.InferenceSession(str(path), sess_options=options, providers=['CPUExecutionProvider'])


# ---------------------------------------------------------------- geometry helpers

def _hull(points):
    """Monotone-chain convex hull of integer points (N, 2), counter-clockwise."""
    pts = np.unique(points, axis=0)
    if len(pts) < 3:
        return pts.astype(np.float64)
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))].tolist()

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1], dtype=np.float64)


def min_area_rect(points):
    """Smallest rotated rectangle around the points: (corners (4, 2), short side)."""
    hull = _hull(np.asarray(points).reshape(-1, 2))
    if len(hull) == 1:
        p = hull[0]
        return np.array([p, p, p, p]), 0.0
    if len(hull) == 2:
        a, b = hull
        return np.array([a, b, b, a]), 0.0
    edges = np.roll(hull, -1, axis=0) - hull
    angles = np.unique(np.mod(np.arctan2(edges[:, 1], edges[:, 0]), np.pi / 2))
    best = None
    for t in angles:
        c, s = math.cos(t), math.sin(t)
        rot = hull @ np.array([[c, -s], [s, c]])
        x0, y0 = rot.min(axis=0)
        x1, y1 = rot.max(axis=0)
        area = (x1 - x0) * (y1 - y0)
        if best is None or area < best[0]:
            best = (area, t, x0, y0, x1, y1)
    _, t, x0, y0, x1, y1 = best
    c, s = math.cos(t), math.sin(t)
    corners = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]) @ np.array([[c, s], [-s, c]])
    return corners, min(x1 - x0, y1 - y0)


def mini_box(points):
    """RapidOCR get_mini_boxes: rectangle corners ordered tl, tr, br, bl and its short side."""
    corners, short = min_area_rect(points)
    pts = sorted(corners.tolist(), key=lambda p: p[0])
    i1, i4 = (0, 1) if pts[1][1] > pts[0][1] else (1, 0)
    i2, i3 = (2, 3) if pts[3][1] > pts[2][1] else (3, 2)
    return np.array([pts[i1], pts[i2], pts[i3], pts[i4]]), short


def _polygon_mask(poly, h, w):
    """Boolean mask of pixel centres inside a convex polygon (h x w), edges included."""
    ys, xs = np.mgrid[0:h, 0:w]
    pos = np.ones((h, w), dtype=bool)
    neg = np.ones((h, w), dtype=bool)
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        cross = (x1 - x0) * (ys - y0) - (y1 - y0) * (xs - x0)
        tol = 0.5 * math.hypot(x1 - x0, y1 - y0)
        pos &= cross >= -tol
        neg &= cross <= tol
    return pos | neg


def box_score(pred, box):
    h, w = pred.shape
    xmin = int(np.clip(np.floor(box[:, 0].min()), 0, w - 1))
    xmax = int(np.clip(np.ceil(box[:, 0].max()), 0, w - 1))
    ymin = int(np.clip(np.floor(box[:, 1].min()), 0, h - 1))
    ymax = int(np.clip(np.ceil(box[:, 1].max()), 0, h - 1))
    local = box - [xmin, ymin]
    mask = _polygon_mask(np.round(local).tolist(), ymax - ymin + 1, xmax - xmin + 1)
    region = pred[ymin:ymax + 1, xmin:xmax + 1]
    return float(region[mask].mean()) if mask.any() else 0.0


def unclip(box, ratio):
    x, y = box[:, 0], box[:, 1]
    area = abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2
    length = np.sum(np.hypot(*(np.roll(box, -1, axis=0) - box).T))
    offset = pyclipper.PyclipperOffset()
    offset.AddPath(box.tolist(), pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
    out = offset.Execute(area * ratio / length) if length else []
    return np.array(out[0] if out else box).reshape(-1, 2)


def components(mask):
    """8-connected components of a boolean mask as lists of (y, x_start, x_end) runs."""
    parent = []

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    runs = []
    prev = []
    for y in range(mask.shape[0]):
        row = mask[y]
        if not row.any():
            prev = []
            continue
        d = np.diff(np.concatenate(([0], row.view(np.int8), [0])))
        starts = np.flatnonzero(d == 1)
        ends = np.flatnonzero(d == -1) - 1
        cur = []
        j = 0
        for s, e in zip(starts.tolist(), ends.tolist()):
            label = len(parent)
            parent.append(label)
            while j < len(prev) and prev[j][1] < s - 1:
                j += 1
            k = j
            while k < len(prev) and prev[k][0] <= e + 1:
                ra, rb = find(label), find(prev[k][2])
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
                k += 1
            runs.append((y, s, e, label))
            cur.append((s, e, label))
        prev = cur
    groups = {}
    for y, s, e, label in runs:
        groups.setdefault(find(label), []).append((y, s, e))
    return list(groups.values())


def order_clockwise(pts):
    xs = pts[np.argsort(pts[:, 0]), :]
    left, right = xs[:2], xs[2:]
    tl, bl = left[np.argsort(left[:, 1])]
    tr, br = right[np.argsort(right[:, 1])]
    return np.array([tl, tr, br, bl], dtype=np.float32)


# ---------------------------------------------------------------- detection

class Detector:
    def __init__(self, model, threads=None, thresh=0.3, box_thresh=0.5, unclip_ratio=1.6, limit_side_len=736,
                 max_side_len=3000):
        self.session = session(model, threads)
        self.thresh, self.box_thresh, self.unclip_ratio = thresh, box_thresh, unclip_ratio
        self.limit, self.max_side = limit_side_len, max_side_len

    def __call__(self, image, scale=None):
        """image: RGB PIL image. Returns int boxes (N, 4, 2) in image pixels, top-to-bottom.
        Very tall text (lines over 96 px, e.g. a large render) splits into overlapping boxes, so it is
        detected again on a copy scaled to 48 px lines; crops are always read from the full image."""
        w, h = image.size
        ratio = self.limit / min(h, w) if min(h, w) < self.limit else 1.0
        if self.max_side and max(h, w) * ratio > self.max_side:
            ratio = self.max_side / max(h, w)
        if scale:
            ratio = scale
        boxes = self._detect(image, ratio)
        if scale is None and len(boxes):
            heights = np.linalg.norm(boxes[:, 0] - boxes[:, 3], axis=1)
            tall = float(np.median(heights))
            if tall > 96:
                return self(image, max(0.05, ratio * 48 / tall))
        return boxes

    def _detect(self, image, ratio):
        w, h = image.size
        rh = int(round(int(h * ratio) / 32) * 32)
        rw = int(round(int(w * ratio) / 32) * 32)
        resized = np.asarray(image.resize((rw, rh), Image.BILINEAR), dtype=np.float32)[:, :, ::-1]
        x = ((resized / 255.0 - 0.5) / 0.5).transpose(2, 0, 1)[None].astype(np.float32)
        pred = self.session.run(None, {self.session.get_inputs()[0].name: x})[0][0, 0]
        seg = pred > self.thresh
        mask = seg.copy()
        mask[1:, :] |= seg[:-1, :]
        mask[:, 1:] |= seg[:, :-1]
        mask[1:, 1:] |= seg[:-1, :-1]
        boxes = []
        for comp in components(mask)[:1000]:
            pts = np.array([(s, y) for y, s, e in comp] + [(e, y) for y, s, e in comp])
            box, short = mini_box(pts)
            if short < 3:
                continue
            if box_score(pred, box) < self.box_thresh:
                continue
            box, short = mini_box(unclip(box, self.unclip_ratio))
            if short < 5:
                continue
            box[:, 0] = np.clip(np.round(box[:, 0] / rw * w), 0, w)
            box[:, 1] = np.clip(np.round(box[:, 1] / rh * h), 0, h)
            box = order_clockwise(box.astype(np.int32).astype(np.float32))
            box[:, 0] = np.clip(box[:, 0], 0, w - 1).astype(np.int32)
            box[:, 1] = np.clip(box[:, 1], 0, h - 1).astype(np.int32)
            if int(np.linalg.norm(box[0] - box[1])) <= 3 or int(np.linalg.norm(box[0] - box[3])) <= 3:
                continue
            boxes.append(box)
        if not boxes:
            return np.zeros((0, 4, 2), dtype=np.float32)
        boxes = np.array(boxes)
        y = boxes[:, 0, 1]
        order = np.argsort(y, kind='stable')
        boxes, y = boxes[order], y[order]
        lines = np.concatenate([[0], np.cumsum(np.diff(y) >= 10)])
        return boxes[np.lexsort((boxes[:, 0, 0], lines))]


def perspective_coeffs(src, dst):
    """PIL PERSPECTIVE coefficients mapping output points dst to input points src."""
    a = []
    for (x, y), (u, v) in zip(dst, src):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    return np.linalg.solve(np.array(a, dtype=np.float64), np.array(src, dtype=np.float64).reshape(8)).tolist()


def crop(image, box):
    w = int(max(np.linalg.norm(box[0] - box[1]), np.linalg.norm(box[2] - box[3])))
    h = int(max(np.linalg.norm(box[0] - box[3]), np.linalg.norm(box[1] - box[2])))
    w, h = max(w, 1), max(h, 1)
    dst = [(0, 0), (w, 0), (w, h), (0, h)]
    out = image.transform((w, h), Image.PERSPECTIVE, perspective_coeffs(box.tolist(), dst), Image.BICUBIC)
    if h / w >= 1.5:
        out = out.transpose(Image.ROTATE_90)
    return out


# ---------------------------------------------------------------- recognition

class Recognizer:
    def __init__(self, model, threads=None, rtl=False, batch=6, height=48, width=320):
        self.session = session(model, threads)
        meta = self.session.get_modelmeta().custom_metadata_map
        self.chars = ['blank'] + meta['character'].splitlines() + [' ']
        self.rtl, self.batch, self.height, self.width = rtl, batch, height, width

    def _norm(self, img, max_ratio):
        target = int(self.height * max_ratio)
        w, h = img.size
        rw = min(target, int(math.ceil(self.height * w / float(h))))
        arr = np.asarray(img.resize((rw, self.height), Image.BILINEAR), dtype=np.float32)[:, :, ::-1]
        arr = (arr.transpose(2, 0, 1) / 255 - 0.5) / 0.5
        out = np.zeros((3, self.height, target), dtype=np.float32)
        out[:, :, :rw] = arr
        return out

    def __call__(self, crops):
        """crops: RGB PIL images. Returns [(text, confidence)] in the same order."""
        ratios = [c.size[0] / float(c.size[1]) for c in crops]
        order = np.argsort(np.array(ratios))
        out = [('', 0.0)] * len(crops)
        for b in range(0, len(crops), self.batch):
            idx = order[b:b + self.batch]
            max_ratio = max([self.width / self.height] + [ratios[i] for i in idx])
            x = np.stack([self._norm(crops[i], max_ratio) for i in idx])
            pred = self.session.run(None, {self.session.get_inputs()[0].name: x})[0]
            ids, probs = pred.argmax(axis=2), pred.max(axis=2)
            for n, i in enumerate(idx):
                t = ids[n]
                keep = np.ones(len(t), dtype=bool)
                keep[1:] = t[1:] != t[:-1]
                keep &= t != 0
                conf = probs[n][keep]
                text = ''.join(self.chars[k] for k in t[keep])
                out[i] = (text, float(np.round(conf.mean(), 5)) if len(conf) else 0.0)
        if self.rtl:
            from bidi.algorithm import get_display
            out = [(get_display(t), s) for t, s in out]
        return out


# ---------------------------------------------------------------- page reading

MODELS = ('det.onnx', 'rec_en.onnx', 'rec_ar.onnx')
ARABIC = ('\u0600', '\u06ff')
_engines = {}
_lock = threading.Lock()


def model_dir():
    """vendor/ocr-onnx in the portable build; the source tree's ocr-models folder when run from source."""
    bundled = resources() / 'ocr-onnx'
    return bundled if bundled.is_dir() else app_root() / 'ocr-models'


def available():
    try:
        import onnxruntime  # noqa: F401
    except Exception:
        return False
    return all((model_dir() / name).is_file() for name in MODELS)


def _latin_arabic(value):
    """Drop CJK characters: the multilingual English model reads icons and boxes as Chinese, and the
    app reads only Arabic and English."""
    import unicodedata
    value = ''.join(unicodedata.normalize('NFKC', c) if '\uff01' <= c <= '\uff5e' else c for c in value)
    return ''.join(c for c in value if not ('\u2e80' <= c <= '\u9fff' or '\uf900' <= c <= '\ufaff'
                                            or '\uac00' <= c <= '\ud7af'))


def _arabic_share(value):
    letters = [c for c in value if c.isalpha()]
    return sum(ARABIC[0] <= c <= ARABIC[1] for c in letters) / max(1, len(letters)), len(letters)


class Engine:
    def __init__(self, threads=None):
        root = model_dir()
        self.det = Detector(root / 'det.onnx', threads)
        self.en = Recognizer(root / 'rec_en.onnx', threads)
        self.ar = Recognizer(root / 'rec_ar.onnx', threads, rtl=True)

    def lines(self, image, language='ara+eng'):
        """[(box (4, 2), text, confidence 0-1)] for one RGB image. English reading first; the Arabic
        recogniser reads boxes the English one is unsure of, and wins when its reading is mostly Arabic."""
        boxes = self.det(image)
        if not len(boxes):
            return []
        crops = [crop(image, b) for b in boxes]
        langs = set(language.split('+'))
        if 'eng' in langs:
            first = self.en(crops)
        else:
            first = [('', 0.0)] * len(crops)
        need = [i for i, (t, s) in enumerate(first)
                if 'ara' in langs and (s < 0.9 or any(ord(c) > 0x2e80 for c in t))]
        second = [('', 0.0)] * len(crops)
        for i, r in zip(need, self.ar([crops[i] for i in need]) if need else []):
            second[i] = r
        out = []
        first = [(_latin_arabic(t), s) for t, s in first]
        second = [(_latin_arabic(t), s) for t, s in second]
        for b, (t1, s1), (t2, s2) in zip(boxes, first, second):
            share, letters = _arabic_share(t2)
            if letters and share >= 0.5 and s2 >= 0.5:
                out.append((b, t2.strip(), s2))
            elif t1.strip() and s1 >= 0.5:
                out.append((b, t1.strip(), s1))
        return out

    def read(self, image, language='ara+eng'):
        """Tesseract-style TSV word rows (dicts of strings) for one RGB image."""
        return rows_from_lines(self.lines(image, language))


def engine(threads=None):
    """One shared engine per process; ONNX Runtime sessions are safe to run from several threads."""
    with _lock:
        if threads not in _engines:
            _engines[threads] = Engine(threads)
        return _engines[threads]


def rows_from_lines(found):
    """Group detected boxes into visual lines and split each box into words with estimated positions.
    Word order is logical: right-to-left lines (mostly Arabic) list their rightmost box first."""
    items = []
    for b, value, score in found:
        x0, y0 = float(b[:, 0].min()), float(b[:, 1].min())
        x1, y1 = float(b[:, 0].max()), float(b[:, 1].max())
        items.append(((y0 + y1) / 2, x0, y0, x1, y1, value, score))
    items.sort()
    groups, current, cy, ch = [], [], None, None
    for item in items:
        h = item[4] - item[2]
        if current and abs(item[0] - cy) > 0.5 * max(ch, h):
            groups.append(current)
            current = []
        if not current:
            cy, ch = item[0], h
        current.append(item)
    if current:
        groups.append(current)
    rows = []
    for n, group in enumerate(groups, 1):
        joined = ' '.join(g[5] for g in group)
        share, letters = _arabic_share(joined)
        rtl = letters and share >= 0.5
        group.sort(key=lambda g: -g[1] if rtl else g[1])
        word = 0
        for _, x0, y0, x1, y1, value, score in group:
            words = value.split()
            box_rtl = _arabic_share(value)[0] >= 0.5
            total = sum(len(w) for w in words) + max(0, len(words) - 1)
            pos = 0
            for w in words:
                a, z = pos / max(1, total), (pos + len(w)) / max(1, total)
                pos += len(w) + 1
                left, right = (x1 - z * (x1 - x0), x1 - a * (x1 - x0)) if box_rtl else (x0 + a * (x1 - x0), x0 + z * (x1 - x0))
                word += 1
                rows.append({'level': '5', 'page_num': '1', 'block_num': str(n), 'par_num': '1', 'line_num': '1',
                             'word_num': str(word), 'left': str(int(round(left))), 'top': str(int(round(y0))),
                             'width': str(max(1, int(round(right - left)))), 'height': str(max(1, int(round(y1 - y0)))),
                             'conf': f'{100 * score:.2f}', 'text': w})
    return rows


def fingerprint():
    """Model hashes for the conversion identity."""
    from .paths import sha256
    return {('ocr-onnx/' + p.name): sha256(p) for p in sorted(model_dir().glob('*.onnx'))}
