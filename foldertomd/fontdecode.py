# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Decode legacy Arabic PDF fonts (1990s Windows "MSTT" fonts with no Unicode map).

Such PDFs contain real text, but each glyph is stored under a private code. The code of a
glyph is the same on every page, so the mapping can be learned once per document:

1. OCR a sample of pages and pair each OCR word with the glyph codes drawn inside its box.
2. Align glyph sequences to letters (a glyph may be a letter, a ligature of two letters, or a
   kashida stretch) and keep the most frequent reading of every glyph.
3. Identify digits and punctuation by shape, because OCR misreads Arabic digits.
4. Read every page straight from its glyph codes; pages with too many unknown glyphs fall
   back to OCR.

The result is usually more accurate than OCR (numbers especially) and much faster.
"""
import collections, csv, io, math, os, re, unicodedata
import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFont

AR = re.compile('[\u0600-\u06ff]')
LETTERS = re.compile('[\u0621-\u064a]')
LETTER = re.compile('^[\u0621-\u064a\u0671-\u06d3]+$')
LTR = re.compile(r'^[0-9A-Za-z\u0660-\u0669\u06f0-\u06f9/%\-]+$')   # '.' and ',' are neutral (joined only between digits)   # brackets are mirrored instead
SHAPE_CHARS = '٠١٢٣٤٥٦٧٨٩-()/.:،؛%'
def decimal_marks(text):
    """A comma glued between digits is a decimal mark (٥،٢ -> ٥٫٢). Exactly three digits after it
    (٢،١٢٥, ٥٠٠،٠٠٠) could be a thousands separator, so those stay as they are (Update11)."""
    return re.sub(r'(?<=[٠-٩])،(?=[٠-٩]{1,2}(?![٠-٩])|[٠-٩]{4,})', '٫', text)

DIGITS = set('٠١٢٣٤٥٦٧٨٩0123456789')
LOOKALIKE = 'اهوىدر'          # letters whose shape resembles a digit or dot
MIN_KNOWN = 0.97              # share of glyphs a page must decode, or it falls back to OCR


def legacy_font(name):
    return name.split('+')[-1].startswith('MSTT')


# ---------------------------------------------------------------- glyph identity
class GlyphNames:
    """Maps (page, font name, code) to (font name, original glyph name).

    Several font objects in one PDF can share a name (MSTT31c40c00 on page 3 and on page 40)
    while numbering their glyphs differently, so every page is looked up through its own font
    objects. The glyph name (G3A = original glyph 0x3A) is the stable identity of a glyph."""
    def __init__(self, doc):
        self.enc = {}; self.pages = {}; self.doc = doc
        for i in range(len(doc)):
            fonts = {}
            for xref, ext, typ, name, *rest in doc.get_page_fonts(i):
                base = name.split('+')[-1]
                if not self._legacy_font(doc, xref, typ, base): continue
                fonts[base] = xref
                if xref not in self.enc: self.enc[xref] = self._encoding(doc, xref, typ)
            self.pages[i] = fonts

    @staticmethod
    def _legacy_font(doc, xref, typ, base):
        """Old Windows "MSTT" fonts, and Type3 fonts without a Unicode map (drawn glyph by glyph)."""
        if base.startswith('MSTT'): return True
        if typ == 'Type3':
            try: return '/ToUnicode' not in doc.xref_object(xref)
            except Exception: return False
        return False

    def legacy(self, page_number, font):
        return font in self.pages.get(page_number, {})

    @staticmethod
    def _encoding(doc, xref, typ='Type1'):
        table = {}
        try:
            obj = doc.xref_object(xref)
            m = re.search(r'/Encoding\s+(\d+)\s+0\s+R', obj)
            enc = doc.xref_object(int(m.group(1))) if m else obj
            diff = re.search(r'/Differences\s*\[(.*?)\]', enc, re.S)
        except Exception:
            return table
        if diff:
            code = 0
            for tok in re.findall(r'\d+|/[^\s/\[\]]+', diff.group(1)):
                if tok[0] == '/': table[code] = tok[1:]; code += 1
                else: code = int(tok)
        if typ == 'Type3':
            # Type3 glyph names are arbitrary, but each glyph is a small drawing program: two
            # glyphs with the same program are the same glyph, on any page and in any font object.
            try:
                procs = re.search(r'/CharProcs\s+(\d+)\s+0\s+R', obj)
                cp = doc.xref_object(int(procs.group(1))) if procs else re.search(r'/CharProcs\s*<<(.*?)>>', obj, re.S).group(1)
                refs = dict(re.findall(r'/([^\s/]+)\s+(\d+)\s+0\s+R', cp))
                import hashlib
                table = {code: 'P' + hashlib.md5(doc.xref_stream(int(refs[g])) or b'').hexdigest()[:12]
                         for code, g in table.items() if g in refs}
            except Exception:
                return {}
        return table

    def key(self, page_number, font, code):
        xref = self.pages.get(page_number, {}).get(font)
        name = self.enc.get(xref, {}).get(code) if xref else None
        if name and name.startswith('P'): return ('type3', name)   # same drawing = same glyph
        return (font, name) if name else (font, code)

    def __len__(self):
        return sum(len(v) for v in self.enc.values())


def glyph_names(doc):
    return GlyphNames(doc)


def page_glyphs(page, names):
    """Every drawn character: (key, is_legacy, bbox, origin, size, char)."""
    out = []
    for block in page.get_text('rawdict')['blocks']:
        if block['type'] != 0: continue
        for line in block['lines']:
            for span in line['spans']:
                legacy = names.legacy(page.number, span['font'])
                for c in span['chars']:
                    k = names.key(page.number, span['font'], ord(c['c'])) if legacy else None
                    out.append((k, legacy, c['bbox'], c['origin'], span['size'], c['c']))
    return out


def has_ink(page, bbox):
    # look only at the middle of the box, so ink from touching neighbours is not counted
    r = fitz.Rect(bbox); dx = r.width*0.25; dy = r.height*0.15
    r = fitz.Rect(r.x0+dx, r.y0+dy, r.x1-dx, r.y1-dy)
    if r.is_empty: return False
    pix = page.get_pixmap(dpi=300, clip=r, alpha=False, colorspace=fitz.csGRAY)
    return min(pix.samples) < 128 if pix.samples else False


# ---------------------------------------------------------------- learning
def _clean(t):
    return ''.join(c for c in t if unicodedata.category(c) != 'Cf').replace('ـ', '')


def training_pairs(page, names, words, blank):
    """Pair OCR words (text, conf, box in PDF points) with the glyph keys inside each box."""
    glyphs = [g for g in page_glyphs(page, names) if g[1] and g[0] not in blank]
    pairs = []
    for text, conf, box in words:
        t = _clean(text)
        if conf < 85 or not t or not AR.search(t): continue
        inside = [g for g in glyphs if box[0]-1.5 <= (g[2][0]+g[2][2])/2 <= box[2]+1.5 and box[1]-1.5 <= (g[2][1]+g[2][3])/2 <= box[3]+1.5]
        if not inside: continue
        inside.sort(key=lambda g: -g[3][0])          # right to left = reading order for Arabic
        seq = [g[0] for g in inside]
        if len(seq) <= 2*len(t)+2 and len(t) <= 2*len(seq)+1: pairs.append((seq, t))
    return pairs


def learn(pairs, iterations=4):
    """Monotone alignment of glyph sequences to letters; each glyph emits 0, 1 or 2 letters."""
    counts = collections.defaultdict(collections.Counter)
    for seq, t in pairs:
        if len(seq) == len(t):
            for k, ch in zip(seq, t): counts[k][ch] += 1
    chars = {c for _, t in pairs for c in t} or {'ا'}
    prior = {0: 0.02, 1: 0.9/len(chars), 2: 0.3/len(chars)}
    for _ in range(iterations):
        table = {k: (cn, sum(cn.values())) for k, cn in counts.items()}
        def lp(k, s):
            cn, tot = table.get(k, (None, 0))
            return math.log(((cn[s] if cn else 0) + 0.5*prior[len(s)]) / (tot + 0.5))
        new = collections.defaultdict(collections.Counter)
        for seq, t in pairs:
            n, m = len(seq), len(t); NEG = -1e9
            S = [[NEG]*(m+1) for _ in range(n+1)]; B = [[None]*(m+1) for _ in range(n+1)]; S[0][0] = 0
            for i in range(n+1):
                for j in range(m+1):
                    v = S[i][j]
                    if v == NEG: continue
                    if j < m and v-16 > S[i][j+1]: S[i][j+1] = v-16; B[i][j+1] = (i, j, None)
                    if i < n:
                        for L in (0, 1, 2):
                            if j+L <= m:
                                sc = v + lp(seq[i], t[j:j+L])
                                if sc > S[i+1][j+L]: S[i+1][j+L] = sc; B[i+1][j+L] = (i, j, t[j:j+L])
            if S[n][m] < -6*(n+m): continue
            i, j = n, m
            while (i, j) != (0, 0):
                pi, pj, s = B[i][j]
                if s is not None: new[seq[pi]][s] += 1
                i, j = pi, pj
        counts = new
    return {k: cn.most_common(1)[0][0] for k, cn in counts.items()}, counts


# ---------------------------------------------------------------- digits by shape
def _norm(img, size=32):
    """Crop to ink, pad to a square, scale to size x size. Pure PIL (numpy is not bundled)."""
    from PIL import ImageOps, ImageChops, ImageStat
    g = ImageOps.invert(img.convert('L')).point(lambda p: 255 if p > 127 else 0)
    box = g.getbbox()
    if not box: return None
    g = g.crop(box); w, h = g.size; side = max(w, h)
    sq = Image.new('L', (side, side), 0); sq.paste(g, ((side-w)//2, (side-h)//2))
    v = sq.resize((size, size), Image.BILINEAR)
    energy = ImageStat.Stat(ImageChops.multiply(v, v)).sum[0]
    return v, w/h, energy


def _similarity(a, b):
    from PIL import ImageChops, ImageStat
    (v, ar, ea), (r, rar, er) = a, b
    dot = ImageStat.Stat(ImageChops.multiply(v, r)).sum[0]
    return dot/math.sqrt(ea*er+1e-9) - 0.15*abs(math.log((ar+1e-3)/(rar+1e-3)))


def reference_fonts():
    folders = [os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts'), os.path.join(os.path.dirname(__file__), 'fonts')]
    names = ('trado.ttf', 'simpo.ttf', 'arabtype.ttf', 'times.ttf', 'arial.ttf', 'tahoma.ttf', 'segoeui.ttf',
             'Amiri-Regular.ttf', 'ScheherazadeNew-Regular.ttf', 'NotoNaskh.ttf', 'Lateef-Regular.ttf')
    return [os.path.join(d, n) for d in folders for n in names if os.path.isfile(os.path.join(d, n))]


def shape_references(paths=()):
    """Built-in templates first (same on every PC), then any extra fonts given."""
    import base64
    from PIL import ImageChops, ImageStat
    from .shape_templates import TEMPLATES
    refs = []
    for ch, data, ratio in TEMPLATES:
        v = Image.open(io.BytesIO(base64.b64decode(data))).convert('L')
        refs.append((ch, (v, ratio, ImageStat.Stat(ImageChops.multiply(v, v)).sum[0])))
    for path in paths:
        try: font = ImageFont.truetype(path, 160)
        except OSError: continue
        for ch in SHAPE_CHARS + LOOKALIKE:
            im = Image.new('L', (420, 420), 255); ImageDraw.Draw(im).text((110, 90), ch, font=font, fill=0)
            n = _norm(im)
            if n: refs.append((ch, n))
    return refs


def classify_shape(page, bbox, refs, digits_only=False, minimum_margin=0):
    r = fitz.Rect(bbox) + (-0.5, -0.5, 0.5, 0.5)
    pix = page.get_pixmap(dpi=600, clip=r, alpha=False)
    n = _norm(Image.open(io.BytesIO(pix.tobytes('png'))))
    if not n: return None
    best = {}
    for ch, ref in refs:
        if digits_only and ch not in '٠١٢٣٤٥٦٧٨٩': continue
        best[ch] = max(best.get(ch, -9), _similarity(n, ref))
    if digits_only:
        ranked = sorted(best.items(), key=lambda x: -x[1])
        return ranked[0] if ranked and ranked[0][1] >= 0.8 and (len(ranked)<2 or ranked[0][1]-ranked[1][1]>=minimum_margin) else None
    ranked = sorted(best.items(), key=lambda x: -x[1])
    (c1, s1), (c2, s2) = ranked[0], ranked[1]
    if c1 in LOOKALIKE or s1 < 0.75 or s1 - s2 < 0.06: return None
    return c1, s1


# ---------------------------------------------------------------- the model
def _gutter(glyphs, width):
    """x of an empty vertical band between two columns of text, or None for one column.
    Conservative: a single line crossing the middle (a full-width heading) means one column."""
    inked = [g for g in glyphs if g[1] or g[5].strip()]
    if len(inked) < 200: return None
    lo, hi = width*0.3, width*0.7; step = 2.0
    bins = [0]*int((hi-lo)/step+1)
    for g in inked:
        a, b = max(g[2][0], lo), min(g[2][2], hi)
        if b < a: continue
        for n in range(int((a-lo)/step), int((b-lo)/step)+1):
            if 0 <= n < len(bins): bins[n] += 1
    best = None; run = 0
    for n, v in enumerate(bins):
        run = run+1 if v == 0 else 0
        if run*step >= 12: best = lo+(n-run/2)*step
    if best is None: return None
    left = [g for g in inked if g[2][2] <= best]; right = [g for g in inked if g[2][0] >= best]
    if min(len(left), len(right)) < 0.25*len(inked): return None
    # real text columns have long lines; a borderless table (item | description | unit) has short cells
    def per_line(gs):
        rows = collections.Counter(round(g[3][1]/3) for g in gs)
        return sum(rows.values())/len(rows) if rows else 0
    return best if min(per_line(left), per_line(right)) >= 25 else None


class FontModel:
    def __init__(self, doc):
        self.doc = doc; self.names = glyph_names(doc); self.mapping = {}; self.counts = {}; self.blank = set(); self.markers = set()

    def usable(self):
        return bool(self.names)

    def find_spaces(self, pages):
        """Glyphs that draw nothing are word spaces; kashida and letters have ink."""
        inst = collections.defaultdict(list)
        for i in pages:
            page = self.doc[i]
            if page.rotation: continue
            for g in page_glyphs(page, self.names):
                if g[1] and len(inst[g[0]]) < 400: inst[g[0]].append((g[2][2]-g[2][0], i, g[2]))
        self._first = {k: (max(v)[1], max(v)[2]) for k, v in inst.items()}
        self._width = {k: sorted(w for w, i, bb in v)[len(v)//2] for k, v in inst.items()}
        self._samples = {}
        for k, v in inst.items():
            mid = sorted(v)[len(v)//2][0]; pick = []; used = set()
            for w, i, bb in sorted(v, key=lambda x: abs(x[0]-mid)):
                if i in used: continue
                used.add(i); pick.append((i, bb))
                if len(pick) == 3: break
            self._samples[k] = pick
        # Some codes are drawn as a letter in one place and as a narrow gap in another. Look at a few
        # of the widest instances on different pages: a glyph is a space only if none of them has ink.
        self.blank = set()
        for k, v in inst.items():
            top = max(v)[0]; tried = 0; pages_seen = set(); ink = False
            for w, i, bb in sorted(v, reverse=True):
                if w < 0.7*top or tried >= 6: break
                if i in pages_seen: continue
                pages_seen.add(i); tried += 1
                if has_ink(self.doc[i], bb): ink = True; break
            if not ink: self.blank.add(k)

    def _operator_of(self, k):
        """Sign for glyph code k, judged from its first sampled instance (Update12)."""
        for i, bb in getattr(self, '_samples', {}).get(k, [])[:1]:
            return self._operator(self.doc[i], k, bb)
        return ''

    def _operator(self, page, k, bb):
        """Which sign an unknown glyph between two numbers is, judged from its ink (Update11):
        two small raised marks (a quote, how this font draws the plus-minus sign) -> ±;
        a plus with a bar under it -> ±; a plus -> +; anything else (a cross, an asterisk) -> ×."""
        cache = self.__dict__.setdefault('_op_cache', {})
        if k in cache: return cache[k]
        kind = ''
        try:
            r = fitz.Rect(bb)
            pix = page.get_pixmap(dpi=400, clip=r, alpha=False, colorspace=fitz.csGRAY)
            img = Image.frombytes('L', (pix.width, pix.height), pix.samples).point(lambda v: 255 if v < 150 else 0)
            box = img.getbbox()
            if box:
                w = box[2]-box[0]; h = box[3]-box[1]; H = pix.height
                px = img.load(); seen = set(); parts = 0
                for y in range(box[1], box[3]):
                    for x in range(box[0], box[2]):
                        if px[x, y] and (x, y) not in seen:
                            parts += 1; stack = [(x, y)]; seen.add((x, y))
                            while stack:
                                cx, cy = stack.pop()
                                for nx, ny in ((cx+1, cy), (cx-1, cy), (cx, cy+1), (cx, cy-1), (cx+1, cy+1), (cx-1, cy-1), (cx+1, cy-1), (cx-1, cy+1)):
                                    if box[0] <= nx < box[2] and box[1] <= ny < box[3] and px[nx, ny] and (nx, ny) not in seen: seen.add((nx, ny)); stack.append((nx, ny))
                full = [y for y in range(box[1], box[3]) if sum(1 for x in range(box[0], box[2]) if px[x, y]) >= 0.7*w]
                mid = any(0.25 <= (y-box[1])/h <= 0.65 for y in full); low = any((y-box[1])/h >= 0.8 for y in full)
                raised = box[3]/H < 0.55                       # ink entirely in the upper half of the glyph box
                if parts == 2 and raised: kind = '±'          # "  drawn as two ticks
                elif mid and low: kind = '±'
                elif raised: kind = '×'                        # a raised asterisk stands for a multiplication sign
                elif mid: kind = '+'
                else: kind = '×'
        except Exception:
            kind = ''
        cache[k] = kind; self.__dict__.setdefault('_op_boxes', {})[k] = (page.number, tuple(bb))
        return kind

    def pick_extra_pages(self, legacy, taken, max_pages=16, min_gain=8):
        """Pages (not yet OCR'd) that together contain the most glyph occurrences whose code is still
        unknown, chosen greedily so each extra page adds codes the earlier ones do not (Update11)."""
        occ = {}
        for i in legacy:
            if i in taken or self.doc[i].rotation: continue
            c = collections.Counter(g[0] for g in page_glyphs(self.doc[i], self.names)
                                    if g[1] and self.mapping.get(g[0]) is None and g[0] not in self.blank)
            if c: occ[i] = c
        chosen = []; seen = set()
        while occ and len(chosen) < max_pages:
            best = max(occ, key=lambda i: sum(n for k, n in occ[i].items() if k not in seen))
            if sum(n for k, n in occ[best].items() if k not in seen) < min_gain: break
            chosen.append(best); seen |= set(occ[best]); occ.pop(best)
        return chosen

    def pick_unknown_lines(self, legacy, per_code=2, max_lines=60):
        """Text lines (page index, clip rectangle) that together show every still-unknown glyph code up to
        per_code times. Rare ligatures never appear on the evenly spaced or targeted sample pages; OCR of
        the single line that contains them is cheap and teaches the model those codes (Update13)."""
        where = {}
        for i in legacy:
            if self.doc[i].rotation: continue
            for g in page_glyphs(self.doc[i], self.names):
                if g[1] and self.mapping.get(g[0]) is None and g[0] not in self.blank:
                    where.setdefault((i, round(g[3][1]/3)), set()).add(g[0])
        covered = collections.Counter(); chosen = []
        while where and len(chosen) < max_lines:
            best = max(where, key=lambda l: sum(1 for k in where[l] if covered[k] < per_code))
            if not any(covered[k] < per_code for k in where[best]): break
            chosen.append(best)
            for k in where[best]: covered[k] += 1
            where.pop(best)
        rects = []
        for i, key in chosen:
            gl = [g for g in page_glyphs(self.doc[i], self.names) if round(g[3][1]/3) == key]
            y0 = min(g[2][1] for g in gl); y1 = max(g[2][3] for g in gl)
            rects.append((i, fitz.Rect(15, y0-3, self.doc[i].rect.width-15, y1+3)))
        return rects

    def train(self, samples):
        """samples: {page index: [(text, conf, (x0, y0, x1, y1) in PDF points)]} from OCR."""
        pairs = []
        for i, words in samples.items():
            if not self.doc[i].rotation: pairs += training_pairs(self.doc[i], self.names, words, self.blank)
        self.mapping, self.counts = learn(pairs)
        # OCR reports brackets in reading order, but the glyph is the drawn (mirrored) shape.
        # Store the drawn shape, like the shape matcher does; decode() mirrors it back.
        for k, v in self.mapping.items():
            if v in ('(', ')'): self.mapping[k] = {'(': ')', ')': '('}[v]
        return len(pairs)

    def _neighbours(self):
        """For every glyph: how often it sits right next to another glyph, and with which glyphs."""
        near = collections.defaultdict(collections.Counter)
        for i in range(len(self.doc)):
            page = self.doc[i]
            if page.rotation: continue
            glyphs = [g for g in page_glyphs(page, self.names) if g[1] and g[0] not in self.blank and self.mapping.get(g[0]) != '']
            lines = {}
            for g in glyphs: lines.setdefault(round(g[3][1]), []).append(g)
            for gs in lines.values():
                gs.sort(key=lambda g: g[2][0])
                for a, b in zip(gs, gs[1:]):
                    if b[2][0]-a[2][2] < 1.5:
                        near[a[0]][b[0]] += 1; near[b[0]][a[0]] += 1
        return near

    def learn_shapes(self):
        """Digits and punctuation by shape. OCR often reads old Arabic digits as letters
        (e.g. 9 as ain), so every glyph is compared with digit shapes; the neighbours decide
        whether a digit-like shape is really a digit (next to other digits) or punctuation."""
        refs = shape_references()
        if not refs: return 0
        guess = {}
        for k, inst in getattr(self, '_samples', {}).items():
            if k in self.blank: continue
            tried = [r for r in (classify_shape(self.doc[i], bb, refs) for i, bb in inst) if r]
            if tried: guess[k] = max(tried, key=lambda r: r[1])
        self._shape = guess
        near = self._neighbours()
        def digit_like(k):
            g = guess.get(k)
            return bool(g and g[0] in '٠١٢٣٤٥٦٧٨٩')
        found = 0
        for k, (ch, score) in guess.items():
            cur = self.mapping.get(k); votes = sum(self.counts.get(k, {}).values())
            total = sum(near[k].values())
            digits = sum(n for o, n in near[k].items() if digit_like(o) or (self.mapping.get(o) or 'x')[:1] in '،٫.-/%')
            rate = digits/total if total else 0.0
            is_letter = bool(cur and LETTER.match(cur) and votes >= 3)
            if ch in '٠١٢٣٤٥٦٧٨٩':
                if is_letter:
                    if rate >= 0.5 and score >= 0.8: self.mapping[k] = ch; found += 1   # OCR misread a digit as a letter
                elif ch == '٠' and rate < 0.2:
                    self.mapping[k] = '.'; found += 1                                # full stop look-alike
                elif ch == '٦' and rate < 0.2 and self._ink_fraction(k) < 0.33:
                    # a comma looks like a small ٦; a real ٦ is taller. With no neighbours the rate is 0,
                    # so the rate alone would turn every isolated ٦ into a comma (Update9).
                    self.mapping[k] = '،'; found += 1
                else:
                    self.mapping[k] = ch; found += 1
                continue
            if is_letter: continue
            if ch in '.٠' and rate >= 0.5: self.mapping[k] = '٠'; found += 1; continue   # zero among digits
            # a small dot-like glyph that OCR saw inside words is part of a letter, not punctuation
            if ch in '.٠،:' and votes >= 3 and (not cur or LETTER.match(cur)):
                # A comma that OCR simply dropped (mostly empty votes) is still a comma; only skip when OCR
                # often read it as a letter, i.e. it is part of a word (Update11)
                letters = sum(n for c, n in self.counts.get(k, {}).items() if c and LETTER.match(c))
                if not (ch == '،' and letters < 0.3*votes and self._ink_fraction(k) < 0.35 and score >= 0.85): continue
            self.mapping[k] = ch; found += 1
        # letters that look like digits (ه/٥, ا/١) and sit among digits are digits
        for k, inst in getattr(self, '_samples', {}).items():
            cur = self.mapping.get(k)
            if k in self.blank or (cur and cur not in LOOKALIKE and cur not in '.٠'): continue
            total = sum(near[k].values()); digits = sum(n for o, n in near[k].items() if digit_like(o) or (self.mapping.get(o) or ' ') in '٠١٢٣٤٥٦٧٨٩')
            if total >= 3 and digits/total >= 0.6:
                ink = self._ink_box(k)
                if ink and ink[2] >= 4:                  # a flat stroke among digits is a hyphen (١-٣), not a digit (Update9)
                    self.mapping[k] = '-'; found += 1; continue
                tried = [r for r in (classify_shape(self.doc[i], bb, refs, digits_only=True) for i, bb in inst) if r]
                if tried: self.mapping[k] = max(tried, key=lambda r: r[1])[0]; found += 1
        found += self.recover_numeric_glyphs(refs)
        self._fix_markers()
        self._fix_widths()
        return found

    def recover_numeric_glyphs(self, refs=None):
        """Read still-unknown digits in repeated numeric runs separated by - or /.

        Two independent page samples must agree on shape with a clear margin.
        Existing readings are never changed; a separator must connect to a known
        digit before it counts as numeric context.
        """
        refs=shape_references(reference_fonts()) if refs is None else refs
        near=self._neighbours(); found=0
        for key,instances in getattr(self,'_samples',{}).items():
            if key in self.mapping or key in self.blank: continue
            total=sum(near[key].values())
            numeric=sum(n for other,n in near[key].items()
                        if self.mapping.get(other) in DIGITS or self.mapping.get(other) in ('-','/'))
            if total<3 or numeric/total<.6: continue
            linked=any(self.mapping.get(other) in DIGITS or
                       (self.mapping.get(other) in ('-','/') and
                        any(self.mapping.get(next_key) in DIGITS for next_key in near[other]))
                       for other in near[key])
            if not linked: continue
            readings=[];pages=set()
            for page,box in instances:
                if page in pages: continue
                pages.add(page)
                reading=classify_shape(self.doc[page],box,refs,digits_only=True,minimum_margin=.12)
                if reading and reading[1]>=.82: readings.append(reading)
            if len(readings)>=2 and len({char for char,score in readings})==1:
                self.mapping[key]=readings[0][0];found+=1
        return found

    def _ink_box(self, k):
        """(top, bottom, width/height) of a glyph's ink, top and bottom as fractions of its box height."""
        for i, bb in getattr(self, '_samples', {}).get(k, [])[:2]:
            try:
                r = fitz.Rect(bb); pix = self.doc[i].get_pixmap(dpi=200, clip=r, alpha=False, colorspace=fitz.csGRAY)
                img = Image.frombytes('L', (pix.width, pix.height), pix.samples).point(lambda v: 255 if v < 128 else 0)
                box = img.getbbox()
                if box: return box[1]/max(1, pix.height), box[3]/max(1, pix.height), (box[2]-box[0])/max(1, box[3]-box[1])
            except Exception:
                continue
        return None

    def _digit_shape(self, k):
        """True when the shape matcher is sure this glyph is a digit other than ٠ and its ink is
        digit-shaped (a ring or stroke about as wide as tall), not a slanted comma."""
        g = getattr(self, '_shape', {}).get(k)
        if not g or g[0] not in '١٢٣٤٥٦٧٨٩' or g[1] < 0.9: return False
        ink = self._ink_box(k)
        return ink is None or ink[2] >= 0.8 or g[0] in '١٧٨'

    def _ink_fraction(self, k):
        """Height of a glyph's ink relative to its box: about 0.6 for a digit, under 0.35 for a
        comma or full stop."""
        for i, bb in getattr(self, '_samples', {}).get(k, [])[:2]:
            try:
                r = fitz.Rect(bb); pix = self.doc[i].get_pixmap(dpi=200, clip=r, alpha=False, colorspace=fitz.csGRAY)
                img = Image.frombytes('L', (pix.width, pix.height), pix.samples).point(lambda v: 255 if v < 128 else 0)
                box = img.getbbox()
                if box: return (box[3]-box[1])/max(1, pix.height)
            except Exception:
                continue
        return 1.0

    def _fix_markers(self):
        """Two glyphs OCR labels badly: an end-of-paragraph/cell marker drawn after the last word
        (OCR calls it a letter such as ض), and the Arabic decimal mark between digits (read as 5)."""
        occ = collections.Counter(); alone_end = collections.Counter(); between = collections.Counter(); after_sign = collections.Counter()
        sides = collections.Counter(); dsides = collections.Counter()
        digits = set('٠١٢٣٤٥٦٧٨٩')
        for i in range(len(self.doc)):
            page = self.doc[i]
            if page.rotation: continue
            lines = {}
            for g in page_glyphs(page, self.names):
                if g[1] and g[0] not in self.blank: lines.setdefault(round(g[3][1]), []).append(g)
            for gs in lines.values():
                gs.sort(key=lambda g: g[2][0])
                for n, g in enumerate(gs):
                    occ[g[0]] += 1
                    left = gs[n-1] if n else None; right = gs[n+1] if n+1 < len(gs) else None
                    touch_l = left is not None and g[2][0]-left[2][2] < 1.5
                    touch_r = right is not None and right[2][0]-g[2][2] < 1.5
                    for touch, nb, at in ((touch_l, left, -1), (touch_r, right, 0)):
                        if touch:
                            sides[g[0]] += 1
                            if (self.mapping.get(nb[0]) or ' ')[at] in digits: dsides[g[0]] += 1
                    if not touch_l and not touch_r: alone_end[g[0]] += 1    # stands alone after a word or cell
                    # drawn right after (to the left of) a digit or bracket: an Arabic letter never follows these joined
                    if touch_r and (self.mapping.get(right[0]) or 'x')[:1] in digits | set(')(-/%٫.'): after_sign[g[0]] += 1
                    if touch_l and touch_r and (self.mapping.get(left[0]) or ' ')[-1] in digits and (self.mapping.get(right[0]) or ' ')[:1] in digits:
                        between[g[0]] += 1
        for k, n in occ.items():
            cur = self.mapping.get(k) or ''
            # a letter that is almost never joined to anything is a marker (list letters أ ب ج د ه and و are real words)
            if n >= 5 and len(cur) == 1 and LETTER.match(cur) and cur not in 'وأبجدهـ' and alone_end[k]+after_sign[k] >= 0.8*n:
                self.markers.add(k)                                      # paragraph / cell end marker (see decode)
            elif self._degree(k):
                self.mapping[k] = '°'                                   # small raised ring (Update9)
            elif self._digit_shape(k):
                continue                                                # a short digit such as ٥, not a comma (Update9)
            elif cur in digits and cur != '٠' and sides[k] >= 3 and dsides[k] >= 0.6*sides[k] and self._ink_fraction(k) < 0.35:
                self.mapping[k] = '٫'                                   # a comma-sized glyph OCR called a digit, inside numbers
            elif n >= 3 and between[k] >= 0.8*n and not LETTER.match(cur or 'x'):
                ink = self._ink_box(k)
                if ink and ink[2] >= 4:
                    if cur in ('', None) or cur in digits: self.mapping[k] = '-'   # flat stroke between digits: hyphen (Update9)
                    continue
                # a glyph between numbers whose ink is as wide as it is tall is a sign (× in 900×900×1200), not a
                # decimal comma, which is narrow and hangs below the line (Update12)
                if ink and ink[2] >= 0.85 and not LETTER.match(cur or 'x'):
                    op = self._operator_of(k)
                    if op: self.mapping[k] = op; continue
                # OCR often calls a decimal comma a digit (1); a comma has far less ink than any digit
                if (cur in digits or cur == '') and cur != '٠' and self._ink_fraction(k) < 0.35: self.mapping[k] = '٫'   # Arabic decimal separator
                elif cur not in digits and cur not in '-/%()': self.mapping[k] = '٫'

    def _degree(self, k):
        """A ring shape whose ink sits entirely in the top third of its box is a degree sign
        (a real ٥ reaches down past the middle)."""
        g = getattr(self, '_shape', {}).get(k)
        if not g or g[0] != '٥' or g[1] < 0.8: return False
        ink = self._ink_box(k)
        return bool(ink and ink[1] < 0.3 and ink[2] >= 0.6)

    def _fix_widths(self):
        """A wide glyph read as a narrow letter (final qaf read as alef) takes its next reading."""
        widths = getattr(self, '_width', {})
        by_letter = collections.defaultdict(list)
        for k, v in self.mapping.items():
            if v and len(v) == 1 and k in widths and sum(self.counts.get(k, {}).values()) >= 20: by_letter[v].append(widths[k])
        typical = {c: sorted(w)[len(w)//2] for c, w in by_letter.items() if w}
        for k, v in list(self.mapping.items()):
            if v != 'ا' or k not in widths or 'ا' not in typical: continue
            if widths[k] > 2.2*typical['ا']:
                alt = [(n, c) for c, n in collections.Counter(self.counts.get(k, {})).most_common() if c and c != 'ا' and LETTER.match(c)]
                if alt and alt[0][0] >= 0.15*sum(self.counts[k].values()): self.mapping[k] = alt[0][1]

    def decode(self, page, clip=None, exclude=(), headings=True, columns=True):
        """Text of one page (or of the glyphs inside clip, minus those inside exclude) in reading
        order, and the share of glyphs that were understood."""
        glyphs = page_glyphs(page, self.names)
        if page.rotation:     # glyph boxes are unrotated; read the text in its displayed orientation
            m = page.rotation_matrix
            glyphs = [(k, lg, tuple(fitz.Rect(bb)*m), tuple(fitz.Point(o)*m), sz, ch) for k, lg, bb, o, sz, ch in glyphs]
            glyphs = [(k, lg, (min(b[0], b[2]), min(b[1], b[3]), max(b[0], b[2]), max(b[1], b[3])), o, sz, ch) for k, lg, b, o, sz, ch in glyphs]
        widths = collections.defaultdict(list)
        for g in glyphs:
            if g[1]: widths[g[0]].append(g[2][2]-g[2][0])
        widest = {k: max(v) for k, v in widths.items()}
        widths_digit = max((w for k, v in widths.items() if (self.mapping.get(k) or 'x')[:1] in DIGITS for w in v[:1]), default=6.0)
        def inside(g, r): return r[0] <= (g[2][0]+g[2][2])/2 <= r[2] and r[1] <= (g[2][1]+g[2][3])/2 <= r[3]
        if clip is not None: glyphs = [g for g in glyphs if inside(g, clip)]
        if exclude: glyphs = [g for g in glyphs if not any(inside(g, r) for r in exclude)]
        sizes = sorted(g[4] for g in glyphs if g[1]) or [11]
        body = sizes[len(sizes)//2]
        total = known = 0; out = []; self.last_cells = []
        gutter = _gutter(glyphs, page.rect.width) if columns and clip is None else None
        # two columns: Arabic reads the right-hand column first
        groups = [[g for g in glyphs if (g[2][0]+g[2][2])/2 > gutter], [g for g in glyphs if (g[2][0]+g[2][2])/2 <= gutter]] if gutter else [glyphs]
        for group in groups:
            lines = []
            for g in sorted(group, key=lambda g: g[3][1]):
                if lines and abs(lines[-1][0]-g[3][1]) < 3: lines[-1][1].append(g)
                else: lines.append([g[3][1], [g]])
            for _, gs in lines:
                gs.sort(key=lambda g: g[2][0]); units = []; prev = None; size = 11; segs = [[None, None]]
                for idx, (k, legacy, bb, o, sz, ch) in enumerate(gs):
                    size = max(size, sz)
                    if k in self.markers:
                        # the same code is a real final letter when it is joined to a letter on its right
                        nxt = gs[idx+1] if idx+1 < len(gs) else None
                        if not (nxt and nxt[2][0]-bb[2] < 1.5 and LETTERS.search((self.mapping.get(nxt[0]) or '')[:1] or 'x')):
                            continue
                    if legacy:
                        letter = bool(self.mapping.get(k))
                        # some codes are drawn as a letter in one place and as a narrow gap in another
                        if (k in self.blank and not letter) or bb[2]-bb[0] < 0.6*widest[k]:
                            units.append(' '); continue
                    if legacy:
                        total += 1; s = self.mapping.get(k)
                        if s is None:
                            s = ''
                            # an unknown glyph between two numbers (2.1 _ 0.05) is a plus-minus sign (Update11)
                            def digit_at(j):
                                while 0 <= j < len(gs) and gs[j][1] and (gs[j][0] in self.blank or gs[j][2][2]-gs[j][2][0] < 0.6*widest[gs[j][0]]): j += 1 if j > idx else -1
                                if not 0 <= j < len(gs) or not gs[j][1]: return False
                                return (self.mapping.get(gs[j][0]) or 'x')[:1] in DIGITS
                            if 0 < idx < len(gs)-1 and bb[2]-bb[0] < 0.8*max(widths_digit, 1) and digit_at(idx-1) and digit_at(idx+1):
                                s = self._operator(page, k, bb); known += 1 if s else 0
                            # Preserve the location of a glyph with no reading.
                            # A high page-wide known ratio must not hide a missing
                            # letter or a digit inside an otherwise readable line.
                            if not s: s = '[?]'
                        else: known += 1
                    else: s = ch
                    if prev is not None and bb[0]-prev > 1.8*sz: units.append('\t'); segs.append([None, None])   # wide gap: next table column
                    elif prev is not None and bb[0]-prev > 0.22*sz: units.append(' ')
                    if not legacy or k in self.mapping or s: prev = max(prev or 0, bb[2])   # a sign inferred from its shape (±, ×) also counts (Update13)
                    if s.strip():
                        seg = segs[-1]; seg[0] = bb[0] if seg[0] is None else min(seg[0], bb[0]); seg[1] = bb[2] if seg[1] is None else max(seg[1], bb[2])
                    if s: units.append(s)
                # a '-' glued between Arabic letters is a kashida stretch, not a hyphen
                keep = []
                for n, u in enumerate(units):
                    if u == '-':
                        left = next((x for x in reversed(units[:n]) if x != '-'), '')
                        right = next((x for x in units[n+1:] if x != '-'), '')
                        if LETTERS.search(left[-1:]) and LETTERS.search(right[:1]): continue   # kashida stretch
                    keep.append(u)
                units = keep
                # the same glyph is a decimal mark between digits and a comma in text (Update9)
                for n, u in enumerate(units):
                    if u == '٫':
                        left = units[n-1][-1:] if n else ''; right = units[n+1][:1] if n+1 < len(units) else ''
                        if not (left in DIGITS and right in DIGITS): units[n] = '،'
                units = units[::-1]                              # visual order -> reading order
                # Simplified Unicode bidi: a left-to-right run (Latin words, numbers) is put back in
                # left-to-right order together with the spaces and brackets between its parts, e.g.
                # "ADMIXTURE (ADDITIVE)". Brackets outside such runs are mirrored.
                strong = [bool(LTR.match(u)) for u in units]
                # a lone '-' or '/' is part of a number only between two left-to-right parts (٣-١٣-٥, ١/٢);
                # after a list number before Arabic text it follows the Arabic direction (Update9)
                for n, u in enumerate(units):
                    if u in ('-', '/') and strong[n]:
                        if not (0 < n < len(units)-1 and strong[n-1] and strong[n+1] and units[n-1] not in '-/' and units[n+1] not in '-/'): strong[n] = False
                        # Unicode bidi: a hyphen between two Arabic-Indic numbers is neutral, so the numbers keep
                        # right-to-left order (section ٣-١ is drawn ١-٣). '/' does join them (٥٧/١٣). (Update13)
                        elif u == '-' and re.match('[\u0660-\u0669]', units[n-1][-1:]) and re.match('[\u0660-\u0669]', units[n+1][:1]): strong[n] = False
                res = []; n = 0
                while n < len(units):
                    if strong[n]:
                        m = n
                        while True:
                            k = m + 1
                            while k < len(units) and not strong[k] and not LETTERS.search(units[k]) and units[k] != '\t': k += 1
                            if k < len(units) and strong[k]:
                                gap = units[m+1:k]
                                latin = re.search('[A-Za-z]', units[m]) is not None
                                numbers = re.match('[0-9\u0660-\u0669]', units[m]) and re.match('[0-9\u0660-\u0669]', units[k])
                                # Latin context joins across spaces and brackets ("ADMIXTURE (ADDITIVE)"); two numbers
                                # join only across a decimal mark, otherwise the gap between them stays right-to-left
                                if not gap or latin or (numbers and all(x in '٫.,' for x in gap)): m = k
                                else: break
                            else: break
                        run = units[n:m+1]
                        # a bracket right outside the run that closes one inside it belongs to the run
                        if run.count('(') > run.count(')') and n > 0 and units[n-1] == ')' and res and res[-1] == '(':
                            res.pop(); run = [')'] + run
                        if run.count(')') > run.count('(') and m+1 < len(units) and units[m+1] == '(':
                            run = run + ['(']; m += 1
                        res.extend(run[::-1]); n = m + 1
                    else:
                        u = units[n]; res.append({'(': ')', ')': '('}.get(u, u)); n += 1
                text = re.sub(r'([\u0621-\u064a])([A-Za-z])', r'\1 \2', ''.join(res))
                text = re.sub(r'([A-Za-z])([\u0621-\u064a])', r'\1 \2', text)
                text = re.sub(r' *\t[\t ]*', '\t', re.sub(r' +', ' ', text)).strip(' \t')
                # a comma glued between digits is a decimal mark (٥،٢ -> ٥٫٢); groups of exactly three digits
                # after it (٢،١٢٥) are ambiguous with a thousands separator and stay as they are (Update11)
                text = decimal_marks(text)
                if text:
                    out.append(('### ' if headings and size >= 1.3*body and len(text) < 160 else '') + text)
                    boxes = [tuple(x) for x in segs if x[0] is not None][::-1]   # reading order: rightmost cell first
                    self.last_cells.append(boxes if '\t' in text and len(boxes) == text.count('\t')+1 else None)
        return '\n'.join(out), (known/total if total else 0.0)


def ocr_words(png, settings, work, threads=None, psm='3', origin=(0.0, 0.0)):
    """Tesseract words with boxes in PDF points (image rendered at 300 dpi). For a cropped line pass
    psm='7' and the crop's top-left corner in points as origin, so the boxes are page coordinates."""
    from .ocr import preflight, _tesseract, ocr_language
    # A quality switch must not relearn all legacy font codes with another model.
    # Standard is the stable training baseline; High remains available for actual
    # page/cell OCR outside this legacy font-training function.
    training_settings=dict(settings,quality='standard')
    root = preflight(training_settings)
    result = _tesseract(root, png, ['-l', ocr_language(training_settings), '--psm', str(psm), 'tsv'], work, threads)
    if result.returncode: return []
    words = []
    for r in csv.DictReader(io.StringIO(result.stdout.decode('utf-8', 'replace')), delimiter='\t', quoting=csv.QUOTE_NONE):
        t = (r.get('text') or '').strip()
        if not t: continue
        try:
            x, y, w, h = (int(r[k])*72/300 for k in ('left', 'top', 'width', 'height'))
            words.append((t, float(r['conf']), (origin[0]+x, origin[1]+y, origin[0]+x+w, origin[1]+y+h)))
        except (KeyError, ValueError):
            continue
    return words
