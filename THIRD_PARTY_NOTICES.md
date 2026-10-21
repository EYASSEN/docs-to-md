# Third-party notices and source locations

FolderToMD source is AGPL-3.0-or-later (`LICENSE`). Each third-party component keeps its
own license. Notices and license texts are included under `licenses/`, in the OCR
distribution's `doc/`, in the JRE's `legal/`, and inside each Java JAR's `META-INF/`.
The complete files, versions and SHA-256 hashes are recorded in `BUNDLE_SHA256.json`,
`requirements.lock.txt`, and `dependencies.lock.json`.

## Principal runtime components

| Component | Version | License / source |
|---|---|---|
| Python / Tcl-Tk | Python 3.14.4 and its bundled Tcl/Tk | PSF and Tcl/Tk licenses; https://www.python.org/downloads/release/python-3144/ |
| PyInstaller bootloader | 6.19.0 | GPL-2.0-or-later with bootloader exception; https://github.com/pyinstaller/pyinstaller/tree/v6.19.0 |
| PyMuPDF / MuPDF | 1.26.7 / 1.26.12 | AGPL-3.0; https://github.com/pymupdf/PyMuPDF/tree/1.26.7 and https://github.com/ArtifexSoftware/mupdf/tree/1.26.12 |
| Pillow | 12.1.0 | HPND/Pillow license; https://github.com/python-pillow/Pillow/tree/12.1.0 |
| openpyxl | 3.1.5 | MIT; https://foss.heptapod.net/openpyxl/openpyxl |
| xlrd | 2.0.2 | BSD; https://github.com/python-excel/xlrd/tree/2.0.2 |
| defusedxml | 0.7.1 | PSF; https://github.com/tiran/defusedxml/tree/v0.7.1 |
| charset-normalizer | 3.4.4 | MIT; https://github.com/jawah/charset_normalizer/tree/3.4.4 |
| Beautiful Soup / soupsieve | pinned in requirements.lock.txt | MIT; https://www.crummy.com/software/BeautifulSoup/ and https://github.com/facelessuser/soupsieve |
| markdownify | 1.2.2 | MIT; https://github.com/matthewwithanm/python-markdownify/tree/1.2.2 |
| psutil | 7.2.1 | BSD-3-Clause; https://github.com/giampaolo/psutil/tree/release-7.2.1 |
| Tesseract Windows build | 5.5.0.20241111 | Apache-2.0; https://github.com/tesseract-ocr/tesseract/releases/tag/5.5.0 |
| tessdata_fast Arabic, English, orientation | tag 4.1.0 | Apache-2.0; https://github.com/tesseract-ocr/tessdata_fast/tree/4.1.0 |
| ONNX Runtime | 1.31.0 | MIT; https://github.com/microsoft/onnxruntime/tree/v1.31.0 |
| NumPy | 2.5.4 | BSD-3-Clause; https://github.com/numpy/numpy/tree/v2.5.4 |
| pyclipper | 1.4.0 | MIT; https://github.com/fonttools/pyclipper |
| protobuf / flatbuffers | 7.36.2 / 25.12.19 | BSD-3-Clause / Apache-2.0; https://github.com/protocolbuffers/protobuf and https://github.com/google/flatbuffers |
| python-bidi | 0.6.7 | LGPL-3.0, kept as a separate replaceable module; https://github.com/MeirKriheli/python-bidi |
| OCR models (PaddleOCR via RapidOCR 3.10.0): PP-OCRv6 det small (int8), PP-OCRv6 rec small, arabic PP-OCRv5 rec mobile (int8) | see vendor/ocr-onnx/NOTICE.md | Apache-2.0; https://github.com/PaddlePaddle/PaddleOCR and https://github.com/RapidAI/RapidOCR |
| Eclipse Temurin JRE | 17.0.18+8 x64 Windows | GPL-2.0 with Classpath Exception; https://github.com/adoptium/temurin17-binaries/releases/tag/jdk-17.0.18%2B8 and https://github.com/adoptium/jdk17u/tree/jdk-17.0.18%2B8 |
| Apache POI / poi-scratchpad | 5.4.1 | Apache-2.0; https://github.com/apache/poi/tree/REL_5_4_1 |
| Commons Codec, Collections, Math, IO; Log4j API | pinned in dependencies.lock.json | Apache-2.0; sources and notices are available beside their JARs at https://repo.maven.apache.org/maven2/ |
| SparseBitSet | 1.3 | Apache-2.0; https://github.com/brettwooldridge/SparseBitSet |

The OCR Windows distribution includes native codec, compression, text, network-support,
and C/C++ runtime DLLs. They are redistributed unchanged from the upstream installer;
the application invokes OCR only on image bytes and local language files. See the
additional native notices under `licenses/native/`. GCC runtime libraries use the GCC
Runtime Library Exception; LGPL components remain separate replaceable DLLs. Their
upstream corresponding-source/build locations are recorded there. OpenSSL, libcurl,
and similar support libraries do not cause the application to fetch document URLs.

No fonts were copied from this PC into the distribution. OCR uses trained data, and
normal GUI font rendering uses the destination Windows fonts. The JRE's own legal
notices cover its distributed components.

Revision 49's static 32x32 comparison images were rendered from Liberation Sans,
Liberation Serif and Carlito supplied with the build-only LibreOffice installation.
These are raster glyph comparisons for recognition, not installed fonts. Upstream
font projects: https://github.com/liberationfonts/liberation-fonts and
https://github.com/googlefonts/carlito (SIL Open Font License 1.1).
The OFL FAQ covers graphics created with these fonts:
https://openfontlicense.org/ofl-faq/ (sections 1.1–1.1.2).

## Source and build tools

The separate `FolderToMD-Source.zip` contains the complete application Python and Java
source, build scripts, synthetic regression fixtures, packaging spec, and actual test
reports. Unmodified third-party source is available from the exact release/tag links
above and the Maven `-sources.jar` artifacts. AGPL/GPL components are explicitly named
so recipients can obtain their corresponding upstream source and build instructions.
Application code can be rebuilt or modified with the included scripts.

Eclipse compiler ECJ 3.40.0, 7-Zip 24.09 and the standalone 7zr acquisition tool are
build-only; they are not copied into the portable app. Python DOCX/PPTX/XLSX fixture
writers, pytest and arabic-reshaper are also build/test-only (python-bidi is now a runtime
component of the ONNX OCR reader, Cleanup17). LibreOffice
25.8.4.2 was used only to generate the included binary Office fixtures and is not shipped.


## Tesseract tessdata_best models (ara_best, eng_best)
Source: https://github.com/tesseract-ocr/tessdata_best (tag 4.1.0). License: Apache License 2.0 (same as the bundled tessdata_fast models).
