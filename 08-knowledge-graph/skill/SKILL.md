---
name: paper-kg
description: "Build an evidence-bound knowledge graph from a paper: typed entities and directed relations where every node and edge cites the sentence that supports it, aliases are merged with a recorded reason, and the graph answers real queries and exports to JSON, GraphML and Cypher. Trigger on: knowledge graph, 知识图谱, entity relation extraction, 实体关系抽取, entity alignment, 别名归一, graph export, GraphML, Cypher, 'build a graph from this paper', 'link the entities', 'answer questions over the paper'."
---

# Paper KG

## Requirements

- Python 3.10 or newer.
- PyMuPDF for PDF access: `pip install pymupdf==2.0` (the Docker image pins the same version).
- No other dependencies; the run needs no network access.


A graph without provenance is a diagram. This skill builds a graph in which every
node and every edge carries the sentence it came from, aliases are merged on a
recorded basis, and the result answers queries and exports to tools other people
use.

## What it guarantees

| Topic requirement | Mechanism |
|---|---|
| **抽得准** real entities | nodes may only be built from candidates extracted from the PDF; each node stores the sentence that names it |
| **连得对** correct relations | eleven directed relation types with declared source/target types; a relation that points the wrong way is a hard failure |
| **对得齐** alias handling | the builder normalises labels, merges duplicates and records `{merged, into, reason}`; an unrecorded shared label fails |
| **查得到、回得去** queryable and traceable | four queries run over the graph; every returned row carries its evidence anchor; the GraphML export is parsed and compared with the JSON |

## Run it

Paths are relative to **this skill's own directory**. `cd` there first or use
absolute paths.

```bash
# 1. candidates, outline and source metadata
python scripts/prepare.py PAPER.pdf --out WORK --max-sentences 8

# 2. author WORK/graph-source.json (contract below)

# 3. build: canonical ids, alias merges, JSON + GraphML + Cypher
python scripts/build_graph.py --work WORK
python scripts/validate_graph.py --work WORK
python scripts/validate_graph.py --work WORK --selftest   # proves the checks fire

# 4. apply the case contract
python scripts/run_case.py --case /input/case.json --task /input/task.md \
    --pdf PAPER.pdf --work WORK --out /app/output
```

Without `graph-source.json` the case step stops with `blocked_on_graph_source` —
it never invents entities or edges.

## Graph source contract

```json
{"nodes": [
   {"key": "bert", "type": "Method", "label": "BERT",
    "aliases": ["Bidirectional Encoder Representations from Transformers"],
    "quote_id": "p1b4:s0", "confidence": "high",
    "attributes": {"year": 2019}}
 ],
 "edges": [
   {"source": "bert", "target": "gpt", "type": "improves-on",
    "quote_id": "p3b52:s1", "confidence": "high",
    "condition": "bidirectional self-attention instead of left-context-only"}
 ]}
```

Rules:

1. **Types come from `schema/vocab.json`**: `Paper`, `Method`, `Task`, `Metric`,
   `Dataset`, `Condition`, `Limitation`, `Finding`; edges `uses`, `evaluated-on`,
   `reports`, `compared-with`, `improves-on`, `requires`, `limited-by`,
   `trained-on`, `supports`, `causes`, `from-paper`.
2. **Quote ids, not quotes.** Every node and edge cites a candidate id; the builder
   copies the sentence, so evidence cannot drift from the paper.
3. **Direction is meaning.** `evaluated-on` goes method → task; `limited-by` goes
   the limited thing → the limitation; `supports` goes finding → method. The
   validator checks the declared source/target types.
4. **Aliases are a claim.** Put every other spelling in `aliases`; the builder
   merges duplicates and records why. Two nodes sharing a normalised label without
   a merge record fail.
5. **Conditions stay on edges**, not in labels: "improves on GPT *because it is
   bidirectional*" keeps that in `condition`.
6. **Confidence** is `high`/`medium`/`low`; `medium`/`low` relations are surfaced
   by the uncertainty query instead of being hidden.

The builder adds one `from-paper` edge per typed node, so provenance is uniform
and connectivity is checkable.

## What the validator checks

| Check | Hard? | Fails when |
|---|---|---|
| `node_schema` | yes | unknown node type, missing required field |
| `edge_schema` | yes | unknown edge type, missing endpoint, source/target type not allowed |
| `edge_evidence` | yes | node or edge without evidence, a quote not verbatim in the paper, a malformed anchor, a bad confidence |
| `self_loops` | yes | an edge points at its own source |
| `alias_integrity` | yes | two nodes share a label without a recorded merge, or a merge has no reason |
| `connectivity` | yes | a node has no `from-paper` edge |
| `queries` | yes | fewer than three queries return rows, or a row lacks its anchor |
| `graphml_wellformed` | yes | the GraphML does not parse, or its node/edge counts disagree with the JSON |

`--selftest` injects seven defects (dangling edge, wrong direction, missing
evidence, duplicate label, orphan node, broken GraphML, no query rows) and
requires each to be caught.

## Query set
The shipped queries (`queries.cypher`, mirrored in the validator) answer:

1. what does a method use, and where is that stated;
2. which tasks is it evaluated on, and what does it report;
3. which conditions and limitations constrain it;
4. what is it compared with, and in which direction;
5. which relations are uncertain, and which findings are unattached.

## Handling failures

| Situation | Action |
|---|---|
| an entity appears only in a figure label | leave it out; figure text is not prose evidence |
| the paper does not name a relation direction | use `compared-with` and say so in `condition` |
| two entities share a name but differ | give them distinct labels and put the disambiguation in `attributes` |
| a claim is only implied | mark the edge `medium` or `low`; the uncertainty query surfaces it |
| scanned PDF | the parser reports unreadable pages; build nothing from them and return `partial` |
| a query returns nothing | that is a finding, not an error — report it rather than adding edges to fill it |

## Limits to state in an answer

- Entities and relations are the model's reading; the skill guarantees the quotes,
  the anchors and the schema, not the interpretation.
- The vocabulary is small on purpose; domain types can be added in
  `schema/vocab.json` without code changes.
- The graph is per paper; cross-paper alignment is the next step, not this run.
- Alias merging is label-based plus what the author declares; it cannot resolve a
  genuine homonym without a disambiguating attribute.

## When to use

Use it when the paper's entities and relations must be queryable: every node and edge carries
the sentence it came from, and aliases are merged on evidence rather than on similarity.

- **Input**: one PDF.
- **Output**: `graph.json`, `graph.graphml`, `queries.cypher` and a validation report.
- **Do not use** it to infer relations the paper never states; an ungrounded edge fails.

## Minimal example

Input: a 5-page paper at `input/paper.pdf`.

```bash
python scripts/prepare.py input/paper.pdf --out work --max-sentences 8
python scripts/build_graph.py --work work
python scripts/validate_graph.py --work work
```

示意输出（示例，非正式答案）:

```json
{"nodes": 24, "edges": 19, "dangling_edges": 0, "schema_ok": true,
 "aliases_merged": 2, "status": "success"}
```

Illustrative only.

See `references/` for the workflow, the schema and the QA rules.
