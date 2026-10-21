# Supported formats and limitations

This is a tested scope, not a claim that every object or layout in these formats is
recoverable. Every OCR result requires review; partial conversions have explicit warnings.

| Format | Implemented extraction | Important limits |
|---|---|---|
| PDF | Native page text, geometric reading order, ruled/native tables, scanned image regions, mixed pages, original images and page references | Scanned table structure/column relationships require visual review. Complex multicolumn reading order is heuristic. Password protection fails explicitly. Attachments are not extracted. |
| DOCX, DOCM | Headings, paragraphs, lists, tables, hyperlinks, images/OCR, headers, footers, footnotes/endnotes/comments, text boxes | Lists are represented as bullets; complex numbering is not reconstructed. Merged/nested tables, SmartArt, charts, unsupported image types and OLE objects are partial. Track-changes deletions are omitted; no macro execution. |
| DOC | Apache POI binary reader: body, heading/list styles, tables, images/OCR, headers/footers, footnotes/endnotes, text boxes | Complex layout, merged tables, field hyperlinks, charts and OLE objects are partial. Very old pre-Word-97 variants are not guaranteed. Header/footer story variants may repeat. No Office compatibility application is run. |
| XLSX, XLSM | Streaming XML stored values, all sheets in order, hidden states, sparse blocks, small merged HTML tables, common formatting, media images/OCR | Missing cached formula results are marked. Custom formats may fall back to values. Large/cross-block merges retain coordinates. Chart visuals are not rendered; no chart formulas, VBA, recalculation or external refresh. Images collected from workbook media are labelled as embedded rather than placed at exact cell anchors. |
| XLS | xlrd stored cell values and formatting, sheets/hidden states, merges; Apache POI embedded raster extraction | Charts/drawing shapes are not rendered. BIFF stores formula results in its cell records; validity/freshness cannot be recalculated. Some older unsupported BIFF variants fail explicitly. |
| PPTX, PPTM | Slide order/numbers, titles and text, tables, pictures/OCR, speaker notes, group shapes | SmartArt, charts, OLE objects, unsupported shapes, animation and complex slide layout are not reproduced. |
| PPT | Apache POI HSLF slide text/tables/pictures/OCR and notes | Unsupported drawing/OLE objects are warned. Slide master/background visual reconstruction is limited. |
| PNG, JPG, JPEG, TIFF, TIF, BMP, WEBP | Image link, local OCR, orientation detection/deskew, every frame/page | OCR can omit/misread text and digits. Orientation detection is less reliable on sparse graphics. All image pages are retained. |
| TXT | Encoding detection, preserved readable text in a safe Markdown code block | Uncertain non-UTF encodings generate a warning. |
| CSV, TSV | Quoted records, tables in bounded row blocks, escaped delimiters and line breaks | CSV uses comma; TSV uses tab. Other delimiter conventions are not auto-guessed. |
| HTML, HTM | Headings, paragraphs, links, tables, safe local in-tree raster images | Scripts/active objects and remote images are removed; no URL fetching. Styling is not retained. |
| MD | Exact byte-for-byte copy, intentional additional `.md` extension | Linked dependencies are inventoried but not rewritten/copied automatically. Original Markdown's active markup is not sanitized because exact copying is required. |
| Other | Inventoried as unsupported | XLSB, RTF, ODT, ODS, ODP, archives, media, CAD, executables and arbitrary formats are not supported in this release. |

Windows 11 Pro x64 build 26200 is the actual test platform. The Microsoft Store package
installs on Windows 10 version 2004 or later (x64). Windows 10, UNC shares, very long paths,
ARM and cross-drive use are not separately verified.
