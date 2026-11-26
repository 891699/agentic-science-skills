# Paper translator

Submission for **阅读03｜文献翻译** (`product-arena-01-5a9928c1`).

The deliverable is a skill, not a finished translation. `submission/SKILL.md` is
what the platform installs; `submission/scripts/` are the only programs it needs;
`src/reproduce.py` is the run that produced the evidence in `execution/`. The
platform's three fixed cases are supplied at evaluation time — the page-1 run
here is a demonstration on a public paper, not an answer to those cases.

## What the skill does

Translation itself is the model's job. The skill makes the *result* checkable by
turning the paper into fixed paragraph ids, locking the terminology, and running
a mechanical gate over every segment before a translation is accepted.

| Topic requirement | Mechanism |
|---|---|
| **术语稳** terminology stable | `glossary.json` with `locked` entries; `verify.py` fails any segment where a locked source term is not rendered with its locked Chinese form — 40 locked occurrences in the demo, 100% compliant |
| **段落全** no missing paragraphs | segments carry the PDF's own ids (`p1b4`); the gate compares id sets both ways and flags missing, duplicated or invented ids |
| **关系准** relations intact | per-segment comparison of numeric values, citation markers, formula tokens, negation and hedging markers |
| **可核验** traceable | every target paragraph keeps page, block and bbox; the QA report names the failing id, check and detail |

The workflow: `prepare.py` (segment + glossary + batches) → the agent translates
one batch per turn → `verify.py` (hard gate, exit 1 on any failure) → `run_case.py`
(writes `result.json` with the bilingual pairs, the glossary, the QA report and
the evidence).

## Measured result (page 1 of BERT, EN→ZH)

| Metric | Value |
|---|---|
| Segments / source characters | 10 / 4,282 |
| Translation coverage | **1.00** (10/10, order preserved) |
| Glossary | 26 terms, **21 locked**, 40 locked-term occurrences, **100% compliant** |
| Numbers, citations, formula tokens | 10/10 segments pass each check |
| Negation / hedging markers | 10/10 pass |
| Hard failures after the gate | **0** |
| Gate sensitivity (injected defects) | **7/7 detected** (term drift, lost number, lost citation, lost negation, lost hedge, untranslated segment, placeholder) |
| First draft | 2 terminology defects caught before submission (`语言推断` → locked `推理`; missing `编码器` in the acronym expansion) |
| Runtime | 19 s local, no network, no GPU |

The gate is the point: the first draft *read* fine and still had two term
violations that the lock caught. That is the difference between "the glossary is
in the prompt" and "the glossary is in the output".

## Bundle map

| Path | What it is |
|---|---|
| `submission/SKILL.md` | the skill definition installed under `/skills` |
| `submission/scripts/prepare.py` | segmentation, glossary extraction, batch packing |
| `submission/scripts/verify.py` | the mechanical fidelity gate (+ `--selftest`) |
| `submission/scripts/run_case.py` | case-contract adapter → `result.json` |
| `submission/glossary/seed-ml-zh.csv` | 59-term bilingual seed glossary (all with a locked Chinese form) |
| `submission/references/` | workflow, glossary format, QA rules, worked example |
| `src/reproduce.py` | the run that produced everything below |
| `execution/run.log` | append-only log (also mirrored at `run.log`) |
| `execution/results/` | segments, glossary, translations, bilingual.md, QA report, metrics, case result (also mirrored at `results/`) |
| `trace/trace.jsonl` | typed steps with paired tool calls and artifact paths |
| `characterization.json` | what was measured against the source |
| `bundle_validation.json` | local validation report |

## Honest limits

- Translation quality is the model's; the skill guarantees structure and fidelity
  checks, not literary quality.
- The demo covers page 1 of one paper. Cross-page continuation, tables and figure
  captions are supported by the parser but are not exercised in this run.
- The gate's negation/hedge checks are marker-based: they prove a marker survived,
  not that its scope is identical. Scope doubts go to the review queue.
- Formulas are compared as glyph strings; mathematical equivalence is not checked.
- No OCR: a scanned page is reported unreadable rather than guessed.

## GitHub link

No public repository exists for this run, so `GITHUB_URL.txt` is not included and
the 5-point ecosystem bonus is forfeited rather than filled with a placeholder.

## Licence and reuse

The skill and scripts are released for reuse within this submission. The demo PDF
is an arXiv preprint (arXiv non-exclusive licence) and is not redistributed in the
bundle; `manifest.data_sources` records its URI, size and SHA-256.
