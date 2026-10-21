# DocsToMD 1.0.2 — revision 49

This update repairs confirmed number-recognition and text-loss failures in the latest conversion. It does not certify the 28-file corpus as accurate.

## Changes

- Weak inline number readings in Arabic scan cells can be recovered from local pixels. Arabic digits compete with Latin letters and punctuation; ambiguous readings are retained. Protected signs, decimals, fractions, percentages, leading zeros and strong readings are unchanged. Recovery is bounded and reported as a review warning.
- Table assembly keeps distinct rows that share a vertical coordinate. The old lookup overwrote one row and duplicated another, dropping correctly recognized specification values.
- Tiny bullet glyphs use the existing line height when grouping words. Ordinary wrapped table lines retain their previous behavior.
- Broken vertical border remnants can be removed at cell edges without erasing short character strokes.
- Conversion revision 49 invalidates the older conversion cache when the new executable is used.

## Targeted source evidence

BOQs 1, physical page 3: recover PN16 from the erroneous 160 reading and recover 25 cm from YO. The PN punctuation/order still needs review.

BOQs 2, physical page 34: preserve each of these English specification lines once, including 10 mm, 75 mA at 24Vdc, and the 3.5 m cable. The earlier output falsely assembled these lines as a duplicated table and lost the numbers.

The prior native-table fix is checked on Prime Document page 8: seven columns, correctly owned dates and retained fee punctuation.

## Remaining issues and review limits

Fresh source-pixel review confirmed other errors in BOQs 1 pages 6 and 27, BOQs 2 page 1, BOQs 2 page 34's main quantity rows, and MOM page 5. These include diameter/capacity values, missing clauses, and item/unit/quantity ownership. This release does not claim to resolve them; use the original page images to verify quantities and specifications.

Correction to the earlier review: BOQs 2 page 1's second quantity is **34**, not 24. A fresh 400 dpi crop confirmed the source value.

The latest revision 48 corpus contained 28 inputs and 2,738 pages/frames. All inputs completed with review warnings. Historical findings were mapped against those outputs, but only selected pages were freshly compared with original pixels. Completion and matching hashes do not establish transcription accuracy.

## Validation

See `ACCEPTANCE_REPORT.md`, `verification/`, and the accompanying `delivery-verification.json` for the recorded source tests, frozen-executable checks, targeted page gates, runtime checks and archive hashes. Private source-page fixtures are excluded from the public source ZIP; tests that require them are explicitly guarded.

The packaged runtime is exercised with a stripped PATH, invalid external cache locations and blocked proxy settings. Execution on a separate clean Windows machine remains unverified.

## Install and test

1. Close the previous DocsToMD application.
2. Extract `DocsToMD-1.0.2-revision49-Windows-x64-Portable.zip` into a new folder. Keep the complete `DocsToMD` directory together.
3. Run `DocsToMD.exe` from that extracted folder and select your input folder. The new revision refreshes older cached conversions.
4. Inspect the conversion report, warnings and original page images. Check quantities with their item descriptions and units; the mere presence of a number is insufficient.

The previous release and existing Sample PDF conversion are preserved during delivery. A complete new corpus conversion has not been run as part of this release validation.
