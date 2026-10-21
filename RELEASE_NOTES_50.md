# Docs to MD 1.0.3 — converter revision 50

Release date: October 2026. This release gives the fixes made since revision 49 their own version number.
Every build since revision 49 reported 1.0.2 / revision 49; from now on the version identifies the build.

## Conversion changes since revision 49
- Cleanup4/5: pages whose text layer is empty, noisy or hidden behind a page-sized image are read with
  whole-page OCR (VOL 1.1 front pages and the Geotechnical Report). Visual review of this output is still open.
- Cleanup6: tall BOQ rows that hold several items are split per item.
- Cleanup7b: section headings printed above an item number stay separate from the item.
- Cleanup8b: tolerant table-border detection (Cleanup8) is switched off; it lost text on BOQs 2 summary pages.
  Output of BOQs 1 and 2 is identical to the accepted Cleanup7b result (82 of 82 pages).

## Window
- The original window, light theme only, with dark blue in place of green.

## Known limits
- BOQ row boundaries are still wrong on BOQs 1 pages 18, 22, 38, 39 and BOQs 2 pages 5, 11, 23, 28.
- Quantities and other numbers in scanned BOQs are not certified; every OCR result needs review.
