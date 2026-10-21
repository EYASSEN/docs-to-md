# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Repairs for common broken-Arabic patterns in text taken from files.

- Windows-1256 mojibake: Arabic stored in the old Windows code page but read as Western
  (ÇáÚÑÈíÉ instead of العربية). Only lines that are mostly such characters are converted,
  so French or other accented Latin text is left alone.
- Swapped lam + hamza-alef from some Word "Save as PDF" files: اإلجمالي -> الإجمالي,
  األول -> الأول. An alef directly followed by a hamza-alef does not occur in correct spelling.
- Kashida (tatweel) stretching is removed so words can be searched: الـــعمل -> العمل.
- Stray fathatan (U+064B) that some native PDFs carry inside or between words (Cleanup2). See
  drop_stray_tanween: a real word-final tanween is never touched.
"""
import re

ARABIC = re.compile('[\u0621-\u064a]')
SWAPPED = re.compile('ا([أإآ])ل')


def _mojibake(line):
    letters = [c for c in line if c.isalpha()]
    high = [c for c in letters if '\u00c0' <= c <= '\u00ff']
    if len(high) < 3 or len(high) < 0.4*len(letters): return line
    for codec in ('cp1252', 'latin-1'):
        try: fixed = line.encode(codec).decode('cp1256')
        except UnicodeError: continue
        fixed_letters = [c for c in fixed if c.isalpha()]
        if fixed_letters and sum(1 for c in fixed_letters if ARABIC.match(c)) >= 0.6*len(fixed_letters):
            return fixed
    return line


def fix_text(value):
    if not value: return value
    if any('\u00c0' <= c <= '\u00ff' for c in value):
        value = '\n'.join(_mojibake(l) for l in value.split('\n'))
    if 'ا' in value:
        value = SWAPPED.sub(lambda m: 'ال' + m.group(1), value)
    # A combining mark separated from its Arabic base by spaces is an
    # extraction artifact; preserve word boundaries and line breaks.
    value=re.sub(r'(?<=[\u0621-\u064a\u064b-\u065f]) +(?=[\u064b-\u065f])','',value)
    return value.replace('\u0640', '')


def looks_cp1256(data):
    """Bytes that are Arabic in the Windows code page: mostly high bytes that decode to Arabic."""
    try: text = data.decode('cp1256')
    except UnicodeError: return None
    letters = [c for c in text if c.isalpha()]
    if not letters: return None
    arabic = sum(1 for c in letters if ARABIC.match(c))
    return text if arabic >= 0.3*len(letters) and arabic >= 0.8*sum(1 for c in letters if ord(c) > 127) else None


# ---- Stray tanween (Cleanup2) -------------------------------------------------------------------
# Two styles were seen in the text layer of some native PDFs:
#   A. the mark is the word separator:  word1<mark>word2<mark>word3  (no ordinary spaces)
#   B. the mark sits after the first letter of words that are separated by ordinary spaces
# A mark that sits directly between two Arabic letters is never ordinary spelling, except the typed
# order of a final tanween before alef (شكرًا: mark, then a word-final alef). Everything else is left alone:
# word-final tanween (جداً, مثلةً), marks next to digits, Latin text, spaces or other marks.
_FATHATAN = '\u064b'
_LETTERS = '\u0621-\u064a\u066e-\u06d3\u06fa-\u06ff'
_STRAY = re.compile(f'(?<=[{_LETTERS}])\u064b+(?=[{_LETTERS}])')
_TYPED_FINAL = re.compile(f'\u064b[\u0627\u0649](?![{_LETTERS}])')       # mark + word-final alef / alef maksura
_SPACE_BETWEEN = re.compile(r'(?<=\S) (?=\S)')
_RUN_BEFORE = re.compile(f'[{_LETTERS}\u064c-\u065f]+$')
_SPACE_SHARE = 0.15                                                       # spaces per mark: style B at or above


def _clean_tanween_line(line):
    if _FATHATAN not in line: return line
    sites = [m for m in _STRAY.finditer(line)
             if not (len(m.group()) == 1 and _TYPED_FINAL.match(line, m.start()))]
    if not sites: return line
    # Sites per whitespace-delimited token: a token with several marks is style A (marks separate words).
    tokens = [m.span() for m in re.finditer(r'\S+', line)]
    per_token, owner, t = {}, [], 0
    for m in sites:
        while tokens[t][1] <= m.start(): t += 1
        owner.append(t); per_token[t] = per_token.get(t, 0) + 1
    spaced = len(_SPACE_BETWEEN.findall(line)) >= _SPACE_SHARE * len(sites)   # the line has ordinary spaces: style B
    out, last, replaced = [], 0, False
    for m, t in zip(sites, owner):
        if per_token[t] > 1: sep = ' '                                       # style A: the mark is the separator
        else:
            run = _RUN_BEFORE.search(line[:m.start()])
            first_letter = run is not None and len(run.group()) == 1           # mark right after the first letter
            sep = '' if first_letter or spaced else ' '
        out.append(line[last:m.start()]); out.append(sep); last = m.end()
        replaced = replaced or bool(sep)
    out.append(line[last:])
    result = ''.join(out)
    return re.sub(r' {2,}', ' ', result) if replaced else result


# ---- Misplaced tanween (Cleanup2c/2e) ------------------------------------------------------------
# After the between-letters pass, the same text layers still carry fathatan marks that are drawn nowhere on
# the page: at the start of a line, alone, after spaces, brackets or non-final letters. A real tanween is
# word-final after alef / alef maksura / teh marbuta / hamza (جداً, مثلةً, عصىً) or typed before a word-final
# alef (شكرًا, never on a two-letter word: لًا is the noise). Those stay.
# Some PDFs also store a real tanween after the punctuation that follows
# its word (مثلا،ً): it moves back before the punctuation (مثلاً،) instead of being lost.
_KEEP_FINAL = re.compile(f'(?<=[\u0627\u0649\u0629\u0623\u0625\u0621\u0626])\u064b(?![{_LETTERS}\u064b-\u0652])')
_KEEP_TYPED = re.compile(f'(?<=[{_LETTERS}\u064c-\u0652][{_LETTERS}\u064c-\u0652])\u064b(?=[\u0627\u0649](?![{_LETTERS}]))')   # two letters before: not لا / فى / ما
_AFTER_PUNCT = re.compile('(?<=[{0}]\u0627)([\u060c.:\u061b,!\u061f])\u064b'.format(_LETTERS))


def _drop_misplaced_fathatan(line):
    if _FATHATAN not in line: return line
    if not ARABIC.search(line):                       # no Arabic letter: only a line of marks and punctuation is cleaned
        rest = line.replace(_FATHATAN, '')
        return rest if not any(c.isalnum() for c in rest) else line
    line = _AFTER_PUNCT.sub(lambda m: _FATHATAN + m.group(1), line)
    # Mark count cannot distinguish a grammatical sentence from font noise.
    keep = {m.start() for m in _KEEP_FINAL.finditer(line)} | {m.start() for m in _KEEP_TYPED.finditer(line)}
    return ''.join(c for i, c in enumerate(line) if c != _FATHATAN or i in keep)


def drop_stray_tanween(value):
    """Remove stray and misplaced fathatan, line by line. Lines without any mark stay identical."""
    if not value or _FATHATAN not in value: return value
    return '\n'.join(_drop_misplaced_fathatan(_clean_tanween_line(line)) for line in value.split('\n'))
