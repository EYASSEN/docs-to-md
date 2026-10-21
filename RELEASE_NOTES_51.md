# Docs to MD 1.0.4 — converter revision 51

## Conversion change
- Blue rubber-stamp blocks are removed before OCR (Cleanup9). The rectangular "Joint Venture IWSP II"
  stamp on VOL 1.1 pages, rotated stamps, and round seals that hold text inside are now detected; until
  now only hollow round stamps were. Only bright stamp ink inside the stamp area is removed; black text
  printed under the stamp is kept. Blue headings, thin coloured table bands and small blue handwriting
  are left alone. The original page image in the output is unchanged.
- The conversion report now says "detected colored stamps suppressed".

## Known limits
- Handwritten entries (for example bid dates) are still not read.
- Numbers in scanned tables and drawings still need checking against the page image.
- The Geotechnical Report scans remain unreadable.
