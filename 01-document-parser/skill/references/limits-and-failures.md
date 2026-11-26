# Limits and failure handling

## Known limits

| Area | Limit | Consequence |
|---|---|---|
| Text source | PDF text layer only; no OCR engine is assumed | a scanned page is reported unreadable, never guessed |
| Formulas | glyph order and span flags are kept; no LaTeX conversion | quote formulas as strings |
| Tables | cells come from PyMuPDF's ruling-line detector | borderless tables can merge columns; review the grid against the page image |
| Reading order | recursive XY-cut with a geometric gutter | a page whose gutter moves mid-page can interleave; pass only that page range and re-check the overlay |
| Hyphen repair | the document's own hyphenated vocabulary decides | the first occurrence of a compound at a line break can lose its hyphen; recorded in `change_records` |
| Headers/footers | removed when the margin text repeats across pages | a one-off margin note stays in the body |
| Rotated text | detected and excluded as a watermark | a genuinely rotated table is dropped, not read |
| Languages | any language the PDF encodes | right-to-left and vertical scripts are extracted in glyph order, not layout order |

## Failure matrix

| Symptom | Detection | Action |
|---|---|---|
| `pymupdf` cannot open the file | exception on open | `status: failed`, reason in `result.json`; do not retry blindly |
| Empty `markdown`, `pages > 0` | every page in `unreadable_pages` | run OCR if the runtime has it; otherwise `partial` with every page named |
| `char_coverage < 0.98` | `stats` | read `uncertainty`, inspect the named pages, re-run those pages only |
| Sections empty but headings visible | `sections: 0` | the font-size heuristic failed (uniform font); fall back to `document.md` and mark the outline `structure_uncertain` |
| Table count lower than the page image | `tables` | add the missing table as a markdown figure and mark it `structure_uncertain` |
| Overlay order looks wrong | `--render` image | re-run with the page range; the gutter is reported per page in `layout.per_page` |

## Budget

One pass over 16 two-column pages takes under 20 seconds on the pinned runtime
(measured: 16.4 s for 12 pages, 18.0 s for 16 pages). A case budget of 900 s
therefore leaves room for a second pass on a suspicious page range.
