---
name: paper-polish
description: "Polish academic English without moving the science: minimal edits, a sentence-level change log, and a mechanical check that numbers, citations, protected terms, negation and hedging survive. Trigger on: polish this paragraph, 润色, academic English editing, proofread my paper, improve the writing, 语言润色, 'make it read better', 'fix the grammar but keep the meaning', reviewer-style language revision, 中译英润色. Use it whenever the text must improve and the claims must not."
---

# Paper Polish

A polish that quietly hardens a claim is a defect, not an edit. This skill pairs
the rewrite with a change log and a verifier, so "improved" is checkable and
"unchanged meaning" is tested rather than promised.

## What it guarantees

| Requirement | Mechanism |
|---|---|
| **改得对** real fixes | edits are typed (grammar, collocation, concision, structure, punctuation, hyphenation, voice); every edit names before and after text |
| **说得像** academic register | contractions fail; intensifier padding may not increase; passive constructions may not increase; style metrics reported before/after |
| **没改坏** meaning preserved | numbers, citation markers, protected terms (acronyms, model names), negations and hedges are compared set-wise per paragraph |
| **讲得清** auditable | every change carries `before`, `after`, `type`, `reason`; before must occur in the draft and after in the polish |

Minimal-edit is enforced numerically: length ratio must stay in 0.85–1.15 and the
sentence count may move by at most −1/+2.

## Run it

Paths are relative to **this skill's own directory**. `cd` there first or use
absolute paths.

```bash
# 1. paragraphs + the facts a polish must not break + style baseline
python scripts/prepare.py PAPER.pdf --out WORK --max-paragraphs 6

# 2. author WORK/polished.jsonl (contract below)

# 3. verify, then apply the case contract
python scripts/verify_polish.py --work WORK
python scripts/verify_polish.py --work WORK --selftest   # proves the checks fire
python scripts/run_case.py --case /input/case.json --task /input/task.md \
    --pdf PAPER.pdf --work WORK --out /app/output
```

Without `polished.jsonl` the case step stops with `blocked_on_polish` — it never
rewrites the prose on its own.

## Polish contract

```json
{"id": "p1b5",
 "polished": "BERT is conceptually simple and empirically powerful. It achieves ...",
 "changes": [
   {"type": "collocation", "before": "It obtains new state-of-the-art results",
    "after": "It achieves new state-of-the-art results",
    "reason": "achieve is the usual verb for results; obtain reads as a literal translation"}
 ],
 "notes": "all numbers kept as printed"}
```

Rules:

1. **One row per paragraph, same order, same ids.** The verifier compares id sets
   both ways.
2. **Every edit is recorded.** Text changed with no recorded change fails; a
   recorded change that does not occur fails.
3. **`before` must be a substring of the draft, `after` of the polish.** This is
   what makes the log auditable rather than decorative.
4. **Numbers and units are untouchable.** `7.7%` may not become `7.7`; `point` may
   not become `%`.
5. **Citations stay byte-identical.** `(Peters et al., 2018a; Radford et al., 2018)`
   is a pointer, not prose.
6. **Hedges and negations survive.** `may`, `can`, `only`, `not`, `without` must
   still be there afterwards; the verifier counts them per paragraph.
7. **Do not fix what is not broken.** An edit that only swaps synonyms for its own
   sake costs the reviewer's trust and risks the claim.

## What the verifier checks

| Check | Hard? | Fails when |
|---|---|---|
| `coverage` | yes | a paragraph is missing, duplicated, reordered or empty |
| `numbers` | yes | the set of numeric values differs from the draft |
| `citations` | yes | a citation marker is added, dropped or altered |
| `protected_terms` | yes | an acronym or model name disappears |
| `negation` | yes | the polish has fewer negation markers than the draft |
| `hedges` | yes | the polish has fewer modal/hedge markers than the draft |
| `change_log` | yes | an unrecorded edit, a phantom change, a `before`/`after` not in the texts, a missing type or a reason under 10 characters |
| `length_ratio` | yes | the paragraph shrinks below 0.85 or grows above 1.15 |
| `sentence_delta` | yes | the sentence count moves by more than −1/+2 |
| `contractions` | yes | informal contractions appear |
| `style` | yes | intensifier padding or passive constructions increase |

`--selftest` injects seven defects (changed number, dropped citation, dropped term,
lost hedge, bad change record, silent rewrite, informal contraction) and requires
each to be caught.

## Handling failures

| Situation | Action |
|---|---|
| a sentence is so broken that fixing it changes meaning | fix the grammar, keep the meaning, and flag the ambiguity in `notes` |
| a term is spelled inconsistently across sections | normalise inside the paragraph, record the change, and list the remaining occurrences for a global pass |
| the draft mixes Chinese and English | polish the language it is written in; do not translate unless asked |
| a table or figure reference cannot be verified from the PDF | keep it as printed and note it |
| the polish would need more than +2 sentences | that is a rewrite, not a polish; do it as a separate task and say so |

## Limits to state in an answer

- The edits are the model's judgement; the skill guarantees the numbers, citations,
  terms, hedges and the audit trail, not the literary quality.
- Style metrics are proxies (average sentence length, passive pattern, padding
  words), not a journal's style checker.
- Register tuning is per paragraph; a full-journal style adaptation is a different,
  larger task.

See `references/` for the edit taxonomy and the QA rules.
