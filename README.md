# Docs to MD

**Version 1.1.1 (conversion revision 58).** A Yassin Labs tool for Windows x64 that converts
whole folders of PDF, Word, Excel, PowerPoint, image and text files to Markdown, with
built-in Arabic and English OCR for scanned pages. Everything runs on your own computer:
no internet connection, account, API key, Python, Java, Microsoft Office or OCR
installation is needed, and no document leaves the computer.

- Microsoft Store: https://apps.microsoft.com/detail/9P14JB03S057
- Website and privacy policy: https://eyassen.github.io/docs-to-md/
- Supported formats and limits: [`SUPPORTED_FORMATS.md`](SUPPORTED_FORMATS.md)
- Arabic quick start: [`QUICKSTART_AR.md`](QUICKSTART_AR.md)
- What changed: [`RELEASE_NOTES_58.md`](RELEASE_NOTES_58.md)

Windows 11 x64 is the tested system. The Store package installs on Windows 10 version 2004
or later (x64); Windows 10, ARM and 32-bit Windows are not separately verified, and macOS
and Linux are not supported.

## Quick start

1. Install **Docs to MD** from the Microsoft Store and start it from the Start menu.
   With a portable build instead, extract the **whole** archive to a writable folder and
   run `DocsToMD.exe` inside the extracted `DocsToMD` folder. Move the entire folder,
   never the executable alone.
2. Choose your source folder and check the output location shown.
3. Press **Convert**.
4. When it finishes, use **Open output folder** or **View report**.

For `D:\Tender` the output is `D:\Tender\Tender_md`. Subfolders, including empty ones, are
mirrored, and full source names are kept: `Scope.docx` becomes `Scope.docx.md` and
`Notes.md` becomes `Notes.md.md`.

## What it reads

- **PDF**, including scanned pages, mixed text-and-scan pages and tables
- **Word** (.docx, .docm and legacy .doc), **Excel** (.xlsx, .xlsm and legacy .xls),
  **PowerPoint** (.pptx, .pptm and legacy .ppt)
- **Images** (PNG, JPG, TIFF, BMP, WEBP), **CSV**, **TSV**, **HTML**, **TXT** and **Markdown**

Other formats are listed in the report as unsupported. Corrupt or password-protected files
are reported and do not stop the run. [`SUPPORTED_FORMATS.md`](SUPPORTED_FORMATS.md) lists
what each format keeps and loses.

## Scanned pages (OCR)

Scanned pages and images are read offline in Arabic, English or both, including
Arabic-Indic digits. The **Standard** and **High** accuracy settings read the text with a
bundled PP-OCR engine run by ONNX Runtime. Tesseract straightens pages turned sideways,
removes coloured stamps before reading, reads ruled tables cell by cell and recognises
pages that are only noise. **Quick** reads each page in one Tesseract pass. If the OCR
engine is missing or fails on a page, that page is read by Tesseract and the report says so.

OCR is an approximate reading. Check numbers taken from scanned pages against the page
image the app keeps beside the text, and treat scanned table layout as a draft.

## Excel: saved values only

Every worksheet is included in workbook order, and hidden and very-hidden sheets are
labelled. For formula cells only the result saved in the file is exported. A missing saved
result is shown as **[Saved value unavailable]** and listed with its sheet and cell.

**Formulas, VBA, macro listings and chart-series formulas are never exported.** No
spreadsheet application is started, nothing is recalculated and no external link is
refreshed. Saved values reflect the last time the author saved the workbook.

Sparse sheets are written in labelled blocks of at most 200 occupied rows and 32 adjacent
columns, all in the same Markdown file.

## Settings, progress and repeat runs

Settings are collapsed at first. The defaults are: subfolders included, Arabic + English OCR,
images read automatically, Standard accuracy, all worksheets, and a per-file time limit
(default 3600 seconds, one hour). Large files may need a higher limit; the app reports a
timeout instead of silently cutting rows, columns or pages.

Progress shows the files found and finished, the current file and stage, and the elapsed
time. **Cancel** stops the job, keeps finished outputs and removes its temporary workspace.
Running the same folder again only converts files that are new or changed, or that failed;
unchanged files are skipped while their outputs still match the recorded hashes. Markdown
you edited by hand is never silently overwritten.

Each output folder has a `.foldertomd-data-...` folder with `INDEX.md`,
`conversion_report.md`, `manifest.json` and the extracted images. Keep it with the Markdown
files. The report lists every file as converted, with warnings, unchanged, unsupported,
failed, cancelled, excluded or obsolete, with the reason.

The Store version keeps its settings in `%LOCALAPPDATA%\DocsToMD\data`; a portable build
keeps them in the `data` folder beside the program.

## Offline and safe by design

No URL, remote image or link is fetched. Office macros are never run. Scripts and active
objects are removed from HTML. The bundled ONNX Runtime has its telemetry turned off.
Legacy `.doc`, `.ppt` and `.xls` drawing data are read by Apache POI on a private Java
runtime under a security policy that grants no network or subprocess access. Existing
`.md` files are copied byte for byte.

## Building from source

Build on Windows x64 with Python 3.14.4 and an internet connection; using the app needs
neither. From the source folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

The script creates `.venv`, installs `requirements.lock.txt`, downloads the pinned Tesseract,
Java runtime and Apache POI files and checks them against `dependencies.lock.json`, compiles
`java/LegacyReader.java`, runs the tests, freezes the app with `FolderToMD.spec` and completes
`dist\DocsToMD` with `scripts/package.py`. The OCR models in `ocr-models/` are copied into the
app; `scripts/make_ocr_models.py` reproduces them from the published PP-OCR models
distributed by RapidOCR.

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe scripts\acceptance.py --exe dist\DocsToMD\DocsToMD.exe --name packaged --expected-revision 58
.\.venv\Scripts\python.exe scripts\make_7z.py --zip <portable zip from package.py>
.\.venv\Scripts\python.exe scripts\make_msix.py
```

`make_7z.py` packs the portable 7z archive and checks it against `BUNDLE_SHA256.json`.
`make_msix.py` builds the Microsoft Store package; `--name`, `--publisher` and
`--publisher-name` take the values from Partner Center.

The test fixtures in this repository are synthetic. Some tests use private fixtures taken
from the author's own work documents; those are not published, and the tests that need
them skip themselves.

## Licence

Docs to MD is free software under the GNU Affero General Public License, version 3 or later
(see [`LICENSE`](LICENSE)). Copyright (C) 2026 Yassin Abd El Aal. Bundled components keep
their own licences: see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md), `licenses/` and
`ocr-models/MODEL_LICENSES.md`.
