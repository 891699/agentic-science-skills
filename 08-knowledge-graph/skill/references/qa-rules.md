# QA rules

## `node_schema` — only declared entity types
A node whose type is not in `schema/vocab.json` fails, and so does a node missing a
required field. This is what stops the graph from inventing a type per paper.

## `edge_schema` — direction is part of the claim
The check enforces the declared source and target types for each relation. A
`Task → Method` `evaluated-on` edge is rejected, because a downstream query walks
the direction and would silently return nothing.

Direction mistakes are the most common graph defect and the hardest to notice by
reading. The schema catches them mechanically.

## `edge_evidence` — every node and edge cites the paper
Each node and edge must carry evidence whose quote occurs verbatim in the parsed
text, with a well-formed anchor, and a confidence in `{high, medium, low}`.

The verbatim requirement is what separates a graph from a summary: a node label can
be a normalisation, but its evidence sentence cannot.

## `self_loops`
An edge whose source equals its target is rejected. Self-relations usually mean two
objects were collapsed into one node, which `alias_integrity` will also flag.

## `alias_integrity` — merge on the record
Two nodes may not share a normalised label (label or alias) unless the builder
produced a merge record, and every merge record must carry a reason.

This is the "既不重复也不错误合并" rule made checkable: merging is allowed and even
encouraged, but it has to be visible and justified, so a reviewer can disagree with
a specific merge instead of distrusting the whole graph.

## `connectivity` — nothing floats
Every typed node must have a `from-paper` edge, which the builder adds
automatically. A node without one is either an authoring mistake or an object the
paper does not actually contain.

## `queries` — the graph answers something
At least three queries must return rows, and every row must carry an evidence
anchor. The shipped set asks: what does a method use; which tasks and scores;
which constraints; what is compared and in which direction.

A query that returns nothing is a *legitimate result* and is reported as such by
the case result — it is not a reason to add edges.

## `graphml_wellformed`
The GraphML export must parse as XML and contain the same number of nodes and edges
as the JSON. An export that silently drops half the graph is worse than no export,
because a reader trusts the file.

## Self test
`--selftest` injects: a dangling edge, a wrong-direction edge, missing evidence, a
duplicate label, an orphan node, a broken GraphML document and a rename that makes
the queries return nothing. All seven must be detected while the clean graph
passes.
