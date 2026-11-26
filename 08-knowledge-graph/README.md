# Paper KG

Submission for **阅读15｜文献知识图谱构建** (`product-arena-10-760d1a0b`).

The deliverable is a skill, not a finished graph. `submission/SKILL.md` is what the
platform installs; the scripts are the only programs it needs; `src/reproduce.py`
is the run that produced the evidence in `execution/`. The platform's three fixed
cases are supplied at evaluation time.

## What the skill does

The paper is parsed into sections and quotable sentences. The agent authors typed
nodes and directed edges against those sentences; the builder canonicalises ids,
merges aliases and exports; the validator checks schema, evidence, connectivity,
exports and queries before anything is accepted.

| Topic requirement | Mechanism |
|---|---|
| **抽得准** real entities | every node cites a sentence extracted from the PDF; a node with no evidence fails |
| **连得对** correct relations | eleven directed relation types with declared source/target types; wrong direction is a hard failure |
| **对得齐** alias handling | label normalisation merges duplicates and records `{merged, into, reason}`; an unrecorded shared label fails |
| **查得到、回得去** | four queries answered, every row carries its anchor; every node and edge exports with its anchor to GraphML |

## Measured result (BERT → graph)

| Metric | Value |
|---|---|
| Nodes / edges | **22 / 41** (incl. one `from-paper` edge per typed node) |
| Node types used | 7 of 8 (`Paper` excluded from count): Method, Task, Metric, Condition, Limitation, Finding |
| Edge types used | **9 of 11** (all but 	rained-on, causes) |
| Alias merges | **1** recorded (`MLM` → `masked language model (MLM)`, same normalised label) |
| Evidence coverage | **21/22 nodes** (the Paper node carries file metadata instead), **41/41 edges**, all verbatim + anchored |
| Queries answered | **4** (uses, evaluated-on + reports, constraints, comparisons) |
| Hard validation failures | **0** (schema, direction, evidence, self-loops, aliases, connectivity, queries, GraphML) |
| Exports | `graph.json`, `graph.graphml` (XML parsed, counts match), `queries.cypher` |
| Gate sensitivity | **7/7** injected defects detected |
| First draft | 1 defect caught: the `Paper` node lacked the `title` field the schema requires |
| Runtime | 16 s local, no network, no GPU |

The first-draft catch is small but representative: the graph looked complete, and
the schema check found the root node missing the one field every other node depends
on for provenance.

## Bundle map

| Path | What it is |
|---|---|
| `submission/SKILL.md` | skill definition installed under `/skills` |
| `submission/scripts/prepare.py` | candidates, outline, source metadata |
| `submission/scripts/build_graph.py` | ids, alias merges, JSON/GraphML/Cypher export |
| `submission/scripts/validate_graph.py` | the eight checks, four queries (+ `--selftest`) |
| `submission/scripts/run_case.py` | case-contract adapter → `result.json` |
| `submission/schema/vocab.json` | node and edge vocabulary |
| `submission/references/` | workflow, schema, QA rules |
| `src/reproduce.py` | the run that produced everything below |
| `execution/run.log` | append-only log (mirrored at `run.log`) |
| `execution/results/` | candidates, authored source, `graph.json`, `graph.graphml`, `queries.cypher`, QA, metrics, case result (mirrored at `results/`) |
| `trace/trace.jsonl` | typed steps with paired tool calls and artifact paths |
| `characterization.json` | what was measured |
| `bundle_validation.json` | local validation report |

## Honest limits

- Entities and relations are the model's reading; the skill guarantees the quotes,
  anchors and schema, not the interpretation.
- The vocabulary is small on purpose; domain types can be added in
  `schema/vocab.json` without code changes.
- The graph covers one paper; cross-paper alignment is the documented next step, not
  this run.
- Alias merging is label-based plus what the author declares; a genuine homonym needs
  a disambiguating attribute and is reported rather than silently merged.
- No OCR: scanned pages are reported unreadable rather than turned into nodes.

## GitHub link

No public repository exists for this run, so `GITHUB_URL.txt` is not included and
the 5-point ecosystem bonus is forfeited rather than filled with a placeholder.

## Licence and reuse

The skill, vocabulary and scripts are released for reuse within this submission.
The demo PDF is an arXiv preprint (arXiv non-exclusive licence) and is not
redistributed; `manifest.data_sources` records its URI, size and SHA-256.
