# Hidden Arabic OCR regression

`hidden-ocr.pdf` is synthetic: a raster Arabic/English scan with invisible
`render_mode=3` text placed over it. No external or user documents are included.

Expected OCR includes `مرحبا بالعالم` and `Invoice number 4826`.
Neither `HIDDEN_GARBLED_OCR_LAYER_9147` nor the reversed hidden phrase
`ملاعلاب ابحرم` may appear in exported Markdown.

`tests/make_fixtures.py` regenerates the PDF with `hidden_ocr_pdf()`.
The parameterized core regression also tests a smaller scan with a visible header,
ensuring render-mode detection works without the page-sized-image heuristic.

`boq-sample.pdf` is synthetic too (Cleanup22): an invented 8-item Arabic BOQ (storm drainage works,
quantities and SAR amounts made up, marked "نموذج توضيحي - البيانات غير حقيقية"), rendered from HTML
and degraded like a photocopy (0.9 degree skew, blur, noise, JPEG). `tests/test_cleanup22.py`
checks that all 24 amounts and the grand total survive the ruled-table reading.
