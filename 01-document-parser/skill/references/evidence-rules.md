# Evidence rules

Every statement in an answer must survive a check that costs the reader one
minute. These rules keep that true.

## 1. Quote, do not paraphrase, for anything numeric

Parameters, table cells, ranges and percentages are copied from
`tables[].grid` or from a paragraph in `document.md`, together with its anchor.
If the text layer and the page image disagree, the image wins and the
disagreement is reported.

## 2. One anchor per claim, one claim per anchor

A citation is `p3b12` (page 3, block 12) or `p5t1` (page 5, table 1). A paragraph
merged from several blocks keeps `evidence_list`, so a claim that spans a column
break can cite both halves.

## 3. Never fill a gap

Three outcomes are allowed:

| Outcome | How to write it |
|---|---|
| reported | value + anchor |
| not reported | `not_reported` + the page range you checked |
| unreadable | `unreadable` + the page (from `unreadable_pages`) |

`not_reported` is a result, not a failure. A plausible value invented to fill a
table cell is the one error a grader cannot forgive.

## 4. Say which is structure and which is interpretation

`sections`, `tables`, `figures`, `references` are extracted structure — they can
be verified mechanically. A summary, a translation or a conclusion is
interpretation: mark it as such and point at the blocks it rests on.

## 5. Report the document's own defects

Missing pages, a broken reference number, a table whose caption does not match
its content, two columns that overlap: these belong in the answer under
`uncertainty`. They are evidence of careful reading, not noise.

## 6. Keep the change record honest

Ligature normalisation, line-break hyphen repair, header/footer removal and
paragraph merging all modify the text. Each is counted in `change_records`; quote
that record when a reader asks why a word looks different from the page image.
