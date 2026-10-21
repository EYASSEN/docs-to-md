# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compare two conversion outputs word by word (Update21).

    python scripts/compare_outputs.py OLD_FOLDER NEW_FOLDER [--show 15] [--out comparison.md]

Use it after changing the code or updating a library: convert the same files with the old and the new
build, then compare the two output folders. Image links and asset paths are ignored. Standard library only.
"""
import argparse, collections, difflib, re, sys
from pathlib import Path

LINK = re.compile(r'!?\[[^\]]*\]\([^)]*\)')


def words(path):
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    return re.findall(r'\S+', LINK.sub(' ', text))


def markdown_files(root):
    root = Path(root)
    return {p.relative_to(root).as_posix(): p for p in root.rglob('*.md')
            if not any(part.startswith('.') for part in p.relative_to(root).parts)}


def compare(old, new):
    """(old word count, new word count, changed spots, words kept, Counter of (old text, new text))."""
    a, b = words(old), words(new)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    changes = collections.Counter(); kept = 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal': kept += i2 - i1
        else: changes[(' '.join(a[i1:i2])[:80], ' '.join(b[j1:j2])[:80])] += 1
    return len(a), len(b), sum(changes.values()), kept, changes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('old'); ap.add_argument('new')
    ap.add_argument('--show', type=int, default=15, help='most frequent changes listed per file')
    ap.add_argument('--out', help='also write the comparison to this Markdown file')
    args = ap.parse_args(argv)
    old, new = markdown_files(args.old), markdown_files(args.new)
    lines = ['# Output comparison', '', f'Old: `{args.old}`', f'New: `{args.new}`', '',
             '| File | Old words | New words | Changed spots | Old words kept |', '| --- | --- | --- | --- | --- |']
    details = []
    for rel in sorted(set(old) | set(new)):
        if rel not in new: lines.append(f'| {rel} | - | missing | - | - |'); continue
        if rel not in old: lines.append(f'| {rel} | new file | - | - | - |'); continue
        n_old, n_new, spots, kept, changes = compare(old[rel], new[rel])
        share = f'{100 * kept / n_old:.1f}%' if n_old else '-'
        lines.append(f'| {rel} | {n_old:,} | {n_new:,} | {spots:,} | {share} |')
        if changes:
            details += ['', f'## {rel}', '', '| Times | Old | New |', '| --- | --- | --- |']
            for (x, y), n in changes.most_common(args.show):
                details.append(f'| {n} | {x or "(nothing)"} | {y or "(nothing)"} |'.replace('\n', ' '))
    report = '\n'.join(lines + details) + '\n'
    sys.stdout.write(report)
    if args.out: Path(args.out).write_text(report, encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
