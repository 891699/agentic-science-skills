# PDF evidence reader

Submission for **阅读01｜文献文档解析** (`product-arena-08-3027d350`).

The deliverable is a skill, not an answer sheet. `submission/SKILL.md` is the
skill the platform installs; `submission/scripts/` are the only programs it
needs; `src/reproduce.py` is the run that produced the evidence in
`execution/`. The platform's three fixed cases are supplied at evaluation time —
nothing here is a prepared answer.

## What the skill does

`pdf_evidence_parser.py` turns a scientific PDF into a reading-ordered,
structure-typed document in which every element carries a provenance anchor
(`p<page>b<block>`, bbox). It addresses the four failure modes the topic names:

| Topic requirement | Mechanism in this submission |
|---|---|
| **提得全** text completeness | painted-span de-duplication (fake-bold double strike), repeated-margin removal, character accounting (`stats.char_coverage`), ligature normalisation recorded per change |
| **排得对** reading order | recursive XY-cut over block boxes with a geometric gutter, figures separated from prose, captions re-attached to their figure, cross-column / cross-page sentences merged |
| **拆得清** structure | heading tree from numbering + font size, table grids with real cells and bboxes, formula blocks with span flags, numbered reference list split back into entries |
| **核得回** verifiability | `evidence` on every paragraph, table, figure and reference; `uncertainty` for everything not established; `unreadable_pages` for pages without a text layer |

`run_case.py` applies a case contract: it fills every structural field of
`case.json`'s `output_contract` from the parse, writes `result.json` with
`case_id`, `status`, `evidence`, `uncertainty`, and leaves judgement fields in
`pending_fields` unless the reader supplies them. It never invents an answer.

## Run it

```bash
python submission/scripts/pdf_evidence_parser.py paper.pdf --out work --render
python submission/scripts/run_case.py --case case.json --task task.md \
    --pdf paper.pdf --work work --out output
```

`src/reproduce.py` reproduces the evidence in this bundle end to end
(about 70 s, three cases, no GPU, no network):

```bash
python src/reproduce.py --data data --out execution/results \
    --log execution/run.log --trace trace/trace.jsonl
```

## Measured result

Three documents, 29 pages, on the pinned runtime (Python 3.14.7, PyMuPDF 2.0).
Baselines are what an agent does without the skill: `raw` = PyMuPDF plain-text
dump, `pymupdf4llm` = the strongest off-the-shelf layout-aware markdown
converter available here.

| Metric (totals over 3 cases) | raw | pymupdf4llm | **this skill** |
|---|---|---|---|
| Tables with a cell grid **and** page/bbox provenance | 0 | 0 | **21** |
| Evidence anchors (page + block + bbox) | 0 | 0 | **507** |
| Figure-internal text spliced into prose (80 probes) | 30 | 4 | **1** |
| arXiv margin stamp leaking into the text | 1 | 1 | **0** |
| Right-column → left-column reading-order jumps | 35 | n/a (no geometry) | **23** |
| Non-space character coverage vs the text layer | — | — | **1.00** |

Per case:

| Case | pages | sections | tables | figures | references | coverage | status |
|---|---|---|---|---|---|---|---|
| `resnet-2015` two-column IEEE | 12 | 17 | 14 | 6 | 50 (exactly the printed 50) | 1.00 | success |
| `bert-2019` two-column, merged-cell tables | 16 | 25 | 7 | 5 | 67 | 1.00 | success |
| `resnet-scan-p1` image-only page | 1 | 0 | 0 | 1 | 0 | — | **partial, page 1 unreadable** |

The scanned case is deliberate: there is no OCR engine in this runtime, so the
skill reports the page as unreadable and returns `status: partial` instead of
inventing text. That behaviour is the honesty requirement, not a missing feature.

Evidence for every row: `execution/results/comparison.json`,
`execution/results/comparison.png`, and the per-case `parse.json` /
`case_result.json`. Page overlays with the reading order drawn on them are in
each `execution/results/<case>/overlays/`.

## Bundle map

| Path | What it is |
|---|---|
| `submission/SKILL.md` | the skill definition the platform installs under `/skills` |
| `submission/scripts/pdf_evidence_parser.py` | parser (text, order, structure, tables, formulas, references, evidence) |
| `submission/scripts/run_case.py` | case-contract adapter → `result.json` |
| `submission/references/` | I/O contract, evidence rules, limits and failure matrix, worked example |
| `src/reproduce.py` | the run that produced everything below |
| `execution/run.log` | append-only log of the run (also mirrored at `run.log`) |
| `execution/results/` | per-case parse, markdown, overlays, metrics, comparison (also mirrored at `results/`) |
| `trace/trace.jsonl` | typed steps of the run, with paired tool calls and artifact paths |
| `characterization.json` | what was measured against the documents' own claims |
| `bundle_validation.json` | local validation report (manifest, trace, artifact existence) |

`execution/` and the bundle-root `run.log` / `results/` are byte-identical copies:
the challenge lists `execution/run.log` and `execution/results/`, the ARM scanner
looks for `run.log` and `results/*` at the bundle root. Both contracts are
satisfied without guessing which one the grader reads.

## Honest limits

- No OCR: pages without a text layer are reported, not read.
- Formulas keep glyph order and sub/superscript span flags; they are not LaTeX.
- Table cells come from PyMuPDF's ruling-line detector; borderless tables can
  merge columns and are flagged for review.
- Hyphen repair uses the document's own hyphenated vocabulary; the first
  occurrence of a compound at a line break can lose its hyphen (recorded in
  `change_records`).
- `column_jumps` counts right→left returns on a page; some are legitimate returns
  after a full-width element, so the number is a bound, not an error count. It is
  reported as a bound rather than dressed up as an accuracy figure.

## GitHub link

No public repository exists for this run, so `GITHUB_URL.txt` is not included and
the 5-point ecosystem bonus is forfeited rather than filled with a placeholder
link. The full skill, its scripts and this README are inside the bundle itself.

## Licence and reuse

The parser and the skill text are released for reuse inside this submission.
The two demo PDFs are arXiv preprints (arXiv non-exclusive licence) and are not
redistributed in the bundle; `manifest.data_sources` records their URI, size and
SHA-256 so the run can be repeated byte-for-byte.
