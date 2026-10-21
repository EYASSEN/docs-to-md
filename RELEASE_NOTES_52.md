# Docs to MD 1.0.5 — converter revision 52

## Conversion change
- Invisible PDF text no longer leaks into the output (Cleanup10). Scanned PDFs often carry the
  scanner's own invisible OCR layer. Its spans were hidden only when their centre fell inside the
  layer's trace boxes; spans with taller text boxes slipped through, and when about 30 letters of that
  noise survived, the page was treated as having real text and was never OCR'd. Now any span the PDF
  marks fully transparent is hidden by itself, and such pages are read from the page image.
- VOL 1.1 pages 510, 886, 887, 907, 928 and 959 and TOR page 23 are now OCR'd instead of
  exporting a few words of noise. No other page in the sample folders changes its reading path;
  BOQs 1 and BOQs 2 contain no invisible text and are unaffected.
- An invisible watermark does not hide visible text inside its text box.

## Known limits
- A visible line drawn right on top of an invisible watermark's letters can still be dropped
  (unchanged from earlier revisions).
- Handwritten entries (for example bid dates) are still not read.
- Numbers in scanned tables and drawings still need checking against the page image.
- The Geotechnical Report scans remain unreadable.
