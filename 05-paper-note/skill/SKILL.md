---
name: paper-note
description: "Turn a scientific paper into a structured, quote-anchored note: a fixed paper card plus section-by-section notes where every claim carries the verbatim source sentence and its page/block. Trigger on: reading notes, 文献总结, 结构化笔记, paper card, 论文卡片, 'summarise this paper', 'take notes on this paper', 'extract the key findings', 'compare these papers', 'what are the limitations', 'make it reusable'. Use it whenever a summary must stay checkable against the paper instead of reading like a plausible abstract."
---

# Paper Note

A summary is cheap; a summary you can audit is not. This skill produces a note in
which the paper's own structure is preserved, every claim is bound to a sentence
that really exists in the PDF, and a verifier re-checks that binding before the
note is accepted.

## What it guarantees

| Topic requirement | Mechanism |
|---|---|
| **对得上** follows the paper | the note's section list is built from the parsed outline; the verifier requires a role line for every section, so the note shows the whole paper rather than a generic template |
| **留得住** keeps what makes it true | the card has fixed fields incl. **conditions** (what must hold for the findings) and **limitations**, not just findings |
| **找得回** traceable | a claim may only cite a `quote_id` from `candidates.json`; the verifier resolves it, matches it verbatim against the parsed source, and requires every number in the claim to appear in that quote |
| **用得上** reusable | one `result.json` + one `note.md`; claims, quotes, anchors and pages are machine-readable and can be diffed across papers |

## Run it

Paths are relative to **this skill's own directory** (the loader reports it as the
resource base, e.g. `/skills/weekly-skill`). `cd` there first or use absolute paths.

```bash
# 1. section skeleton + quotable candidates (each with page/block/anchor)
python scripts/prepare.py PAPER.pdf --out WORK --max-sentences 8

# 2. write WORK/notes.json against candidate ids (see the contract below)

# 3. re-check every claim against the source
python scripts/verify_notes.py --work WORK
python scripts/verify_notes.py --work WORK --selftest   # proves the checks fire

# 4. apply the case contract
python scripts/run_case.py --case /input/case.json --task /input/task.md \
    --pdf PAPER.pdf --work WORK --out /app/output
```

Without `notes.json` the case step stops with `blocked_on_notes` and reports how
many candidates exist — it never writes a summary on its own.

## Note contract

`notes.json`:

```json
{
  "paper": {"title": "...", "authors": "...", "pages": 16},
  "card": {
    "research_question": {"claim": "...", "quote_id": "p1b4:s2"},
    "data": {...}, "method": {...}, "reuse": {...},
    "conditions":  [{"claim": "...", "quote_id": "..."}],
    "findings":    [{"claim": "...", "quote_id": "..."}],
    "limitations": [{"claim": "...", "quote_id": "..."}]
  },
  "sections": [
    {"section": "Abstract", "role": "one line on what this section does",
     "notes": [{"claim": "...", "quote_id": "p1b4:s1"}]}
  ]
}
```

Rules:

1. `section` strings must match the parsed outline exactly; every section in the
   paper appears, with either claims or a `role` of at least six characters.
2. `quote_id` must be a candidate id (`<anchor>:s<index>`). The quote is copied
   from the candidate, never typed by hand.
3. Numbers in a claim must appear in that claim's quote. If the paper says
   "eleven", write 十一 in Chinese — `11` would be an unsourced number.
4. Claims are analysis and may paraphrase; quotes are evidence and may not.
5. One claim per point. Duplicate claim text is a hard failure.
6. Prefer 1–3 claims for the sections that carry the argument (abstract,
   introduction, method, main results, ablation, conclusion) and a role line for
   the rest.

## What the verifier checks

| Check | Hard? | Fails when |
|---|---|---|
| `quote_resolution` | yes | a claim has no `quote_id`, or it does not resolve to a candidate |
| `quote_verbatim` | yes | the candidate text does not appear verbatim in the parsed source |
| `number_grounding` | yes | a claim contains a number absent from its quote |
| `section_coverage` | yes | a paper section is missing, or has neither notes nor a role line |
| `anchor_resolution` | yes | the quote's section is not in the parsed outline, or the anchor is malformed |
| `card_completeness` | yes | a required card field is missing, or fewer than 2 findings / 1 limitation / 1 condition |
| `claim_uniqueness` | yes | the same claim text appears twice |

Pass also needs ≥8 claims and ≥5 sections carrying claims, so a note cannot pass
by being empty. `--selftest` injects seven defects (unknown quote, invented
number, missing section, empty role, empty card, duplicate claim, bad anchor) and
requires each to be caught.

## Handling failures

| Situation | Action |
|---|---|
| no text layer (scanned PDF) | parser reports `unreadable_pages`; note only what exists, status `partial`, name the pages |
| a section has no reliable sentence | keep the section with a `role` line and no claims — honest, and coverage still passes |
| two sections make the same point | merge the claim into the section that argues it, keep the other as a role line |
| numbers appear only in a table | quote the caption that names the table, or mark the number as table-derived instead of asserting it |
| paper has no explicit limitations | say so in `limitations` with a quote showing the closest statement, or state `not_reported` |

## Limits to state in an answer

- Claims are the model's reading; the skill guarantees the **quote and the
  numbers**, not the interpretation.
- The verifier proves a quote exists and contains the numbers; it does not prove
  the claim is the only sensible reading of that quote.
- Section boundaries come from the PDF's typography; a paper with unusual
  headings may need one manual correction in `segments.json`.
- Table-only results are not quoted unless a caption sentence carries them.

See `references/` for the workflow, the note schema and the QA rules.
