# Docs to MD 1.0.7 — converter revision 54

## Conversion change
- Bill-of-quantities rows: a heading or introduction above an item now goes with that item
  (Cleanup12). The previous item's unit ("عدد", "No.", "m") marks where that item ends, and the
  boundary is the first paragraph gap after it. Fixed examples: BOQs 1 page 18 (elbow and valve
  introductions "بالعدد توريد وتركيب ... التالية :-"), page 22 (special-fitting introduction),
  page 38 ("Section 16440 Switchboards ..." now starts item 3; items 3 and 4 no longer cut in the
  middle of item 3), page 39 ("Section 16060 Grounding and Bonding" now starts item 3).
- Paragraph gaps are measured in the description column only and must be at least 1.5 line
  heights, so wide English line spacing and stamp noise in the price columns no longer create
  false item boundaries. Only confidently read unit words count as an item's end.
- Items whose unit sits on the number line keep the earlier rule.

## Known limits
- The introduction of the first item on a page stays with the section heading row.
- Numbers in scanned tables still need checking against the page image.
