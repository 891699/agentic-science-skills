---
name: intro-drafter
description: "Draft a paper's introduction and related work with a sentence-level evidence map: every sentence cites a fact from the paper, a reference key, or declares itself as judgement. Groups related work by research route, derives the gap from at least two cited works, and checks that each contribution maps to the paper's own results. Trigger on: write the introduction, 引言写作, related work, 相关工作, research gap, 研究空白, contributions, 贡献表述, 'draft the intro', 'organise the related work', 'what does this paper add', 'check my claims against the citations'."
---

# Intro Drafter

## Requirements

- Python 3.10 or newer.
- PyMuPDF for PDF access: `pip install pymupdf==2.0` (the Docker image pins the same version).
- No other dependencies; the run needs no network access.


The failure mode this skill exists for is a fluent introduction whose every
sentence is unsourced: "recent years have seen growing interest" (whose?),
"existing methods fail to" (which ones?), "we achieve state-of-the-art" (where?).
Here the prose and its evidence are produced together and verified together.

## What it guarantees

| Requirement | Mechanism |
|---|---|
| **立得住** background with substance | background sentences cite facts extracted from the paper, not generic importance claims |
| **分得清** grouped, not listed | related work is written as routes: each group has a thesis, ≥2 member works and a differentiation sentence naming how this paper differs |
| **说得实** gap from the cited work | the gap paragraph must cite ≥2 works, contain a contrast, and rest on a fact from the paper |
| **对得上** contributions match the paper | each contribution maps to a fact containing a result token or a number, and names the part of the paper it comes from |
| **可核验** nothing floats | every sentence has an evidence entry; the prose and the map are assembled from the same markdown, so they cannot drift |

Hard guards on top: no citation outside the reference list, no number that is not
in the cited fact, `first`/`novel`/`state-of-the-art` only when the paper says so,
no self-citation, and at most 40% of sentences may be pure judgement (with a note).

## Run it

Paths are relative to **this skill's own directory**. `cd` there first or use
absolute paths.

```bash
# 1. fact base: quotable sentences, citation keys, outline
python scripts/prepare.py PAPER.pdf --out WORK --max-facts 260

# 2. write WORK/intro.md and WORK/related.md, plus WORK/mapping.json
#    (positional: one entry per sentence, in order)

# 3. zip prose and evidence, then verify
python scripts/assemble.py --work WORK
python scripts/verify_draft.py --work WORK
python scripts/verify_draft.py --work WORK --selftest

# 4. apply the case contract
python scripts/run_case.py --case /input/case.json --task /input/task.md \
    --pdf PAPER.pdf --work WORK --out /app/output
```

`assemble.py` refuses to proceed when the draft and the mapping disagree on
sentence count: that is the mechanism that keeps the prose and the evidence map
the same document.

## The draft contract

`intro.md` — five paragraphs: background, problem, gap, approach, contributions.

`related.md` — one paragraph per route, three sentences each:

1. what the route does, with its member works;
2. what it costs or assumes (a judgement, with a note, if the paper only implies it);
3. how this paper differs, backed by a fact from the paper.

`mapping.json` — positional entries:

```json
{"intro_md": [
   {"bucket": "intro", "role": "background",
    "evidence": [{"type": "source", "ref": "p1b7:s0"},
                 {"type": "citation", "ref": "dai2015"}]},
   {"bucket": "contributions",
    "maps_to": "main results: eleven tasks, GLUE 80.5, MultiNLI 86.7",
    "evidence": [{"type": "source", "ref": "p1b5:s1"}]}
 ],
 "related_md": [
   {"bucket": "related", "group": "Fine-tuning", "role": "group-thesis",
    "evidence": [{"type": "source", "ref": "p1b8:s2"},
                 {"type": "citation", "ref": "radford2018"}]}
 ],
 "groups": [{"name": "Fine-tuning", "members": ["radford2018", "howard2018"],
             "thesis": "R4", "differentiation": "R6"}],
 "paper_authors": ["Devlin"]}
```

