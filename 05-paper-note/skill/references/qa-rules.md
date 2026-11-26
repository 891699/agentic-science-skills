# QA rules

The note is judged on whether it can be audited, so each rule closes a specific
way a summary can look right and be wrong.

## `quote_resolution` — every claim has a source sentence
A claim without a `quote_id`, or with an id that is not in `candidates.json`, fails.
This is the rule that makes "找得回" structural rather than aspirational: there is
no syntax for an unsourced claim.

## `quote_verbatim` — the quote is really in the paper
The candidate text must appear verbatim in the parsed document. It normally does by
construction, so a failure here means the parse or the candidate list changed under
the note — exactly the drift a re-run should catch.

## `number_grounding` — no number that its quote lacks
Every numeric token in a claim must appear in that claim's quote. Two consequences:

- writing `11` where the paper writes "eleven" fails — write 十一;
- a number from Table 2 may not be asserted unless a quoted sentence carries it.

This is the anti-fabrication rule. It is deliberately strict: it prefers a claim
with fewer numbers over a claim with an unverifiable one.

## `section_coverage` — the whole paper is visible
Every section in `segments.json` must appear in the note, either with claims or
with a role line of at least six characters. The note therefore shows what the
paper contains even where the reader chose not to annotate.

## `anchor_resolution` — the anchor is real
The quote's section must exist in the parsed outline and its anchor must match
`p<page>b<block>`. A note that cites a page but not a block is not resolvable.

## `card_completeness` — the fields that carry judgement
`research_question`, `data`, `method`, `reuse` are required; `findings` needs at
least two, `limitations` and `conditions` at least one each. A card without
`conditions` is the common failure: findings that are true only under a budget or
an assumption get summarised as unconditional.

## `claim_uniqueness` — no restatement padding
Duplicate claim text fails. If the same point belongs to two sections, keep it in
the section that argues it and give the other a role line.

## Passing shape
`status: success` requires zero hard failures **and** at least 8 claims **and** at
least 5 sections carrying claims. A note cannot pass by being empty or by having a
perfect card and no body.

## Review queue
Claims with four or more numbers are listed in `review_queue` for a human pass:
they are the ones most likely to be mis-transcribed even when every number is
technically grounded.
