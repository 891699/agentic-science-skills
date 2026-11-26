# Workflow

## 1. Prepare
```bash
python scripts/prepare.py paper.pdf --out work --max-sentences 8
```
| File | Meaning |
|---|---|
| `work/candidates.json` | quotable sentences with `id` (`p4b7:s1`), `anchor`, `page`, `block`, `section` |
| `work/segments.json` | the paper outline, so nodes can be grouped by section |
| `work/paper.json` | title, authors, year, arXiv/DOI, SHA-256 — becomes the `Paper` node |

## 2. Author the graph source
Write `work/graph-source.json` with `nodes` and `edges`. Read the paper, then for
each object decide: is it named in a sentence (take that candidate id), or am I
remembering it from elsewhere (leave it out).

The most useful discipline: write the edge list first, as sentences — "BERT uses
MLM", "BERT is evaluated on GLUE", "removing NSP lowers QNLI" — then turn each into
a node pair. Edges you cannot write as a sentence are edges you do not have
evidence for.

## 3. Build
```bash
python scripts/build_graph.py --work work
```
- ids become `kg:<type>:<slug>`; keys are local and stable across rebuilds;
- aliases and normalised labels are merged, with `{merged, into, reason}` recorded;
- one `from-paper` edge is added per typed node;
- outputs `graph.json`, `graph.graphml`, `queries.cypher`, `build_report.json`.

## 4. Validate
```bash
python scripts/validate_graph.py --work work            # exit 1 while anything hard fails
python scripts/validate_graph.py --work work --selftest # proves the checks fire
```
Read the failures array: each entry says the check, the item id and the detail.
Fix the node/edge, rebuild, re-validate.

## 5. Produce the case result
```bash
python scripts/run_case.py --case case.json --task task.md --pdf paper.pdf \
    --work work --out output
```
Outputs: `output/result.json`, plus `graph.json`, `graph.graphml`, `queries.cypher`
copied next to it.

## 6. Query and reuse
```bash
# Neo4j / Memgraph: load graph.graphml, then run queries.cypher
# Python:
import json; g = json.load(open("output/graph.json"))
# answers are already in result.json → results.queries
```
The four queries in `queries.cypher` mirror the ones the validator runs, so a
reviewer can reproduce a query result without trusting the report.
