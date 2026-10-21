# Docs to MD 1.1.0 — revision 57

## New: ONNX OCR engine for scanned pages (Cleanup17)

Standard and High accuracy now read scanned pages with an offline PP-OCR engine (ONNX Runtime,
no internet, no OpenCV). Tesseract still corrects page orientation, removes coloured stamps,
reads ruled tables cell by cell, and decides whether a page is unreadable noise. Quick mode is
unchanged (one Tesseract pass). If the engine is missing or fails on a page, that page is read by
Tesseract and a warning says so.

Measured on a hand-checked 15-page reference set (VOL scanned tables, Geotechnical Report, BOQ):

| | Revision 55 | Engine |
|---|---|---|
| Numbers found | 375/504 (74%) | 416/504 (83%) |
| Wrong extra numbers | 72 | 40 |
| Words found | 81.5% | 85.0% |
| Table rows intact | 76/122 | 89/122 |

Arabic BOQ quantities in Arabic-Indic digits and poor geotechnical scans improve most; they are
still not reliable. Review numbers against the page image.

Revision 56 was the withdrawn table experiment (Cleanup15) and was never released.

## Package

Adds ONNX Runtime, NumPy, pyclipper and three OCR models (about 37 MB in the 7z). Licences in
THIRD_PARTY_NOTICES.md and vendor/ocr-onnx.

## Microsoft Store package (Cleanup18)

scripts/make_msix.py builds an MSIX package from the completed dist/DocsToMD for the Microsoft
Store, which signs Store apps, so Windows SmartScreen and Smart App Control do not block them.
When the app runs as an installed package its install folder is read-only, so settings are kept in
%LOCALAPPDATA%\DocsToMD\data; the portable ZIP/7z still keeps them in the data folder beside the
program. Conversion output is unchanged (converter revision 57).
