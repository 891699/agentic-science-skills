# Assertion rules

## Atomicity
An assertion is atomic when you can say whether it is true or false without
choosing which part you mean. The validator approximates this mechanically:

- exactly one `subject`, one `relation`, one `object` triple in the assertion graph;
- the relation must be in `vocab/relations.json`;
- no ` and ` / `、` / `；` / `且` inside subject or object;
- subject and object each under 200 characters.

The conjunction rule is the useful one in practice. "Removing NSP hurts QNLI, MNLI
and SQuAD 1.1" becomes three nanopublications with the same subject and relation
and one object each — that is not duplication, because each can fail on its own.

## The relation vocabulary
Ten relations cover most claim types in a paper. Direction is always subject →
object.

| Relation | Use it when | Typical object |
|---|---|---|
| `reports-score` | the paper states a measured value | "GLUE 80.5%" |
| `outperforms` | a comparison with a direction | another method |
| `uses-method` | a component of the approach | a technique |
| `trained-on` | training data | a corpus |
| `requires-condition` | the claim holds only under this | a condition |
| `has-limitation` | a bound on validity | the limitation |
| `improves-on` | a modification raises performance | the previous version |
| `compared-with` | evaluated under the same conditions, no direction | another method |
| `part-of` | a component of a workflow | the workflow |
| `causes` | reported cause of an observed effect | the effect |

If the relation you want is missing, choose the closest one and put the nuance in
`qualifiers`. Do not invent a relation: the validator will reject it, and a
free-form predicate is not queryable anyway.

## Evidence kinds
- `direct` — the quoted sentence states the assertion;
- `indirect` — the sentence supports it by inference (a table total you computed, a
  condition implied by the method description).

`indirect` assertions still need a quote; the difference is what the reader should
expect to have to check.

## Qualifiers
Qualifiers carry what must not be folded into the object: benchmark, metric,
absolute improvement, dataset size, budget, assumption. They are serialised as one
JSON literal on `vocab:qualifiers`, so they stay queryable without exploding the
triple count.

## What not to assert
- a number that only exists in a table body (use a qualifier with `indirect`);
- a claim the paper only mentions as prior work (attribute it, don't restate it);
- a causal claim the paper states as correlation;
- anything from a section the parser marked unreadable.
