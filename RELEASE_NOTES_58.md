# Docs to MD 1.1.1 — revision 58

## Ruled-table cells read by the ONNX OCR engine (Cleanup22)

In Standard and High accuracy, each cell of a ruled scanned table is now read by the ONNX OCR engine
as well as by Tesseract. A cell keeps the engine reading unless the engine found nothing, read
letters of another script (for example "3ρ" for the unit م3), read Latin letters where Tesseract
read Arabic, or lost digit groups that Tesseract found (Latin numbers inside Arabic descriptions).
Number cells always keep the engine reading when it is a number. The report says how many cells
the engine read.

Measured on an invented, photocopy-degraded Arabic BOQ (tests/fixtures/pdf/boq-sample.pdf):

| | Revision 57 | Revision 58 |
|---|---|---|
| Amounts and quantities correct | 21/24 | 24/24 |
| Grand total | "1,498,085 .0" | 1,498,085.00 |
| Last item description | lost | kept |

On the 15-page reference set the result is unchanged within one value (numbers 418 → 417 of 504,
words 3003 → 3000 of 3508, table rows 94/122 both): only the three BOQ pages have ruled tables,
and their cells are mostly Arabic-Indic digits that both readers already agree on.

Quick mode and the Tesseract setting are unchanged. Converter revision 58 re-converts scanned files.
