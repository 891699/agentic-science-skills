#!/usr/bin/env python3
"""Validate a paper knowledge graph against its source and its own schema.

Checks that node and edge types are in the vocabulary, that every node and edge
carries evidence whose quote occurs verbatim in the parsed paper, that the graph is
connected to the paper node, that aliases did not create duplicate nodes, that the
GraphML export is well formed, and that the query set actually returns results.

Usage:
    python validate_graph.py --work WORK [--selftest]

Exit code 0 when every hard check passes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HARD = ("node_schema", "edge_schema", "edge_evidence", "self_loops", "alias_integrity",
        "connectivity", "queries", "graphml_wellformed")
QUERY_METHOD = "BERT"


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def run_queries(graph: dict, method_label: str = QUERY_METHOD) -> list[dict]:
    nodes = {n["id"]: n for n in graph["nodes"]}
    edges = graph["edges"]

    def ev(edge: dict) -> dict:
        e = (edge.get("evidence") or [{}])[0]
        return {"anchor": e.get("anchor"), "page": e.get("page"), "quote": e.get("quote")}

    target = next((n for n in graph["nodes"]
                   if n["type"] == "Method" and norm(n["label"]) == norm(method_label)), None)
    results = []
    if target is None:
        return [{"id": "Q0", "question": f"method {method_label} not in graph",
                 "rows": [], "evidence": []}]

    def outgoing(types: tuple[str, ...]) -> list[dict]:
        # Skip edges whose endpoints are missing: a broken graph must report a
        # schema error, not crash the query layer.
        return [e for e in edges
                if e["source"] == target["id"] and e["type"] in types
                and e.get("target") in nodes]

    q1_rows = [{"component": nodes[e["target"]]["label"], **ev(e)} for e in outgoing(("uses",))]
    results.append({"id": "Q1", "question": f"what does {method_label} use?",
                    "rows": q1_rows, "evidence": [r["anchor"] for r in q1_rows]})

    q2_rows = []
    for edge in outgoing(("evaluated-on",)):
        row = {"task": nodes[edge["target"]]["label"], **ev(edge)}
        reports = [e for e in outgoing(("reports",))]
        if reports:
            row["reported"] = nodes[reports[0]["target"]]["label"]
            row["reported_anchor"] = ev(reports[0])["anchor"]
        q2_rows.append(row)
    results.append({"id": "Q2", "question": f"which tasks is {method_label} evaluated on, and what does it report?",
                    "rows": q2_rows, "evidence": [r["anchor"] for r in q2_rows]})

    q3_rows = [{"kind": nodes[e["target"]]["type"], "constraint": nodes[e["target"]]["label"], **ev(e)}
               for e in outgoing(("requires", "limited-by"))]
    results.append({"id": "Q3", "question": f"which conditions and limitations constrain {method_label}?",
                    "rows": q3_rows, "evidence": [r["anchor"] for r in q3_rows]})

    q4_rows = [{"relation": e["type"], "other": nodes[e["target"]]["label"], **ev(e)}
               for e in outgoing(("compared-with", "improves-on"))]
    results.append({"id": "Q4", "question": f"what is {method_label} compared with, and in which direction?",
                    "rows": q4_rows, "evidence": [r["anchor"] for r in q4_rows]})

    uncertain = [{"edge": e["id"], "type": e["type"], "confidence": e.get("confidence")}
                 for e in edges if e.get("confidence") in ("medium", "low")]
    results.append({"id": "QU", "question": "which relations are uncertain?",
                    "rows": uncertain, "evidence": []})
    return results


def evaluate(graph: dict, vocab: dict, source_text: str, graphml_text: str,
             merges: list[dict]) -> dict:
    problems: list[dict] = []

    def fail(check: str, where: str, detail: str) -> None:
        problems.append({"check": check, "where": where, "detail": detail})

    node_types = (vocab.get("node_types") or {})
    edge_types = (vocab.get("edge_types") or {})
    nodes = {n["id"]: n for n in graph.get("nodes") or []}
    edges = graph.get("edges") or []

    # nodes
    for node in nodes.values():
        spec = node_types.get(node.get("type"))
        if spec is None:
            fail("node_schema", node["id"], f"unknown node type {node.get('type')!r}")
            continue
        for field in spec.get("required") or []:
            if not node.get(field):
                fail("node_schema", node["id"], f"missing required field {field}")
        if node["type"] != "Paper":
            evidence = node.get("evidence") or []
            if not evidence:
                fail("edge_evidence", node["id"], "node has no evidence")
            else:
                ev = evidence[0]
                if ev.get("quote") and ev["quote"] not in source_text:
                    fail("edge_evidence", node["id"], "node quote not verbatim in the source")
                if not re.match(r"^p\d+b\d+$", ev.get("anchor") or ""):
                    fail("edge_evidence", node["id"], f"bad anchor {ev.get('anchor')!r}")

    # edges
    for edge in edges:
        spec = edge_types.get(edge.get("type"))
        if spec is None:
            fail("edge_schema", edge["id"], f"unknown edge type {edge.get('type')!r}")
            continue
        src = nodes.get(edge.get("source"))
        dst = nodes.get(edge.get("target"))
        if src is None or dst is None:
            fail("edge_schema", edge["id"], "endpoint missing from the node set")
            continue
        allowed_src = spec.get("source") or []
        allowed_dst = spec.get("target") or []
        if src["type"] not in allowed_src:
            fail("edge_schema", edge["id"],
                 f"{edge['type']} cannot start at a {src['type']} (allowed: {allowed_src})")
        if dst["type"] not in allowed_dst:
            fail("edge_schema", edge["id"],
                 f"{edge['type']} cannot end at a {dst['type']} (allowed: {allowed_dst})")
        if edge.get("source") == edge.get("target"):
            fail("self_loops", edge["id"], "edge points at its own source")
        evidence = edge.get("evidence") or []
        if not evidence:
            fail("edge_evidence", edge["id"], "edge has no evidence")
        else:
            ev = evidence[0]
            if not ev.get("quote"):
                fail("edge_evidence", edge["id"], "edge evidence has no quote")
            elif ev["quote"] not in source_text:
                fail("edge_evidence", edge["id"], "edge quote not verbatim in the source")
            if not re.match(r"^p\d+b\d+$", ev.get("anchor") or ""):
                fail("edge_evidence", edge["id"], f"bad anchor {ev.get('anchor')!r}")
        if edge.get("confidence") not in ("high", "medium", "low"):
            fail("edge_evidence", edge["id"], f"bad confidence {edge.get('confidence')!r}")

    # alias integrity: no two nodes share a label, unless a merge was recorded
    seen: dict[str, str] = {}
    for node in nodes.values():
        for label in [node.get("label")] + list(node.get("aliases") or []):
            key = norm(label)
            if not key:
                continue
            if key in seen and seen[key] != node["id"]:
                fail("alias_integrity", node["id"],
                     f"label {label!r} already used by {seen[key]} without a merge record")
            seen.setdefault(key, node["id"])
    for merge in merges:
        if not merge.get("reason"):
            fail("alias_integrity", str(merge.get("merged")), "merge has no recorded reason")

    # connectivity: every node reaches the paper through from-paper edges
    paper_node = next((n for n in nodes.values() if n["type"] == "Paper"), None)
    if paper_node is None:
        fail("connectivity", "*", "no Paper node")
    else:
        linked = {e["source"] for e in edges if e["type"] == "from-paper"
                  and e["target"] == paper_node["id"]}
        for node in nodes.values():
            if node["id"] != paper_node["id"] and node["id"] not in linked:
                fail("connectivity", node["id"], "node has no from-paper edge")

    # graphml
    try:
        root = ET.fromstring(graphml_text)
        ns = "{http://graphml.graphdrawing.org/xmlns}"
        xml_nodes = root.findall(f".//{ns}node")
        xml_edges = root.findall(f".//{ns}edge")
        if len(xml_nodes) != len(nodes):
            fail("graphml_wellformed", "*", f"{len(xml_nodes)} nodes in GraphML vs {len(nodes)} in JSON")
        if len(xml_edges) != len(edges):
            fail("graphml_wellformed", "*", f"{len(xml_edges)} edges in GraphML vs {len(edges)} in JSON")
    except ET.ParseError as exc:
        fail("graphml_wellformed", "*", f"GraphML does not parse: {exc}")

    # queries
    queries = run_queries(graph)
    answered = [q for q in queries if q["id"] != "QU" and q["rows"]]
    if len(answered) < 3:
        fail("queries", "*", f"only {len(answered)} queries return rows (need 3)")
    for query in queries:
        if query["id"] != "QU" and not query["rows"]:
            fail("queries", query["id"], "query returns no rows")
        for row in query["rows"]:
            if query["id"] != "QU" and not row.get("anchor"):
                fail("queries", query["id"], "row has no evidence anchor")

    hard_failed = [p for p in problems if p["check"] in HARD]
    checks = {name: {"failed": len([p for p in problems if p["check"] == name])} for name in HARD}
    return {
        "schema": "paper-kg/qa/1.0",
        "nodes": len(nodes),
        "edges": len(edges),
        "merges": len(merges),
        "queries": queries,
        "queries_answered": len(answered),
        "checks": checks,
        "hard_failures": len(hard_failed),
        "status": ("success" if not hard_failed else
                   "partial" if nodes else "failed"),
        "failures": hard_failed,
    }


def selftest(graph: dict, vocab: dict, source_text: str, graphml_text: str,
             merges: list[dict]) -> dict:
    import copy

    cases = {}

    def run(name: str, fn) -> None:
        g = copy.deepcopy(graph)
        text = graphml_text
        m = copy.deepcopy(merges)
        out = fn(g, m)
        if isinstance(out, str):
            text = out
        report = evaluate(g, vocab, source_text, text, m)
        cases[name] = {"detected": report["status"] != "success",
                       "checks": sorted({p["check"] for p in report["failures"]})}

    run("dangling_edge", lambda g, m: g["edges"][0].update({"target": "kg:method:does-not-exist"}))
    run("bad_direction", lambda g, m: next(
        e for e in g["edges"] if e["type"] == "uses").update({"type": "evaluated-on"}))
    run("missing_evidence", lambda g, m: g["edges"][0].pop("evidence"))
    run("duplicate_label", lambda g, m: g["nodes"].append(
        {**copy.deepcopy(g["nodes"][1]), "id": "kg:method:duplicate"}))
    run("orphan_node", lambda g, m: g["edges"].clear() or g["edges"].extend(
        [e for e in graph["edges"] if e["type"] != "from-paper"]))
    run("broken_graphml", lambda g, m: "<graphml><graph>")
    run("no_queries", lambda g, m: next(
        n for n in g["nodes"] if n["type"] == "Method").update({"label": "NotBERT"}))
    for name, result in cases.items():
        result["name"] = name
    clean = evaluate(graph, vocab, source_text, graphml_text, merges)
    return {"clean": clean["status"], "injected": cases,
            "all_detected": all(v["detected"] for v in cases.values())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    work = args.work
    graph = load(work / "graph.json", {"nodes": [], "edges": []})
    vocab = load(Path(__file__).resolve().parent.parent / "schema" / "vocab.json", {})
    source_text = load(work / "parse.json", {}).get("markdown", "")
    graphml_text = (work / "graph.graphml").read_text(encoding="utf-8") if (
        work / "graph.graphml").exists() else ""

    if args.selftest:
        result = selftest(graph, vocab, source_text, graphml_text, graph.get("merges") or [])
        (work / "selftest.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
        print("SELFTEST " + json.dumps({
            "clean": result["clean"],
            "detected": f"{sum(1 for v in result['injected'].values() if v['detected'])}"
                        f"/{len(result['injected'])}"}, ensure_ascii=False))
        return 0 if result["all_detected"] else 1

    report = evaluate(graph, vocab, source_text, graphml_text, graph.get("merges") or [])
    (work / "qa_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    print("VALIDATE " + json.dumps({
        "status": report["status"], "nodes": report["nodes"], "edges": report["edges"],
        "merges": report["merges"], "queries": report["queries_answered"],
        "hard_failures": report["hard_failures"],
        "failed": {k: v["failed"] for k, v in report["checks"].items() if v["failed"]},
    }, ensure_ascii=False))
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