`source` refs are fact ids (`p<page>b<block>:s<index>`), `citation` refs are keys
from `works.json`, `judgement` refs carry a note explaining the inference.

## What the verifier checks

| Check | Hard? | Fails when |
|---|---|---|
| `structure` | yes | a required part (background/problem/gap/approach) is missing, fewer than three contributions, fewer than three routes |
| `text_sync` | yes | a mapped sentence is not in the markdown, or a markdown sentence has no mapping |
| `evidence_present` | yes | a sentence has no evidence at all |
| `source_evidence` | yes | a fact id does not resolve, or the fact is not verbatim in the paper |
| `citation_evidence` | yes | a citation claimed as evidence is not cited in that sentence, or the key is unknown |
| `citation_resolution` | yes | an in-text marker does not resolve to a reference key |
| `citation_coverage` | yes | fewer than 8 distinct works, or a group cites fewer than two of its members |
| `gap_derivation` | yes | the gap cites fewer than two works, states no contrast, or rests on no fact |
| `contributions` | yes | a contribution has no fact, no `maps_to`, or its fact states no result |
| `hype_guard` | yes | `first`/`novel`/`state-of-the-art` without a fact that says it |
| `numbers_grounded` | yes | a number in a sentence is absent from the facts it cites |
| `self_citation` | yes | the draft cites the paper it is written for |
| `judgement_ratio` | yes | more than 40% of sentences are judgement, or a judgement has no note |

`--selftest` injects eleven defects — an unbacked sentence, prose/map drift, an
unknown citation, a dangling fact id, an invented number, unsupported hype, a
single-work gap, a contribution without a fact, a one-member group, a self-citation
and a bare judgement — and requires each to be caught.

## Handling failures

| Situation | Action |
|---|---|
| the paper does not state the gap | say so: the gap paragraph cites the two lines and the paper's own limitation fact; do not invent a shortcoming |
| a cited work's entry is malformed in the PDF | cite the key that the normaliser produced and note the field damage in the mapping |
| the reviewer disagrees with a grouping | the group thesis is one sentence; move the member and re-run — coverage recomputes |
| a contribution has no result fact | it is not a contribution yet: either find the fact or drop the bullet |
| draft and mapping disagree | re-run `assemble.py`; it tells you which file has the extra sentence |
| scanned PDF | the parser reports unreadable pages; draft nothing from them |

## Limits to state in an answer

- The prose is the model's; the skill guarantees the evidence binding, the
  coverage and the guards, not literary quality.
- Grouping is a judgement about routes: the mechanism checks that a group is
  populated and differentiated, not that the taxonomy is the best one.
- Judgement sentences are allowed and counted; the ratio cap and the mandatory note
  keep them visible rather than hidden.
- Facts are sentences of the paper; a claim that spans two sentences needs two
  fact ids, and the verifier will accept either, so cite both.

## When to use

Use it when an introduction and related work must be auditable: every sentence is bound to a
fact, a citation or an explicit judgement, and the gap has to come from cited work.

- **Input**: one PDF; the draft and its positional evidence map are authored together.
- **Output**: `intro.md`, `related.md`, `claims.json`, an evidence map and a QA report.
- **Do not use** it for marketing prose; a sentence with no basis fails the build.

## Minimal example

Input: a 16-page paper at `input/paper.pdf`.

```bash
python scripts/prepare.py input/paper.pdf --out work --max-facts 260
python scripts/assemble.py --work work
python scripts/verify_draft.py --work work
```

示意输出（示例，非正式答案）:

```json
{"status": "success", "units": 24, "groups": 3, "cited_works": 13,
 "judgement_units": 2, "hard_failures": 0}
```

Illustrative only.

See `references/` for the evidence contract, the grouping and gap rules, and the QA
rules.
