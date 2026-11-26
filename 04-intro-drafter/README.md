# Intro drafter

Submission for **写作08｜引言与相关工作写作** (`product-arena-04-4b82ad21`).

The deliverable is a skill, not a fixed draft. `submission/SKILL.md` is what the
platform installs; the scripts are the only programs it needs; `src/reproduce.py`
is the run that produced the evidence in `execution/`.

## What the skill does

The paper is turned into a fact base (quotable sentences with anchors) and a
citation-keyed bibliography. The agent writes the introduction and related work as
markdown, and writes a **positional evidence mapping** next to it. `assemble.py`
zips the two by sentence, refusing to continue if they disagree; `verify_draft.py`
then re-checks structure, evidence, citations, the gap, the contributions, hype,
numbers and self-citation.

| Requirement | Mechanism |
|---|---|
| **立得住** | background and problem sentences cite facts from the paper, not general importance claims |
| **分得清** | three routes minimum; each group has a thesis citing ≥2 works, a limitation, and a differentiation backed by a fact |
| **说得实** | the gap cites ≥2 works, states a contrast and rests on the paper's own limitation claim |
| **对得上** | each contribution maps to a fact containing a result token or a number, plus the `maps_to` label |
| **可核验** | every sentence carries source/citation/judgement evidence; prose and map come from one assembly step |

## Measured result (BERT, 16 pages)

| Metric | Value |
|---|---|
| Fact base | 260 sentences with page/block anchors |
| Bibliography | 54 entries after fragment merging, keys `surname+year` with `a`/`b` |
| Draft units | **24** sentences (12 introduction, 9 related work, 3 contributions) |
| Related-work groups | **3** routes, each with 2–3 cited members |
| Distinct works cited | **13** of 54 |
| Judgement sentences | 2 of 24 (8%), both with a note |
| Hard verification failures | **0** across all 13 checks |
| Baseline (same prose, evidence map removed) | **29** failures |
| Gate sensitivity (injected defects) | **11/11** detected |
| Runtime | 18 s local, no network, no GPU |

The baseline row is the honest comparison: the *same* prose scores 29 hard failures
the moment its evidence map is removed. What the skill adds is not better sentences
— it is the ability to tell whether a sentence is allowed to stand.

## What the evidence looks like

`evidence_map.md` is one row per sentence:

| id | part | role | sentence | evidence |
|---|---|---|---|---|
| I1 | intro | background | Pre-training a language model on unlabeled text … (Dai and Le, 2015; …) | source `p1b7:s0` p.1 (`p1b7`); cite `dai2015`; cite `peters2018a`; … |
| R6 | related | differentiation | BERT keeps the fine-tuning recipe but replaces the constrained attention … | source `p3b52:s1` p.3 (`p3b52`) |
| C2 | contributions | — | The resulting model obtains new state-of-the-art results on eleven tasks … | source `p1b5:s1` p.1 (`p1b5`) |

`coverage.json` records, per route, exactly which works are cited, and how much of
the bibliography the draft uses.

## Bundle map

| Path | What it is |
|---|---|
| `submission/SKILL.md` | skill definition installed under `/skills` |
| `submission/scripts/prepare.py` | fact base, citation keys, outline |
| `submission/scripts/refs.py` | reference fragment merge and key assignment |
| `submission/scripts/assemble.py` | markdown ⇄ mapping zip; refuses on drift |
| `submission/scripts/verify_draft.py` | the 13 checks (+ `--selftest`) |
| `submission/scripts/run_case.py` | case-contract adapter → `result.json`, `evidence_map.md`, `coverage.json` |
| `submission/references/` | evidence contract, grouping/gap/contributions, QA rules |
| `src/reproduce.py` | the run that produced everything below |
| `execution/run.log` | append-only log (mirrored at `run.log`) |
| `execution/results/` | facts, works, claims, QA, baseline, metrics, case result, `evidence_map.md` (mirrored at `results/`) |
| `trace/trace.jsonl` | typed steps with paired tool calls and artifact paths |
| `characterization.json` | what was measured |
| `bundle_validation.json` | local validation report |

## Honest limits

- The prose is the model's; the skill guarantees the evidence binding, the coverage
  and the guards, not literary quality.
- Grouping into routes is a judgement: the mechanism checks that a group is
  populated and differentiated, not that the taxonomy is the best available.
- Judgement sentences are allowed and capped, not eliminated; they are listed in
  the QA report for review.
- The fact base is the paper's own sentences: a claim spanning two sentences needs
  two fact ids.
- No OCR: scanned pages are reported unreadable rather than drafted from.

## GitHub link

No public repository exists for this run, so `GITHUB_URL.txt` is not included and
the 5-point ecosystem bonus is forfeited rather than filled with a placeholder.

## Licence and reuse

The skill, templates and scripts are released for reuse within this submission. The
demo PDF is an arXiv preprint (arXiv non-exclusive licence) and is not
redistributed; `manifest.data_sources` records its URI, size and SHA-256.
