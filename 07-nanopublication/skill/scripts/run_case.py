#!/usr/bin/env python3
"""Apply a nanopublication case contract: assertions -> nanopubs -> result.json.

Reads the case definition (``/input/case.json`` at evaluation time), emits the
TriG nanopublications, validates them and writes ``result.json`` with the
assertions, their evidence anchors, the source metadata and the validation report.

Assertions are authored by the agent; this script never invents a claim.

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

import validate_nanopub as vn  # noqa: E402

DEFAULT_FIELDS = ("assertions", "nanopublications", "source", "evidence", "qa", "trig")

ALIASES = {
    "assertions": ("assertion", "claims", "断言"),
    "nanopublications": ("nanopub", "nanopublication", "triples", "纳米"),
    "source": ("source", "provenance", "paper", "来源"),
    "evidence": ("evidence", "anchors", "quotes", "证据"),
    "qa": ("qa", "checks", "validation", "核验"),
    "trig": ("trig", "rdf", "serial", "导出"),
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
    ap.add_argument("--assertions", type=Path, default=None)
    ap.add_argument("--case-id", default=None)
    args = ap.parse_args(argv)

    case = load(args.case, {}) if args.case else {}
    task = args.task.read_text(encoding="utf-8", errors="replace") if (
        args.task and args.task.exists()) else ""
    args.work.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    case_id = args.case_id or case.get("case_id") or case.get("id") or "unknown"

    if not (args.work / "candidates.json").exists():
        pdf = args.pdf or next(iter(sorted(Path("/input").glob("*.pdf"))), None)
        if pdf:
            subprocess.run([sys.executable, str(HERE / "prepare.py"), str(pdf),
                            "--out", str(args.work)], check=False)

    assertions_doc = load(args.assertions or (args.work / "assertions.json"), {})
    if not (assertions_doc.get("assertions")):
        result = {"case_id": case_id, "status": "blocked_on_assertions",
                  "reason": "assertions.json missing; author assertions against candidates.json",
                  "candidates": len(load(args.work / "candidates.json", []))}
        (args.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
        print("CASE_BLOCKED " + json.dumps({"candidates": result["candidates"]}, ensure_ascii=False))
        return 2

    subprocess.run([sys.executable, str(HERE / "emit_nanopub.py"), "--work", str(args.work)],
                   check=False, capture_output=True, text=True)
    subprocess.run([sys.executable, str(HERE / "validate_nanopub.py"), "--work", str(args.work)],
                   check=False, capture_output=True, text=True)

    trig = (args.work / "nanopubs.trig").read_text(encoding="utf-8") if (
        args.work / "nanopubs.trig").exists() else ""
    records = vn.load_jsonl(args.work / "nanopubs.jsonl")
    qa = load(args.work / "qa_report.json", {"status": "failed"})
    paper = load(args.work / "paper.json", {})
    shutil.copyfile(args.work / "nanopubs.trig", args.out / "nanopubs.trig")

    assertions = []
    for record in records:
        assertions.append({
            "subject": record["assertion"]["subject"],
            "relation": record["assertion"]["relation"],
            "object": record["assertion"]["object"],
            "qualifiers": record["assertion"].get("qualifiers") or {},
            "evidence_kind": record["assertion"].get("evidence_kind"),
            "confidence": record["assertion"].get("confidence"),
            "quote": record["evidence"]["quote"],
            "page": record["evidence"]["page"],
            "anchor": record["evidence"]["anchor"],
            "section": record["evidence"]["section"],
            "nanopub_uri": record["uri"],
        })
    evidence = [{"anchor": a["anchor"], "page": a["page"], "section": a["section"],
                 "quote_id": None, "nanopub_uri": a["nanopub_uri"]} for a in assertions]
    ctx = {
        "assertions": assertions,
        "nanopublications": [{"uri": r["uri"], "assertion": r["assertion"],
                              "evidence": r["evidence"]} for r in records],
        "source": paper,
        "evidence": evidence,
        "qa": qa,
        "trig": trig,
    }
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
        "schema": "paper-nanopub/result/1.0",
        "case_id": case_id,
        "status": status,
        "task": {"excerpt": task.strip()[:500]},
        "output_contract": fields,
        "results": results,
        "pending_fields": pending,
        "qa": qa,
        "source": paper,
        "uncertainty": qa.get("failures", []),
        "run": {"finished_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                "nanopubs": len(records), "assertions": len(assertions),
                "trig": str(args.out / "nanopubs.trig")},
    }
    (args.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    print("CASE_OK " + json.dumps({
        "case_id": case_id, "status": status, "nanopubs": len(records),
        "assertions": len(assertions), "sections": qa.get("sections_with_assertions"),
        "hard_failures": qa.get("hard_failures"), "fields": len(results), "pending": pending,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
