# QA rules

## `structure` — the four graphs
A nanopublication is a head graph plus three named graphs. The head must link
`np:hasAssertion`, `np:hasProvenance` and `np:hasPublicationInfo`, and each linked
graph must exist. A missing provenance graph is the most common defect and the
most damaging: the claim then has no route back to the paper.

## `assertion_atomic` — one thing is claimed
Flags any assertion with a missing or repeated subject/relation/object, a relation
outside the vocabulary, a compound value, or a value over 200 characters.

The compound rule is deliberately blunt (` and `, `、`, `；`, `且`). It produces
false positives on names that contain "and" — rewrite the object rather than
weakening the rule, because a compound object is exactly what makes a
nanopublication unverifiable.

## `evidence_verbatim` — the quote is in the paper
The evidence sentence must occur verbatim in the parsed document, the anchor must
match `p<page>b<block>`, and — when the sentence is a known candidate — the anchor
must be the one that sentence came from. This catches a quote that was edited to
fit the claim, which is the failure mode visual inspection never catches.

## `provenance_chain` — the route back
The provenance graph must carry `prov:wasAttributedTo`, `prov:used`, the source
title and SHA-256, the evidence quote and anchor, and a source URI that names the
paper's arXiv id (or DOI). Without these the claim cannot be re-checked six months
later.

## `pubinfo_complete` — who, when, under what licence
`dct:creator`, `dct:created`, `dct:license`, `pav:version`. A nanopublication
without a licence or a creator is not publishable.

## `uri_integrity` — the content address
Recompute the SHA-256 over assertion + evidence + source metadata and compare it
with the URI suffix. This makes tampering visible: editing a triple without
re-emitting leaves a URI that no longer matches its content.

## `no_duplicates` — one claim, one URI
Two nanopublications with the same subject-relation-object are a duplication, even
if their evidence differs. If the same claim is supported by two sentences, keep
one and put the second in qualifiers, or split the claim so each part is distinct.

## `coverage` — a paper, not a sentence
At least 8 nanopublications and at least 5 sections represented. This stops a
submission that passes every structural check with two claims.

## Self test
`--selftest` injects: a missing provenance graph, a compound assertion, evidence
that is not in the source, a duplicate assertion, a tampered hash, a missing
creator and an unknown relation. All seven must be detected while the clean set
passes; the command exits nonzero otherwise.
