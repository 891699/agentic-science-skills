# Method writer

Submission for **写作09｜方法与实验章节写作** (`product-arena-05-64faa4a2`).

The deliverable is a skill, not a fixed section. `submission/SKILL.md` is what the
platform installs; the scripts are the only programs it needs; `src/reproduce.py` is
the run that produced the evidence in `execution/`.

## What the skill does

The paper is mined for three kinds of material — fact sentences with page/block
anchors, parameter candidates in the common shapes (`L=12`, `batch size of 256`,
`learning rate of 5e-5`), and table rows with numbers. The author then writes a
**reproduction spec**: one slot per parameter with value, unit, source sentence and
status. The section is written against that spec, sentence by sentence, and a verifier
ties the prose, the spec and the paper together.

| Requirement | Mechanism |
|---|---|
| **步骤** | step sentences carry a role and a fact anchor |
| **设置** | setting sentences must state the slots they cite |
| **参数** | every parameter is a slot with a source sentence |
| **数据** | corpus sizes and task names are slots with their own sources |
| **对照** | at least two anchored ablation sentences |
| **复现与限制** | unspecified values become `unavailable` slots with reasons, written into the limits paragraph |

## Measured result (BERT, 16 pages)

| Metric | Value |
|---|---|
| Fact base | 348 anchored sentences |
| Extracted parameter candidates | **54** across 5 families |
| Tables kept separately | 7 |
| Section sentences | **23** in five subsections |
| Spec slots | **30** (27 stated, 3 unavailable) |
| Declared gaps | **3** (random seeds, per-task GLUE learning rate, preprocessing pipeline) |
| Hard verification failures | **0** across 12 checks |
| Baseline (same prose, slot bindings removed) | **33** failures |
| Gate sensitivity (injected defects) | **10/10** detected |
| Runtime | 19 s local, no network |

The baseline row is the point: the *same paragraphs*, with the sentence-to-spec
bindings dropped, fail 33 checks — 30 unbound parameters and 3 admitted gaps that
never reach the reader. What the skill adds is not nicer sentences; it is the
guarantee that each number in them has a home in the paper.

## What the evidence looks like

`checklist.md` — one row per slot:

| id | family | parameter | value | status | source |
|---|---|---|---|---|---|
| S04 | objective | masked language model rate | 15% | stated | `p4b7:s3` |
| S14 | optimization | pre-training learning rate | 1e-4 | stated | `p13b37:s1` |
| S28 | repro | random seeds | — | unavailable | — |

`gaps.md` — the open questions for the author, one per unavailable slot.

## Bundle map

| Path | What it is |
|---|---|
| `submission/SKILL.md` | skill definition installed under `/skills` |
| `submission/scripts/prepare.py` | facts, parameter candidates, tables |
| `submission/scripts/refs.py` | reference merge and keys |
| `submission/scripts/verify_method.py` | the 12 checks (+ `--selftest`) |
| `submission/scripts/run_case.py` | case adapter → `result.json`, `checklist.md`, `gaps.md` |
| `submission/references/spec-contract.md` | slot schema, why values are strings, gaps as slots |
| `submission/references/qa-rules.md` | the checks and what each one catches |
| `src/reproduce.py` | the run that produced everything below |
| `execution/run.log` | append-only log (mirrored at `run.log`) |
| `execution/results/` | facts, params, tables, spec, QA, baseline, metrics, case output (mirrored at `results/`) |
| `trace/trace.jsonl` | typed steps with paired tool calls and artifact paths |
| `characterization.json` | what was measured |
| `bundle_validation.json` | local validation report |

## Honest limits

- The prose is the model's; the skill guarantees parameter fidelity and provenance,
  not literary quality.
- Parameter extraction is pattern-based. Unusual phrasing is missed, and a miss shows
  up as an `unavailable` slot with a reason rather than a wrong value.
- Values are matched as strings against the source sentence, so they must be written
  the way the paper writes them (`1e-4`, not `0.0001`).
- Numbers that appear only in a figure cannot be verified and are excluded; table
  numbers need `tables.json`.
- Three gaps in the demo paper are declared, not filled. That is the intended
  behaviour, not an omission.

## GitHub link

`GITHUB_URL.txt` points at `https://github.com/891699/agentic-science-skills`, folder
`09-method-writer`.

## Licence and reuse

The skill, spec template, checklist template and gap list are released for reuse
within this submission. The demo PDF is an arXiv preprint (arXiv non-exclusive
licence) and is not redistributed; `manifest.data_sources` records its URI, size and
SHA-256.
