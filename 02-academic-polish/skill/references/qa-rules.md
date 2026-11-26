# QA rules

## `numbers`
The set of numeric values must be identical before and after. Percent signs and
commas are part of the value: `7.7%` may not become `7.7`, and `3,600` may not
become `3600` in a way that changes the printed form.

A polish that "tidies" a number is the most damaging kind, because nothing in the
prose signals it.

## `citations`
Citation markers are pointers. `(Peters et al., 2018a; Radford et al., 2018)` must
come out byte-identical; a marker may move within the sentence, not change.

## `protected_terms`
Every acronym and model name present in the draft must appear in the polish. This
is what stops "BERT" becoming "the model" and then "it" across a paragraph, which
silently breaks the term-consistency requirement.

## `negation` and `hedges`
Marker counts may not drop. The check cannot tell whether scope moved, but it does
catch the common failure: `could be very harmful` becoming `is very harmful`, or
`only predict the masked words` losing its `only`.

Marker counts are counted per paragraph, not per sentence, so a rewrite that keeps
the modal in a different clause still passes.

## `change_log`
Three conditions, all hard:

- changed text with no recorded change;
- a recorded change whose `before` is not in the draft or whose `after` is not in
  the polish;
- a change without a type or with a reason shorter than ten characters.

The `before`/`after` membership test is what makes the log a diff rather than a
summary: a reviewer can see exactly which substring moved.

## `length_ratio` and `sentence_delta`
The band exists to prevent a rewrite disguised as a polish. 0.85–1.15 of the word
count and −1/+2 sentences accommodates real concision and a legitimate split while
excluding wholesale replacement.

## `contractions` and `style`
Contractions fail outright. Intensifier padding (`very`, `quite`, `obviously`) and
passive constructions may not increase: the first is a register problem, the second
is a clarity regression that a polite polish often introduces ("when applying X"
becoming "when X is applied").

Style metrics are reported before/after (average sentence words, passive patterns,
padding count) so the improvement is visible, not asserted.

## Self test
`--selftest` injects: a changed number, a dropped citation, a dropped protected
term, a lost hedge, an impossible change record, a silent rewrite and an informal
contraction. All seven must be detected while the clean polish passes.
