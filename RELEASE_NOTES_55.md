# Docs to MD 1.0.8 — converter revision 55

## Conversion change
- Bill-of-quantities introductions shared by the items below them are now a row of their own
  without a number, as printed (Cleanup14). Until now Cleanup12 merged such an introduction into
  the first item under it, which made it look as if it belonged to that item only. An
  introduction is recognised when it is a paragraph between the previous item's unit line and the
  item line, separated from the item line by a paragraph gap or ending with ":-"
  ("بالعدد توريد وتركيب ... للأقطار التالية :-").

## Known limits
- An introduction printed directly against the item line, with no gap and no ":-" (for example
  BOQs 2 page 16 "قسم ٠٩٣١٠ بلاطات السيراميك ..."), stays merged with the first item under it.
- A heading printed directly above an item ("Section 16440 ...") stays with that item.
- The introduction above the first item of a page stays in the section heading row.
- Numbers in scanned tables still need checking against the page image.
