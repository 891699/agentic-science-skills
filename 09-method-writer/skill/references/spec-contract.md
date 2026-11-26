# The spec contract

The spec is the only place a number may enter the section. It has one job: make each
value checkable by someone who has the PDF open.

## A slot

```json
{"id": "S14", "family": "optimization", "name": "pre-training learning rate",
 "value": ["1e-4"], "unit": "lr", "status": "stated", "source": ["p13b37:s1"]}
```

| Field | Meaning |
|---|---|
| `id` | stable, referenced by the draft's mapping |
| `family` | architecture, objective, data, optimization, compute, fine-tuning, controls, results, repro |
| `value` | one or more strings, exactly as written in the paper (`1e-4`, not `0.0001`; `2,500M`, not `2500M`) |
| `unit` | layers, dim, heads, parameters, sequences, tokens, steps, epochs, lr, rate, days |
| `status` | `stated` or `unavailable` |
| `source` | fact ids (`p<page>b<block>:s<n>`); a list when the value spans sentences |
| `reason` | required when `status` is `unavailable` |

## Why values are strings

A slot is checked by searching its source sentence for the value as the paper writes
it. That is deliberately strict: `1e-4` and `0.0001` are the same number but only one
of them is in the paper, and a reader who greps the PDF for `0.0001` finds nothing.
Writing the value the way the source writes it makes the check mechanical.

## Why gaps are slots

A methods section is judged by what it claims and by what it admits. Three kinds of
gap appear in real papers: values that are simply not stated (seeds), values that
are stated per task but not listed (the chosen learning rate for each GLUE task), and
values that are described but not specified (the preprocessing pipeline). Each becomes
an `unavailable` slot with a reason, and the draft must say so in its limits
paragraph. A slot that is unavailable but never written into the draft fails
`limits`: the gap has to reach the reader.

## Unit consistency

The unit is not decoration. If the paper says "4 days" and the slot says `hours`, the
value string will not be found and the slot fails `slot_sourced`. Unit drift is
usually the first sign that a value was converted or remembered rather than copied.

## Families and the six elements

| Family | Element it serves |
|---|---|
| architecture, optimization | parameters |
| objective, data | procedure and datasets |
| compute, fine-tuning | experiment settings |
| controls | controls and ablations |
| repro | reproducibility and limits |
| results | claims the section makes about outcomes |

`spec_families` requires architecture, objective, data, optimization, compute,
controls and repro to be present, so a section cannot pass by describing only the
model architecture.
