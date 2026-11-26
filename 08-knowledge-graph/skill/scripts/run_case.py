#!/usr/bin/env python3
"""Apply a knowledge-graph case contract: graph + queries -> result.json.

Reads the case definition (``/input/case.json`` at evaluation time), builds the
graph from the authored source, validates it, runs the query set and writes
``result.json`` with nodes, edges, query answers, evidence anchors and the QA
report. Also copies the exports (graph.json, graph.graphml, queries.cypher) next
to the result.

Usage:
    python run_case.py --case /input/case.json --task /input/task.md \
        --pdf /input/paper.pdf --work /app/work --out /app/output
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import validate_graph as vg  # noqa: E402

DEFAULT_FIELDS = ("nodes", "edges", "queries", "evidence", "qa", "exports")

ALIASES = {
    "nodes": ("node", "entities", "实体"),
    "edges": ("edge", "relations", "关系"),
    "queries": ("query", "qa_pairs", "查询"),
    "evidence": ("evidence", "anchors", "sources", "证据"),
    "qa": ("qa", "checks", "validation", "核验"),
    "exports": ("export", "graphml", "cypher", "导出"),
}


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def contract_fields(case: dict) -> dict[str, str]:
    contract = case.get("output_contract") or case.get("outputs") or {}
    fields: dict[str, str] = {}
    if isinstance(contract, dict):
        fields.update({k: str(v) for k, v in contract.items()})
        for key in ("fields", "properties", "required"):
            value = contract.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        fields.setdefault(item, "")
                    elif isinstance(item, dict) and "name" in item:
                        fields.setdefault(item["name"], str(item.get("description", "")))
    elif isinstance(contract, list):
        for item in contract:
            if isinstance(item, str):
                fields[item] = ""
            elif isinstance(item, dict) and "name" in item:
                fields[item["name"]] = str(item.get("description", ""))
    return fields


def field_value(name: str, ctx: dict):
    key = norm(name)
    for family, aliases in ALIASES.items():
        candidates = [norm(family)] + [norm(a) for a in aliases]
        if any(c and (key == c or key.startswith(c) or c in key) for c in candidates):
            return True, ctx[family]
    return False, None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", type=Path, default=None)
    ap.add_argument("--task", type=Path, default=None)
    ap.add_argument("--pdf", type=Path, default=None)
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--out", type=Path, default=Path("output"))
    ap.add_argument("--case-id", default=None)
    args = ap.parse_args(argv)

    case = load(args.case, {}) if args.case else {}
    task = args.task.read_text(encoding="utf-8", errors="replace") if (
        args.task and args.task.exists()) else ""
    args.work.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    case_id = args.case_id or case.get("case_id") or case.get("id") or "unknown"

    if not (args.work / "graph-source.json").exists():
        result = {"case_id": case_id, "status": "blocked_on_graph_source",
                  "reason": "graph-source.json missing; author nodes and edges against candidates.json"}
        (args.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
        print("CASE_BLOCKED " + json.dumps({"reason": result["reason"]}, ensure_ascii=False))
        return 2

    subprocess.run([sys.executable, str(HERE / "build_graph.py"), "--work", str(args.work)],
                   capture_output=True, text=True, check=False)
    subprocess.run([sys.executable, str(HERE / "validate_graph.py"), "--work", str(args.work)],
                   capture_output=True, text=True, check=False)

    graph = load(args.work / "graph.json", {"nodes": [], "edges": []})
    qa = load(args.work / "qa_report.json", {"status": "failed"})
    for name in ("graph.json", "graph.graphml", "queries.cypher"):
        src = args.work / name
        if src.exists():
            shutil.copyfile(src, args.out / name)

    nodes = [{k: n.get(k) for k in ("id", "type", "label", "aliases", "confidence", "evidence")}
             for n in graph.get("nodes", [])]
    edges = [{k: e.get(k) for k in ("id", "source", "target", "type", "condition",
                                    "confidence", "evidence")}
             for e in graph.get("edges", [])]
    evidence = []
    for item in graph.get("nodes", []) + graph.get("edges", []):
        for ev in item.get("evidence") or []:
            evidence.append({"item": item.get("id"), "anchor": ev.get("anchor"),
                             "page": ev.get("page"), "quote": ev.get("quote")})
    exports = {"graph_json": str(args.out / "graph.json"),
               "graphml": str(args.out / "graph.graphml"),
               "cypher": str(args.out / "queries.cypher")}
    ctx = {"nodes": nodes, "edges": edges, "queries": qa.get("queries") or [],
           "evidence": evidence, "qa": qa, "exports": exports}

    fields = contract_fields(case) or {name: name for name in DEFAULT_FIELDS}
    results, pending = {}, []
    for name in fields:
        ok, value = field_value(name, ctx)
        if ok:
            results[name] = value
        else:
            pending.append(name)

    status = qa.get("status", "failed")
    if pending:
        status = "partial" if status == "success" else status
    result = {
        "schema": "paper-kg/result/1.0",
        "case_id": case_id,
        "status": status,
        "task": {"excerpt": task.strip()[:500]},
        "output_contract": fields,
        "results": results,
        "pending_fields": pending,
        "paper": graph.get("paper"),
        "stats": graph.get("stats"),
        "merges": graph.get("merges") or [],
        "qa": qa,
        "uncertainty": qa.get("failures", []),
        "run": {"finished_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                "nodes": len(nodes), "edges": len(edges),
                "queries_answered": qa.get("queries_answered")},
    }
    (args.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    print("CASE_OK " + json.dumps({
        "case_id": case_id, "status": status, "nodes": len(nodes), "edges": len(edges),
        "merges": len(graph.get("merges") or []),
        "queries": qa.get("queries_answered"), "hard_failures": qa.get("hard_failures"),
        "fields": len(results), "pending": pending,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
