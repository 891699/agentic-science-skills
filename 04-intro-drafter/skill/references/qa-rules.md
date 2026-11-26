# QA rules

## `text_sync` — the prose and the map are one document
Two directions, both hard:

- every mapped sentence must occur in the markdown file of its bucket;
- every sentence of the markdown must be covered by some mapping entry.

The second direction is the one that matters: it is trivial to keep a map in sync
by only checking the first. A sentence added to the draft after assembly has no
mapping and fails here.

## `evidence_present` / `source_evidence`
A sentence with no evidence fails. A `source` ref must resolve to a fact and that
fact's text must occur verbatim in the parsed paper, so the pointer is checkable by
anyone with the PDF.

## `citation_evidence` / `citation_resolution`
A `citation` ref must resolve to a reference key *and* be cited in the sentence it
claims to support. Resolution re-derives the key from the in-text marker
(`Peters et al., 2018a` → `peters2018a`, `Dai and Le, 2015` → `dai2015`,
`Tjong Kim Sang and De Meulder, 2003` → `sang2003` by surname tail), so a marker
that names a work not in the bibliography fails instead of passing silently.

## `citation_coverage`
At least eight distinct works across the draft, and every group must cite all of its
own members. The eight-work floor stops a draft that cites two papers and calls it
related work; the per-group rule stops a group whose membership is decoration.

## `gap_derivation`
Three requirements on the gap paragraph: ≥2 works, a contrast, a fact. A gap that
fails any of them is either an unsupported claim or a restatement of the problem.

## `contributions`
Each bullet needs a fact, a `maps_to` label, and a fact that states a result. This
is what connects the introduction to the body: a contribution that maps to nothing
is a promise the paper does not keep.

## `hype_guard`
`first`/`novel`/`state-of-the-art`/`best`/`unprecedented` require the same word in a
cited fact. The guard exists because these words are the ones most likely to be
added by the drafter and least likely to be checked by a reviewer.

## `numbers_grounded`
Numbers in a sentence must occur in the facts that sentence cites, after removing
citation markers. Catches a rounded score, a wrong percentage, or a number carried
over from another paper.

## `self_citation`
The draft may not cite the paper it introduces. Besides being circular, a
self-citation would let the draft "support" a claim with the claim itself.

## `judgement_ratio`
At most 40% of sentences may be pure judgement, and every judgement needs a note.
Judgement is not forbidden — a related-work paragraph usually needs one sentence no
paper states — but it must be visible and explained.

## Self test
`--selftest` injects eleven defects, one per check family: an unbacked sentence,
prose/map drift, an unknown citation, a dangling fact id, an invented number,
unsupported hype, a single-work gap, a contribution without a fact, a one-member
group, a self-citation and a bare judgement. All eleven must be detected while the
clean draft passes.
