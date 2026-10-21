# Hidden Arabic OCR regression

`hidden-ocr.pdf` is synthetic: a raster Arabic/English scan with invisible
`render_mode=3` text placed over it. No external or user documents are included.

Expected OCR includes `مرحبا بالعالم` and `Invoice number 4826`.
Neither `HIDDEN_GARBLED_OCR_LAYER_9147` nor the reversed hidden phrase
`ملاعلاب ابحرم` may appear in exported Markdown.

`tests/make_fixtures.py` regenerates the PDF with `hidden_ocr_pdf()`.
The parameterized core regression also tests a smaller scan with a visible header,
ensuring render-mode detection works without the page-sized-image heuristic.
