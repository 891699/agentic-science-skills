# QA rules

## `structure`
Five subsections (`3.1` … `3.5`) and at least twenty sentences. A methods section
under twenty sentences is a summary, not a description of a procedure.

## `text_sync`
The mapping has exactly one entry per sentence, in order, and every entry names a
section and a role. Role drift is how a description of a result becomes a description
of a method: if a sentence reports an outcome, it is `result`, not `step`.

## `spec_families`
Architecture, objective, data, optimization, compute, controls and repro must all
appear. Missing `repro` is the most common failure and the most damaging: it means
the section never says what cannot be reproduced.

## `slot_sourced`
For a stated slot, every value string must occur in the text of its source sentences.
For an unavailable slot, the reason must be non-empty. This is the check that stops a
value from entering the prose through the back door: a slot with no source is not a
slot, it is a guess.

## `slot_coverage`
Two directions. A slot that no sentence mentions is a parameter the section silently
omits. A sentence that cites an unknown slot id is a broken binding. Both fail.

## `prose_agreement`
If a sentence cites slot `S09`, the sentence must state `256`. This is the check that
keeps the prose and the spec the same document: the spec cannot be right while the
sentence rounds, and the sentence cannot be right while the spec drifts.

## `numbers_grounded`
Every number in a sentence must occur in one of the facts that sentence cites. A
value can be correct and still fail here if the sentence cites the wrong sentence of
the paper — which is a provenance bug worth fixing.

## `no_invention`
Every number in the draft must occur somewhere in the paper. This is the backstop for
numbers that arrive from memory, from a related paper, or from a round-off.

## `steps` and `controls`
At least four step sentences and six setting sentences; at least two ablation
sentences, each anchored. A controls paragraph with one ablation is an anecdote.

## `limits`
At least three declared gaps, and each one must appear in a `limit` sentence. The
count is a floor, not a target: a paper with only two genuine gaps should declare two
and say so, and the report makes that visible rather than failing silently.

## `vague`
`several`, `many`, `large batch`, `significantly`, `substantial` and similar phrases
fail when the sentence cites a slot: the number is available, so the adjective is not
a substitute for it. In a sentence without slots the check does not fire, because
there is nothing to state.

## Self test
`--selftest` injects ten defects, one per failure family: a dropped binding, a
missing source, a wrong value, a gap without a reason, a gap never written, an
invented number, a missing control, a drifted value, a vague quantifier and a missing
step. All ten must be detected while the clean draft passes.
