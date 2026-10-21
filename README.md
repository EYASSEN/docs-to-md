# Docs to MD — portable Windows document converter

**Release candidate 1.0.0-rc3.** A Windows x64 desktop application with bundled Python,
Arabic/English Tesseract OCR, and a dedicated Apache POI legacy Office reader with its
own Java runtime. No Python, Java, Microsoft Office, LibreOffice, OCR installation,
account, API key, or ordinary-use internet connection is needed on the destination PC.

Read `ACCEPTANCE_REPORT.md` for the actual test evidence and unverified release gates.
The executable was built on Windows 11 Pro x64, build 26200. All 16 core tests,
39 source integration checks and 39 packaged-executable integration checks passed.
The earlier rc2 executable was blocked by Windows Application Control; this rc3
build launched successfully. Clean-machine offline portability remains unverified. Windows 10,
ARM, 32-bit Windows, macOS, and Linux are not verified targets.

## Quick start

1. Extract **all** of `DocsToMD-Windows-x64-Portable.zip` to a writable folder.
2. Open the extracted `DocsToMD` folder and double-click **DocsToMD.exe**.
   `Launch_DocsToMD.bat` is an optional equivalent launcher.
3. Choose your source folder, check the displayed output location, and press **OK / Convert**.
4. Use **Open output folder** or **View report** when processing finishes.

For `D:\Tender`, the output is `D:\Tender\Tender_md`. Subfolders, including empty
folders, are mirrored. Complete source filenames are retained: `Scope.docx` becomes
`Scope.docx.md`, and `Notes.md` becomes `Notes.md.md`.

Move the **entire** extracted application folder, not just its executable. To make a
desktop shortcut, right-click `DocsToMD.exe`, choose **Show more options → Send to →
Desktop (create shortcut)**. The shortcut must point to the executable in its current
location. No installer, elevation, PATH editing, or registry setup is required.

## Settings and progress

Settings are collapsed initially. Defaults are recursive conversion, Arabic + English
OCR, automatic reading of images, retention of visuals, all worksheets, and updates to
changed inputs. Optional settings select Arabic, English, or both, disable OCR, and
change the per-file timeout (default 3600 seconds, one hour). Large files may need a higher limit.
The app reports timeouts instead of silently limiting rows, columns, pages, or content.

Progress shows discovered/completed counts, current file, current stage, and elapsed
time. There is no estimated finishing time. **Cancel** stops this job's worker tree,
keeps completed outputs, and removes its temporary conversion workspace. Run the same
folder again to resume. Closing the app during a job requests cancellation first.

## Excel: contents and saved values only

Every worksheet is included in workbook order; hidden and very-hidden sheets are
labelled. Literal strings, zeros, booleans, dates, numbers, common number formats, and
saved error values are exported. For formula cells, only the stored result is exported.
An absent OOXML formula cache is shown as **[Saved value unavailable]** and reported
with the sheet/cell reference. A literal string starting with `=` remains ordinary text.

**Formula expressions, VBA source, macro listings, calculation reports, and chart-series
formulas are never exported.** No spreadsheet application is launched, no formula is
recalculated, no query or external link is refreshed, and the source is never saved.
Cached values can be stale: they reflect the last result saved by the workbook's author.

Sparse sheets are emitted in coordinate-labelled blocks of at most 200 occupied rows
and 32 adjacent columns, with every block retained in the same Markdown file. Large
formatted-but-empty areas do not become huge empty tables. Small merged regions use
HTML tables; exact merged coordinates are listed for larger/cross-block regions.
Complex custom formats fall back to underlying values with a warning.

## Reports, assets, and repeat runs

The output has an ownership marker and a uniquely named `.foldertomd-data-...` folder.
That metadata area contains `INDEX.md`, `conversion_report.md`, `manifest.json`, assets,
and the job lock. Keep it with the Markdown files when moving the output folder.
Asset links are relative and do not require the source folder after conversion.

Statuses distinguish converted, partial (shown as **With warnings**), unchanged,
unsupported, failed, cancelled, excluded, and obsolete. The report inventories every
discovered file and records elapsed times, warnings, counts, settings, hashes, and
backend/model versions. OCR is approximate and is reported with review warnings.
Scan table layout is not guaranteed; visual references are retained.

