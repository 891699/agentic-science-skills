---
name: method-writer
description: "Write a methods and experiments section from a paper's own numbers: build a reproduction spec (every parameter with value, unit, source sentence and status), draft the section bound to that spec, and verify that the prose, the spec and the paper agree. Gaps the paper does not state are listed as open questions instead of guessed. Trigger on: methods section, 方法章节, 实验章节, experiment setup, hyperparameters, 参数表, reproducibility, 复现, 'write the methods', 'extract the training setup', 'what settings did they use', 'make this section reproducible'."
---

# Method Writer

## Requirements

- Python 3.10 or newer.
- PyMuPDF for PDF access: `pip install pymupdf==2.0` (the Docker image pins the same version).
- No other dependencies; the run needs no network access.


The failure this skill prevents is a smooth methods paragraph whose numbers came
from nowhere: a learning rate rounded from memory, a batch size that drifted, a
"large batch" standing in for 256. Here the numbers are extracted first, the section
is written against them, and a verifier ties every claim back to a sentence of the
paper.

## What it guarantees

| Requirement | Mechanism |
|---|---|
| **步骤** procedure | step sentences carry a role and a fact anchor, in section order |
| **设置** settings | every setting sentence states the spec slots it uses; the values must appear in it |
| **参数** parameters | each parameter is a spec slot with value, unit, source sentence and status |
| **数据** datasets | corpus sizes and task names are slots with their own sources |
| **对照** controls | ablation sentences must be anchored; fewer than two fails |
| **复现与限制** | slots the paper does not specify are `unavailable` with a reason and appear in the draft's limits paragraph |

Guards on top: no number in the draft that does not occur in the paper, no number in
a sentence that is absent from its cited fact, no vague quantifier where a number
exists, and no slot that the prose forgets to mention.

## Run it

Paths are relative to **this skill's own directory**. `cd` there first or use
absolute paths.

```bash
# 1. extract facts, parameter candidates and tables
python scripts/prepare.py PAPER.pdf --out WORK --max-facts 420

# 2. author WORK/spec.json, WORK/method.md and WORK/mapping.json
#    (spec: one slot per parameter; mapping: one entry per sentence, in order)

# 3. verify, then prove the checks fire
python scripts/verify_method.py --work WORK
python scripts/verify_method.py --work WORK --selftest

# 4. apply the case contract
python scripts/run_case.py --case /input/case.json --task /input/task.md \
    --work WORK --out /app/output
```

## The three files

### `spec.json` — the reproduction contract
```json
{"id": "S09", "family": "optimization", "name": "pre-training batch size",
 "value": ["256"], "unit": "sequences", "status": "stated", "source": ["p13b37:s0"]}
```
`family` is one of architecture, objective, data, optimization, compute, fine-tuning,
controls, results, repro. `status` is `stated` or `unavailable`; an unavailable slot
carries a `reason` instead of a value.

### `method.md` — the section
Headings `3.1` … `3.5`, plain paragraphs under them. Headings are not mapped; every
sentence is.

### `mapping.json` — sentence to spec
```json
{"section": "3.2 Pre-training", "role": "setting",
 "slots": ["S09", "S10"], "evidence": ["p13b37:s0"]}
```
Roles: `context`, `step`, `setting`, `parameter`, `dataset`, `control`, `result`,
`limit`.

## What the verifier checks

| Check | Hard? | Fails when |
|---|---|---|
| `structure` | yes | a section is missing, or fewer than 20 sentences |
| `text_sync` | yes | the mapping and the draft disagree on sentence count, or a sentence has no section/role |
| `spec_families` | yes | a family (architecture, objective, data, optimization, compute, controls, repro) is absent |
| `slot_sourced` | yes | a stated value is not in its source fact, or an unavailable slot has no reason |
| `slot_coverage` | yes | a slot is never mentioned in the draft, or a sentence cites an unknown slot |
| `prose_agreement` | yes | a sentence cites a slot but does not state its value |
| `numbers_grounded` | yes | a number in a sentence is absent from its cited facts |
| `no_invention` | yes | a number in the draft does not occur anywhere in the paper |
| `steps` | yes | fewer than four step sentences or six setting sentences |
| `controls` | yes | fewer than two ablation sentences, or one has no anchor |
| `limits` | yes | fewer than three declared gaps, or a gap never reaches the draft |
| `vague` | yes | "several", "large batch", "significantly" … where a number exists |

`--selftest` injects ten defects — a dropped binding, a missing source, a wrong
value, a gap without a reason, a gap never written, an invented number, a missing
control, a drifted value, a vague quantifier and a missing step — and requires each
to be caught.

## Handling failures

| Situation | Action |
|---|---|
| the paper never states a value (seeds, preprocessing) | mark the slot `unavailable`, give the reason, list it in the limits paragraph; do not guess |
| two values exist (BASE and LARGE) | two slots, or one slot with both values; the draft must state both where it claims both |
| the source sentence has the number but a different unit | the slot's unit is wrong: fix the unit, not the prose |
| a hyperparameter is chosen per task | record it as a gap if the per-task choice is not listed |
| an ablation reports "large drops" without numbers | quote the tasks, not the adjective; a number that is not in the paper cannot be used |
| the section reads well but fails `prose_agreement` | the sentence is paraphrasing a value instead of stating it; state the value |

## Limits to state in an answer

- The prose is the model's; the skill guarantees the parameter fidelity, not the
  writing quality.
- The extractor is pattern-based: it finds the common shapes (L=12, batch size of
  256, 5e-5) and misses unusual phrasing. A miss is a `unavailable` slot with a
  reason, not a silent gap.
- Values are checked as strings against the source sentence; a value stated in a
  different notation (`0.0001` vs `1e-4`) must be written the way the paper writes it.
- Table-only numbers need `tables.json`; a number that exists only in a figure is
  not verifiable and is excluded.

## When to use

Use it when a methods section must be reproducible: parameters go into a spec with their
source sentence first, the prose is written against that spec, and missing values are
declared as gaps instead of guessed.

- **Input**: one PDF.
- **Output**: `method.md`, `spec.json`, `mapping.json`, a checklist and a gap list.
- **Do not use** it to fill a value the paper does not state; that slot stays `unavailable`.

## Minimal example

Input: a 16-page paper at `input/paper.pdf`.

```bash
python scripts/prepare.py input/paper.pdf --out work --max-facts 420
python scripts/verify_method.py --work work
python scripts/verify_method.py --work work --selftest
```

示意输出（示例，非正式答案）:

```json
{"status": "success", "sentences": 23, "slots": 30, "unavailable": 3,
 "hard_failures": 0}
```

Illustrative only.

See `references/` for the spec contract and the QA rules.
