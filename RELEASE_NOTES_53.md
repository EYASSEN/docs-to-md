# Docs to MD 1.0.6 — converter revision 53

## Conversion change
- Scans that read as noise no longer produce noise (Cleanup11). When Tesseract's layout reading
  finds almost no confident word on a scanned page and its sparse reading is mostly fragments, the
  page is read again from a smoothed copy (halftone dots merged into strokes). If that reading is
  clearly better, it is written under the notice "Poor-quality scan: ... approximate. Check every
  word and number against the page image." Otherwise the page gets only the notice "Unreadable
  scan: no reliable text could be read from this page. See the page image." The page image is kept.
- Main target: the Geotechnical Report (dotted, speckled scans). Some Arabic description pages are
  now partly readable; borehole logs and tables still are not, and are marked unreadable.
- Thresholds were set from the bundled Windows Tesseract (Cleanup11b): a page counts as noise when
  the layout reading has fewer than 5 confident words and the sparse reading has 20+ fragments, mean
  confidence below 55 and fewer than 12 % confident words.
- Pages with readable text keep the normal reading path. The first layout reading is reused, so
  pages without a ruled table get no extra OCR pass.

## Known limits
- Text from a smoothed copy is approximate; numbers in it are often wrong.
- Handwritten entries (for example bid dates) are still not read.
- Numbers in scanned tables and drawings still need checking against the page image.
