#!/usr/bin/env python3
"""Build a knowledge graph from authored nodes and edges.

Takes ``graph-source.json`` (nodes and edges the agent wrote, each bound to a
candidate sentence), attaches the verbatim evidence, canonicalises ids, merges
aliases with a recorded reason, and exports the graph three ways: JSON for
programs, GraphML for graph tools, Cypher for Neo4j.

Usage:
    python build_graph.py --work WORK [--source WORK/graph-source.json]

Outputs under WORK:
    graph.json        canonical nodes/edges with evidence, merges and stats
    graph.graphml     GraphML export (XML)
    queries.cypher    the query set as Cypher, for reuse in a graph database
    build_report.json merges, skipped items and counts
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from xml.sax.saxutils import escape

TYPE_PREFIX = {
    "Paper": "paper", "Method": "method", "Task": "task", "Metric": "metric",
    "Dataset": "dataset", "Condition": "condition", "Limitation": "limitation",
    "Finding": "finding",
}


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def slug(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).lower()
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", normalized).strip("-")
    return normalized or "node"


def norm_label(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def build(source: dict, candidates: dict, paper: dict) -> tuple[dict, dict]:
    nodes: list[dict] = []
    by_key: dict[str, dict] = {}
    merges: list[dict] = []
    problems: list[dict] = []
    labels: dict[str, str] = {}

    for raw in source.get("nodes") or []:
        key = raw.get("key")
        node_type = raw.get("type")
        label = (raw.get("label") or "").strip()
        if not key or not node_type or not label:
            problems.append({"item": key or label, "problem": "node needs key, type and label"})
            continue
        aliases = [a for a in (raw.get("aliases") or []) if a]
        normalized = norm_label(label)
        existing = labels.get(normalized)
        if existing and existing != key:
            merges.append({"merged": key, "into": existing,
                           "reason": f"same normalised label {normalized!r}"})
            by_key[existing].setdefault("aliases", []).append(label)
            by_key[key] = by_key[existing]
            continue
        node = {
            "id": f"kg:{TYPE_PREFIX.get(node_type, 'node')}:{slug(label)}",
            "key": key,
            "type": node_type,
            "label": label,
            "aliases": aliases,
            "attributes": raw.get("attributes") or {},
            "quote_id": raw.get("quote_id"),
            "confidence": raw.get("confidence", "high"),
        }
        labels[normalized] = key
        for alias in aliases:
            labels.setdefault(norm_label(alias), key)
        nodes.append(node)
        by_key[key] = node

    for node in nodes:
        quote = candidates.get(node.get("quote_id"))
        if quote is None:
            problems.append({"item": node["id"], "problem": f"unknown quote {node.get('quote_id')}"})
            continue
        node["evidence"] = [{"anchor": quote["anchor"], "page": quote["page"],
                             "section": quote["section"], "quote": quote["text"]}]

    paper_node = {
        "id": "kg:paper:" + slug(paper.get("title") or "paper"),
        "key": "paper",
        "type": "Paper",
        "label": paper.get("title") or "paper",
        "title": paper.get("title") or "paper",
        "aliases": [],
        "attributes": {"authors": paper.get("authors"), "year": paper.get("year"),
                       "identifiers": paper.get("identifiers") or {},
                       "sha256": paper.get("sha256")},
        "quote_id": None,
        "confidence": "high",
        "evidence": [],
    }
    nodes.append(paper_node)
    by_key["paper"] = paper_node

    edges: list[dict] = []
    for index, raw in enumerate(source.get("edges") or [], start=1):
        source_key = raw.get("source")
        target_key = raw.get("target")
        edge_type = raw.get("type")
        src = by_key.get(source_key)
        dst = by_key.get(target_key)
        if src is None or dst is None:
            problems.append({"item": f"edge-{index}",
                             "problem": f"unknown endpoint {source_key} -> {target_key}"})
            continue
        quote = candidates.get(raw.get("quote_id"))
        if quote is None:
            problems.append({"item": f"edge-{index}",
                             "problem": f"unknown quote {raw.get('quote_id')}"})
            continue
        edges.append({
            "id": f"kg:edge:{index:03d}",
            "source": src["id"],
            "target": dst["id"],
            "type": edge_type,
            "condition": raw.get("condition") or "",
            "confidence": raw.get("confidence", "high"),
            "quote_id": raw.get("quote_id"),
            "evidence": [{"anchor": quote["anchor"], "page": quote["page"],
                          "section": quote["section"], "quote": quote["text"]}],
        })

    # every typed node gets a from-paper edge, so provenance is uniform and the
    # connectivity check has something to walk
    for node in nodes:
        if node["type"] == "Paper" or not node.get("evidence"):
            continue
        ev = node["evidence"][0]
        edges.append({
            "id": f"kg:edge:prov-{slug(node['key'])}",
            "source": node["id"],
            "target": paper_node["id"],
            "type": "from-paper",
            "condition": "",
            "confidence": node.get("confidence", "high"),
            "quote_id": node.get("quote_id"),
            "evidence": [ev],
        })

    graph = {
        "schema": "paper-kg/graph/1.0",
        "paper": paper,
        "nodes": nodes,
        "edges": edges,
        "merges": merges,
        "stats": {
            "nodes": len(nodes),
            "edges": len(edges),
            "node_types": sorted({n["type"] for n in nodes}),
            "edge_types": sorted({e["type"] for e in edges}),
            "nodes_with_evidence": sum(1 for n in nodes if n.get("evidence")),
            "edges_with_evidence": sum(1 for e in edges if e.get("evidence")),
        },
    }
    report = {"schema": "paper-kg/build-report/1.0", "merges": merges,
              "problems": problems, "nodes": len(nodes), "edges": len(edges)}
    return graph, report


def to_graphml(graph: dict) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
             '  <key id="type" for="node" attr.name="type" attr.type="string"/>',
             '  <key id="label" for="node" attr.name="label" attr.type="string"/>',
             '  <key id="anchor" for="node" attr.name="anchor" attr.type="string"/>',
             '  <key id="rel" for="edge" attr.name="type" attr.type="string"/>',
             '  <key id="eanchor" for="edge" attr.name="anchor" attr.type="string"/>',
             '  <graph id="paper-kg" edgedefault="directed">']
    for node in graph["nodes"]:
        anchor = (node.get("evidence") or [{}])[0].get("anchor", "")
        lines.append(f'    <node id="{escape(node["id"])}">')
        lines.append(f'      <data key="type">{escape(node["type"])}</data>')
        lines.append(f'      <data key="label">{escape(node["label"])}</data>')
        lines.append(f'      <data key="anchor">{escape(anchor or "")}</data>')
        lines.append("    </node>")
    for edge in graph["edges"]:
        anchor = (edge.get("evidence") or [{}])[0].get("anchor", "")
        lines.append(f'    <edge id="{escape(edge["id"])}" source="{escape(edge["source"])}" '
                     f'target="{escape(edge["target"])}">')
        lines.append(f'      <data key="rel">{escape(edge["type"])}</data>')
        lines.append(f'      <data key="eanchor">{escape(anchor or "")}</data>')
        lines.append("    </edge>")
    lines += ["  </graph>", "</graphml>", ""]
    return "\n".join(lines)


CYPHER = """// Query set for the paper knowledge graph (Neo4j / Memgraph compatible).
// Load graph.json, or import graph.graphml, then run these.

