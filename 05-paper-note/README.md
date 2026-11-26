# Paper note

Submission for **阅读10｜文献总结与结构化笔记** (`product-arena-06-6d8cf72b`).

The deliverable is a skill, not a finished note. `submission/SKILL.md` is what the
platform installs; the scripts are the only programs it needs; `src/reproduce.py`
is the run that produced the evidence in `execution/`. The platform's three fixed
cases are supplied at evaluation time — the BERT run here is a demonstration on a
public paper, not an answer to those cases.

## What the skill does

A note is written against sentences extracted from the PDF, so every claim carries
a quote it cannot drift from. A verifier then re-checks the binding.

| Topic requirement | Mechanism |
|---|---|
| **对得上** follows the paper | the note's section list is the parsed outline; the verifier requires a role line for every section |
| **留得住** keeps the conditions | the card has fixed fields including **conditions** and **limitations**, not only findings |
| **找得回** traceable | a claim may only cite a `quote_id`; the verifier resolves it, matches it verbatim against the source and requires every claim number to appear in that quote |
| **用得上** reusable | one `result.json` with a fixed card and per-claim records, one `note.md`, diffable across papers |

## Measured result (BERT, EN paper → Chinese note)

| Metric | Value |
|---|---|
| Sections in the paper / in the note | 25 / **25** (coverage 1.00) |
| Quotable candidates extracted | 133 |
| Claims written | **31**, across 9 sections |
| Card fields | research question, data, method, **3 conditions**, 3 findings, 2 limitations, reuse |
| Hard grounding failures | **0** (quote resolution, verbatim match, number grounding, coverage, anchors, card, uniqueness) |
| Gate sensitivity | **7/7** injected defects detected (unknown quote, invented number, missing section, empty role, empty card, duplicate claim, bad anchor) |
| First draft | 2 defects caught before submission (`11` where the paper says "eleven"; missing title section) |
| Runtime | 15 s local, no network, no GPU |

The first-draft line is the point: a summary can read correctly and still contain
an unsourced number or a missing section. The verifier caught both.

## Bundle map

| Path | What it is |
|---|---|
| `submission/SKILL.md` | skill definition installed under `/skills` |
| `submission/scripts/prepare.py` | outline + quotable candidates (with page/block/anchor) |
| `submission/scripts/verify_notes.py` | grounding gate (+ `--selftest`) |
| `submission/scripts/run_case.py` | case-contract adapter → `result.json` + `note.md` |
| `submission/references/` | workflow, note schema, QA rules |
| `src/reproduce.py` | the run that produced everything below |
| `execution/run.log` | append-only log (mirrored at `run.log`) |
| `execution/results/` | outline, candidates, note, QA report, metrics, case result, `note.md` (mirrored at `results/`) |
| `trace/trace.jsonl` | typed steps with paired tool calls and artifact paths |
| `characterization.json` | what was measured against the source |
| `bundle_validation.json` | local validation report |

## Honest limits

- Claims are the model's reading; the skill guarantees the quote and the numbers,
  not the interpretation.
- The verifier proves a quote exists and contains the claim's numbers; it does not
  prove the claim is the only sensible reading.
- Section boundaries come from PDF typography; unusual headings may need one
  manual correction.
- Numbers that live only in a table body are not asserted unless a quoted caption
  carries them.
- No OCR: a scanned page is reported unreadable rather than summarised from guesswork.

## GitHub link

No public repository exists for this run, so `GITHUB_URL.txt` is not included and
the 5-point ecosystem bonus is forfeited rather than filled with a placeholder.

## Licence and reuse

The skill and scripts are released for reuse within this submission. The demo PDF
is an arXiv preprint (arXiv non-exclusive licence) and is not redistributed in the
bundle; `manifest.data_sources` records its URI, size and SHA-256.
