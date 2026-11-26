# Parser contract

## Commands

```bash
python pdf_evidence_parser.py INPUT.pdf --out WORK [--render] [--render-pages 1,3]
python run_case.py --case CASE.json --task TASK.md --pdf INPUT.pdf \
    --work WORK --out OUT [--answers ANSWERS.json]
```

Both print one JSON line to stdout: `PARSE_OK {...}` / `CASE_OK {...}`, or
`CASE_FAIL {...}` with a reason. Exit code 0 means the artefacts were written.

## `parse.json`

| Field | Meaning |
|---|---|
| `schema` | `pdf-evidence-parse/1.0` |
| `source` | path, sha256, page count, bytes, parser version |
| `layout` | body font size, page sizes, per-page column detection incl. the gutter |
| `sections[]` | `id`, `title`, `level`, `number`, `page`, `paragraphs[]`, `evidence[]` |
| `sections[].paragraphs[]` | `text`, `kind` (`paragraph`/`caption`/`footnote`/`formula`/`table`/`reference_entry`/`byline`), `evidence`, `evidence_list` (all blocks a merged paragraph came from) |
| `tables[]` | `id`, `page`, `bbox`, `rows`, `cols`, `grid`, `markdown`, `html`, `cells`, `evidence` |
| `figures[]` | `id`, `page`, `bbox`, `caption`, `caption_evidence`, `labels[]`, `evidence` |
| `formulas[]` | `id`, `page`, `text`, `evidence`, `note` |
| `references` | `count`, `entries[]` (text + evidence) |
| `excluded[]` | header/footer/watermark/table-text removed, each with a reason and bbox |
| `stats` | character accounting and `char_coverage` |
| `unreadable_pages[]` | pages with fewer than 40 text-layer characters |
| `change_records[]` | every normalisation that touched the text, with counts |
| `uncertainty[]` | what the parser could not establish |
| `markdown` | the reading-order document used by `document.md` |

## `result.json`

| Field | Meaning |
|---|---|
| `case_id` | from `case.json` (`case_id`/`id`) or the PDF stem |
| `status` | `success`, `partial` (unreadable pages or coverage < 0.98), `failed` |
| `results` | every field named by `case.json`'s `output_contract` |
| `pending_fields` | contract fields the structural parse cannot answer; the agent must fill them |
| `evidence` | anchor list: page, block, bbox, owning section |
| `uncertainty` | inherited parser uncertainty plus one entry per pending field |
| `change_records` | normalisations applied |
| `run` | timestamp, parser version, paths, filled/pending field names |

`--answers answers.json` merges `{field: value}` into `results` for the fields a
reader must supply. Anything not supplied stays in `pending_fields` and in
`uncertainty` — the tool never invents an answer.

## Anchors

An anchor is `p<page>b<block>` (or `p<page>t<n>` for a table). Blocks are numbered
by the PDF text-block index, so an anchor stays valid for the same file version
(check `source.sha256`).
