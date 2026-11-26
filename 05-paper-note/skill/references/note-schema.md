# Note schema

## Card
Fixed keys, so two papers can be compared field by field.

| Key | What it must answer | Minimum |
|---|---|---|
| `research_question` | what problem the paper sets out to solve, in one sentence | 1 claim |
| `data` | what corpus / dataset / material the claims rest on | 1 claim |
| `method` | the mechanism or procedure, not the result | 1 claim |
| `conditions` | what must hold for the findings to stand (budget, supervision, assumption, matching constraint) | ≥1 |
| `findings` | the quantitative or qualitative results, with the numbers as printed | ≥2 |
| `limitations` | what restricts the claims: cost, scope, failure mode, unstated assumption | ≥1 |
| `reuse` | how the next reader should use this note | 1 claim |

Each item is `{"claim": "...", "quote_id": "..."}`. The quote is copied from
`candidates.json` by the case step; you only supply the id.

## Sections
```json
{"section": "<exact title from segments.json>",
 "role": "one line on what this section does",
 "notes": [{"claim": "...", "quote_id": "..."}]}
```

- `section` must match `segments.json` exactly (the verifier compares strings).
- `role` is required when `notes` is empty, and must be at least six characters.
- A section may carry zero claims; it may not be omitted.

## Candidate ids
`<anchor>:s<index>` — anchor is the PDF block (`p3b12`), index is the sentence
position inside that block's joined paragraph. The same anchor may appear under
different sections if the parser merged a cross-column paragraph; the case step
records the section the candidate was filed under, so a mismatch is visible.

## What belongs in `claim`
- the finding itself, with its numbers and conditions;
- the contrast with prior work, when the paper makes it;
- an assumption the result depends on.

## What does not belong
- interpretation the quote does not support;
- numbers that exist only in a table body (quote the caption or say "table-derived");
- a second paraphrase of a claim already made in another section.
