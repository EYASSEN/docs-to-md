# DocsToMD 1.0.1 — converter revision 48

Corrective portable Windows release, 2026-10-10.

## Changes

- Reject cleaned OCR when its numeric tokens disagree with the original reading, even when confidence improves. Keep the original OCR image and reading and emit a review warning. Compare digit scripts without discarding signs, decimal places, or leading zeroes. This prevents unsafe replacements; it does not establish that the original OCR number is correct.
- Preserve valid word-final Arabic fathatan regardless of how many marks occur on a line. Previously, four valid marks triggered aggressive deletion. Existing between-letter and misplaced-mark cleanup remains. Some ambiguous font noise is deliberately preserved rather than deleting potentially valid text.
- Detect native PDF tables from rules rather than shaded backgrounds and preserve left-to-right punctuation in English cells. The reviewed Prime Document physical page 8 now has two rows and seven columns, with distribution/submission dates and bond validity under their correct headers.
- Increment the conversion revision so cached conversions are reconsidered. Keep the preceding portable release and the reviewed conversion outputs intact.
- Support a separate versioned packaging destination and include evidence for this revision rather than earlier acceptance runs.

## Validation and limits

Release validation is recorded in the accompanying verification files: full source tests with private fixtures required, packaged executable acceptance with revision 48 enforced, and a fresh conversion of the affected native table page. Bundle hashes and ZIP integrity are checked before delivery.

This release addresses the reproduced code defects. It does not resolve all corpus findings: scanned Arabic and engineering tables still need verification against source pages, particularly amounts, dimensions, missing clauses, and quantity/unit ownership. The preceding review structurally checked all 28 inputs but completed visual review of only 109 of 2,738 pages/frames. No corpus-wide accuracy percentage is claimed. A clean-machine offline run remains unverified.

## Running this release

Extract the versioned portable ZIP and launch `DocsToMD/DocsToMD.exe` or its launcher. Keep the complete folder, including `vendor` and `_internal`. Use a separate output folder when comparing revision 48 with the original conversions. The new build is under `release/revision48/build/DocsToMD`; the previous `dist/DocsToMD` remains revision 47.

Source code is supplied in the separate revision 48 source archive. Private document fixtures are excluded from that archive; tests that require those fixtures need the original local corpus.
