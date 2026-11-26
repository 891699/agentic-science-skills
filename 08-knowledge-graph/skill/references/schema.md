# Schema

## Node types
| Type | Use for | Required |
|---|---|---|
| `Paper` | the source publication (added by the builder) | `title` |
| `Method` | a model, technique or algorithm the paper names | `label` |
| `Task` | a benchmark or evaluation task | `label` |
| `Metric` | a measured quantity or score | `label` |
| `Dataset` | training or evaluation data | `label` |
| `Condition` | a premise the claim depends on | `label` |
| `Limitation` | a bound on validity or scope | `label` |
| `Finding` | a reported result, so it can be queried as a node | `label` |

## Edge types and direction
| Type | Source → Target | Meaning |
|---|---|---|
| `uses` | Method → Method | the approach contains the component |
| `evaluated-on` | Method → Task | measured on this task |
| `reports` | Method → Metric | reports this value |
| `compared-with` | Method → Method | same conditions, no direction implied |
| `improves-on` | Method → Method | a modification that raises performance |
| `requires` | Method → Condition | holds only when the condition holds |
| `limited-by` | Method → Limitation | the limitation bounds it |
| `trained-on` | Method → Dataset | parameters learned from this data |
| `supports` | Finding → Method | the finding is evidence about the method |
| `causes` | Method/Finding → Finding | reported cause of an observed effect |
| `from-paper` | any typed node → Paper | provenance link, added by the builder |

The validator enforces these source/target types. A relation that "reads fine" but
points backwards (`Task → Method` for `evaluated-on`) is a hard failure, because a
downstream query would silently return nothing.

## Evidence
Each node and edge carries:

```json
{"anchor": "p4b7", "page": 4, "section": "Pre-training BERT",
 "quote": "We refer to this procedure as a “masked LM” (MLM) ..."}
```

`quote` must occur verbatim in the parsed paper. The anchor is the block the
sentence came from (`p<page>b<block>`), which is what makes "回得去" checkable.

## Confidence
- `high` — the sentence states it directly;
- `medium` — the sentence supports it with one inference step;
- `low` — plausible but the paper does not state it; keep it visible, and the
  uncertainty query will list it.

## Aliases and merging
`aliases` lists every other spelling. The builder normalises (case, whitespace) and
merges a new node whose label matches an existing label or alias, recording
`{"merged": "...", "into": "...", "reason": "same normalised label ..."}`.

Rules that keep merging honest:
- a merge must be recorded with a reason; an unrecorded duplicate fails;
- a homonym is **not** merged: give the two nodes distinct labels and put the
  disambiguating attribute (venue, year, dataset) in `attributes`;
- acronyms belong in `aliases` of the full form, not as separate nodes.