// Q1: what does a method use, and where is that stated?
MATCH (m:Method {label: $method})-[:USES]->(used:Method)
RETURN used.label AS component, used.anchor AS anchor;

// Q2: which tasks is a method evaluated on, and what does it report?
MATCH (m:Method {label: $method})-[:EVALUATED_ON]->(t:Task)
OPTIONAL MATCH (m)-[r:REPORTS]->(metric:Metric)
RETURN t.label AS task, metric.label AS metric, r.value AS value, r.anchor AS anchor;

// Q3: which conditions and limitations constrain a method?
MATCH (m:Method {label: $method})-[:REQUIRES|LIMITED_BY]->(c)
RETURN type(c) AS kind, c.label AS constraint, c.anchor AS anchor;

// Q4: what is a method compared with, and in which direction?
MATCH (m:Method {label: $method})-[r:COMPARED_WITH|IMPROVES_ON]->(other:Method)
RETURN type(r) AS relation, other.label AS compared_to, r.anchor AS anchor;

// Q5: findings that are not attached to any method (should be empty)
MATCH (f:Finding)
WHERE NOT (f)-[:SUPPORTS|CAUSES]->()
RETURN f.label AS unattached_finding;
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--source", type=Path, default=None)
    args = ap.parse_args(argv)

    work = args.work
    source = load(args.source or (work / "graph-source.json"), {})
    candidates = {c["id"]: c for c in load(work / "candidates.json", [])}
    paper = load(work / "paper.json", {})
    if not source.get("nodes"):
        print("BUILD_BLOCKED " + json.dumps({"reason": "graph-source.json missing or empty"}))
        return 2

    graph, report = build(source, candidates, paper)
    (work / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    (work / "graph.graphml").write_text(to_graphml(graph), encoding="utf-8")
    (work / "queries.cypher").write_text(CYPHER, encoding="utf-8")
    (work / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    print("BUILD_OK " + json.dumps({"nodes": graph["stats"]["nodes"],
                                    "edges": graph["stats"]["edges"],
                                    "merges": len(graph["merges"]),
                                    "problems": report["problems"]}, ensure_ascii=False))
    return 0 if not report["problems"] else 1


if __name__ == "__main__":
    sys.exit(main())
