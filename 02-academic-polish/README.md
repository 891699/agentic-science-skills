# Paper polish

Submission for **写作02｜学术语言润色** (`product-arena-02-7051d92d`).

The deliverable is a skill, not a rewritten paper. `submission/SKILL.md` is what
the platform installs; the scripts are the only programs it needs;
`src/reproduce.py` is the run that produced the evidence in `execution/`. The
platform's three fixed cases are supplied at evaluation time.

## What the skill does

The draft is split into paragraph segments carrying the facts a polish must not
break (numbers, citations, protected terms, hedges, negations). The agent writes
the polish plus a sentence-level change log; the verifier checks that the prose
changed and the science did not.

| Requirement | Mechanism |
|---|---|
| **改得对** real fixes | 15 typed edit categories; every edit records before, after, type and reason |
| **说得像** register | contractions fail; padding and passive constructions may not increase; style measured before/after |
| **没改坏** meaning kept | per-paragraph set comparison of numbers, citations, acronyms, negations and hedges |
| **讲得清** auditable | `before` must occur in the draft, `after` in the polish — the log is a diff, not a summary |

## Measured result (BERT opening, 6 paragraphs)

| Metric | Before | After |
|---|---|---|
| Words | 598 | 559 (ratio 0.93) |
| Sentences | 21 | 23 (two long sentences split) |
| Average sentence length | **28.5 words** | **24.3 words** |
| Passive patterns | 5 | 1 |
| Intensifier padding | 1 | 1 (unchanged) |
| Recorded edits | — | **30**, each with type and reason |
| Fidelity hard failures | — | **0** (numbers, citations, terms, negation, hedges, change log, length, register) |
| Gate sensitivity (injected defects) | — | **7/7** detected |

The two rejected rewrites are the interesting part: an edit that turned
`could be very harmful` into `is very harmful` was refused by the hedge check, and
a "clearer" passive rewrite was refused by the style check. Both are the exact
failures the topic names, caught before submission.

## Bundle map

| Path | What it is |
|---|---|
| `submission/SKILL.md` | skill definition installed under `/skills` |
| `submission/scripts/prepare.py` | segments + protected facts + style baseline |
| `submission/scripts/verify_polish.py` | fidelity, minimal-edit and style checks (+ `--selftest`) |
| `submission/scripts/run_case.py` | case-contract adapter → `result.json`, `polished.md`, `changes.md` |
| `submission/references/edit-taxonomy.md` | the 15 edit types and what an edit must not do |
| `submission/references/qa-rules.md` | the checks and why each exists |
| `src/reproduce.py` | the run that produced everything below |
| `execution/run.log` | append-only log (mirrored at `run.log`) |
| `execution/results/` | segments, polish, QA, style, metrics, case result, `polished.md`, `changes.md` (mirrored at `results/`) |
| `trace/trace.jsonl` | typed steps with paired tool calls and artifact paths |
| `characterization.json` | what was measured |
| `bundle_validation.json` | local validation report |

## Honest limits

- The edits are the model's judgement; the skill guarantees the numbers, citations,
  terms, hedges and the audit trail, not the literary quality.
- Style metrics are proxies (average sentence length, passive pattern, padding),
  not a journal's house style checker.
- Register is tuned per paragraph; a full journal-style adaptation is a larger task.
- Hedge checking is marker-based: it proves a modal survived, not that its scope is
  identical. Genuine scope doubts belong in `notes`.
- No OCR: a scanned draft is reported unreadable rather than polished from guesswork.

## GitHub link

No public repository exists for this run, so `GITHUB_URL.txt` is not included and
the 5-point ecosystem bonus is forfeited rather than filled with a placeholder.

## Licence and reuse

The skill, taxonomy and scripts are released for reuse within this submission. The
demo PDF is an arXiv preprint (arXiv non-exclusive licence) and is not
redistributed; `manifest.data_sources` records its URI, size and SHA-256.