Successful unchanged files skip only while their generated Markdown and assets still
match the recorded hashes. Changed sources/settings are reprocessed; failed files retry.
Output is staged per file and replaced atomically. When replacement fails, the previous
output remains and is labelled stale. A file changed during reading is rejected for a
later retry. Manually edited generated Markdown or assets are not silently overwritten:
move your edited copy elsewhere, then remove the conflicting generated file to regenerate.
For an edited asset, preserve your output folder and choose a fresh output root (rename
the existing generated root) before rerunning.

Deleted source files leave their previous generated outputs in place as **obsolete**;
they are removed from the current-success index. Old asset generations are retained to
avoid deleting content that may still be referenced. The app never prunes unrelated data.
Do not edit ownership markers or manifests. Simultaneous jobs for one output root are
blocked by an operating-system file lock.

Application-generated roots are excluded when converting them again or scanning their
parent. Legitimate source folders ending in `_md` remain eligible. Junctions/symlinks
are skipped; Office `~$` lock files are excluded with a reason. An existing unowned
output folder causes a conflict instead of being adopted. A drive root maps to
`C:\C_md`; a UNC share root maps to a sanitized server/share anchor name ending in
`_md`. UNC and extreme Windows long-path cases have not been verified; failures are
reported without truncating or renaming inputs.

## Offline behavior and limitations

No URLs, remote images, formulas, or hyperlinks are fetched. Office macros are never
executed. HTML scripts and active objects are removed. Existing `.md` files are copied
byte-for-byte, including their original markup: referenced resources are inventoried
and unresolved dependencies are warned about, rather than rewriting the source.

Tesseract's binaries, English/Arabic/orientation language files, and its DLLs are bundled.
There are no downloaded layout models or first-run downloads. Python document workers
deny socket connections. Legacy `.doc`/`.ppt` reading uses Apache POI under Java 17's
security policy without network or subprocess permissions; it reads temporary copies.
The Java runtime is private to the application and is not installed system-wide.

See `SUPPORTED_FORMATS.md` for concrete limitations: scanned tables, complex document
layout, chart rendering, vector images, nested/merged Office tables, and embedded OLE
objects may need review. Unsupported formats are reported and do not get empty
success-labelled output. Corrupt or password-protected inputs do not stop the batch.

Settings live in `DocsToMD\data\settings.json`. If the application folder is read-only,
move it to a writable location. Per-file workspaces live under the owned output metadata
folder and are cleaned after processing; abandoned workspaces are cleaned on the next
run while holding the output lock. This is not a promise of zero Windows execution traces.

## Building and testing from source

Build on Windows x64 with Python **3.14.4**, internet access, and sufficient free space.
Normal application use does not require these build tools. From the source folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

The script creates a local `.venv`, installs `requirements.lock.txt`, verifies/downloads
the pinned OCR, JRE, and POI artifacts, compiles `java/LegacyReader.java`, runs the core
tests, freezes the app with `FolderToMD.spec`, and builds the portable ZIP. Dependency
downloads are build-only and checked against `dependencies.lock.json`. The initial
dependency lock records TLS-fetched artifact hashes; the JRE hash also matches its
upstream GitHub release digest. Subsequent acquisition rejects mismatches. `7zr.exe`
uses an upstream mutable URL, so a later upstream replacement correctly fails until
the maintainer deliberately audits and updates the lock.

```powershell
.\.venv\Scripts\python.exe scripts\acceptance.py --exe dist\DocsToMD\DocsToMD.exe --name packaged
.\.venv\Scripts\python.exe -m pytest tests\test_core.py -q
```

Acceptance scripts generate synthetic fixtures; no user documents are uploaded.
The included binary `.doc` and `.ppt` fixtures were generated from the synthetic
DOCX/PPTX fixtures with a build-time-only LibreOffice 25.8.4.2 extraction. LibreOffice
is **not** a runtime dependency or part of the final portable app. The optional
fixture regeneration script requires that separate build tool; existing fixtures
are included for ordinary test/build use.

Source code is under AGPL-3.0-or-later; bundled components retain their own licenses.
See `LICENSE`, `THIRD_PARTY_NOTICES.md`, `licenses/`, and the dependency source links.
