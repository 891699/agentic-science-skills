---
name: pdf-evidence-reader
description: "Read a scientific PDF into a verified, evidence-anchored structure before answering, translating, extracting or checking anything from it. Trigger on: parsing a paper, two-column PDF, reading order, table extraction, section outline, references, footnote, formula fidelity, scanned PDF, 'read this paper', 'what does the paper say', 'extract table 2', 'which page says', 'translate the abstract', 'compare with the paper'. Use it whenever a question about a document must be answerable by pointing back to a page and a block."
---

# PDF Evidence Reader

## Requirements

- Python 3.10 or newer.
- PyMuPDF for PDF access: `pip install pymupdf==2.0` (the Docker image pins the same version).
- No other dependencies; the run needs no network access.


Turn one PDF into a structure you can quote. Every sentence, heading, table and
caption this skill emits carries a pointer back to the page and block it came
from, so an answer built on it can be checked by a human or a grader without
re-reading the whole paper.

The skill fixes the four failures that make PDF reading unreliable:

| Failure | What goes wrong without it | What this skill does |
|---|---|---|
| **Missing text** | dropped lines, header/footer glued onto prose, duplicate glyph runs from fake-bold rendering | de-duplicates painted spans, removes repeated margin text, reports character coverage |
| **Wrong order** | left and right column interleaved, captions detached, figure labels spliced into a sentence | recursive XY-cut reading order, figure regions separated from prose |
| **Broken structure** | no section tree, tables turned into word salad, formulas destroyed | heading tree by numbering + font, table grids with real cells, formula blocks preserved |
| **No provenance** | a claim you cannot check; a gap quietly filled with a guess | page/block/bbox anchors on every element, explicit uncertainty and status |

## When to use it

Use it before answering anything that depends on a document: reading a paper,
translating a section, extracting parameters or tables, checking a claim,
building a reading note, comparing a reproduction with the original. Do not
answer from a raw `pdftotext` dump — that is exactly the input this skill exists
to replace.

## What it needs

- The PDF itself (the platform supplies it at `/input/`, next to `case.json` and `task.md`).
- Python 3 with PyMuPDF (`pymupdf` / `fitz`), installed with `pip install pymupdf==2.0`.
- No network, no model calls, no OCR engine required for text-layer PDFs.

## Run it

Paths below are relative to **this skill's own directory** — the directory the
loader reports as the resource base (for example `/skills/weekly-skill`). If the
shell's working directory is somewhere else, `cd` into the skill directory first
or pass the absolute path to the script; `python scripts/...` only resolves when
the working directory is the skill directory.

```bash
# 1. Structure the document (writes parse.json, document.md, structure.json)
python scripts/pdf_evidence_parser.py INPUT.pdf --out WORK --render

# 2. Apply the case contract (reads case.json + task.md, writes result.json)
python scripts/run_case.py --case /input/case.json --task /input/task.md \
    --pdf INPUT.pdf --work WORK --out /app/output
```

`--render` writes page images with the reading order drawn on them; keep them
when the case needs a visual check or a page-level screenshot.

`run_case.py` also works with no `case.json` fields: it falls back to a generic
contract and still writes `result.json`.

## Output contract

`WORK/parse.json` — the full structure:

```json
{
  "schema": "pdf-evidence-parse/1.0",
  "source": {"path": "...", "sha256": "...", "pages": 12},
  "sections": [{"id": "sec-3", "title": "Deep Residual Learning", "level": 1,
                "number": "3", "page": 3,
                "paragraphs": [{"text": "...", "kind": "paragraph",
                                "evidence": {"anchor": "p3b2", "page": 3, "bbox": [...]}}]}],
  "tables": [{"id": "tbl-p5-1", "page": 5, "rows": 9, "cols": 7,
              "grid": [["layer name", "output size", "..."]], "markdown": "..."}],
  "figures": [{"id": "fig-1", "page": 1, "bbox": [...], "caption": "Figure 1. ..."}],
  "formulas": [{"id": "eq-1", "page": 3, "text": "y = F(x, {Wi}) + x. (1)"}],
  "references": {"count": 52, "entries": [{"text": "[1] Y. Bengio ...", "evidence": {...}}]},
  "stats": {"char_coverage": 1.0, "...": "..."},
  "unreadable_pages": [],
  "change_records": [{"change": "ligature_normalization", "count": 157}],
  "uncertainty": []
}
```

`document.md` — reading-order markdown; every block ends with `<!-- p3b2 -->`.

`result.json` — the case answer: `case_id`, `status`, every field named by
`case.json`'s `output_contract`, plus `evidence`, `uncertainty`, `limits`,
`run` metadata.

## How to answer with it

1. Read `structure.json` first: section outline, table list, figure list,
   reference count, `stats.char_coverage`, `unreadable_pages`.
2. Open `document.md` at the sections the task names. Quote from it verbatim.
3. For every claim in the answer, attach the anchor of the block it came from
   (`p3b2`) and the human-readable page (`p. 3`).
4. Table values come from `tables[].grid`, never from re-typing the prose
   around the table.
5. When the document does not report something, write `not_reported` and say
   which page range you checked. Never fill a gap with plausible-sounding text.
6. When `unreadable_pages` is non-empty, the honest status is `partial`, and the
   answer must name those pages as unreadable rather than silently skipping them.

## Self-check before you finish

Run these five checks; they are cheap and they catch almost every real error:

1. `stats.char_coverage == 1.0` — otherwise some text was dropped; inspect the
   pages named in `uncertainty`.
2. Section count matches the paper's own outline (compare with the rendered
   first page).
3. Each table you rely on has `rows x cols` you can see on the page image.
4. Re-read three quoted passages against the PDF page image — do not trust the
   text layer alone for numbers or symbols.
5. Every `not_reported` / uncertain item names what was checked.

## Failure handling

| Situation | Detection | What to do |
|---|---|---|
| Scanned page, no text layer | `unreadable_pages` non-empty, page chars < 40 | run the OCR tool if present; otherwise report `partial` and name the pages |
| Encrypted PDF | `pymupdf` raises on open | report `failed` with the reason; do not retry silently |
| Rotated page / landscape | `layout.page_sizes` and block bboxes disagree with text flow | rotate the page (`page.set_rotation`) before parsing, note it in `change_records` |
| Borderless table | `tables` empty where the page image shows a grid | fall back to the table text block and mark it `structure_uncertain` |
| Formula fidelity | formula blocks keep glyph order only | quote the formula as a string; do not rewrite it as LaTeX unless the task asks |
| Two columns interleaved | a sentence reads across unrelated paragraphs | check `layout.per_page[].gutter`; if the gutter moved mid-page, re-run on the page range only |

## Limits worth stating in an answer

- Text comes from the PDF text layer; this skill does not invent OCR results.
- Formula sub/superscripts are captured as span flags and glyph order, not as LaTeX.
- Merged table cells are reported through the cell grid; review borderless tables.
- Header/footer removal keys on repeated margin text; a one-off margin note stays in the body and is flagged.


## Minimal example

Input: a 3-page paper at `input/paper.pdf`.

```bash
python scripts/pdf_evidence_parser.py input/paper.pdf --out work --render
```

示意输出（示例，非正式答案）:

```json
{"pages": 3, "sections": 7, "blocks": 46, "tables": 1, "figures": 2,
 "references": 21, "coverage": 0.96, "out": "work/parse.json"}
```

The numbers describe this documentation example only; a real run reports what it finds,
and a page it cannot read is listed as unreadable instead of being guessed.

See `references/` for the full I/O contract, the evidence rules and a worked example.
