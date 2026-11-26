#!/usr/bin/env python3
"""Apply a citation-audit case contract: audit + exports -> result.json.

Reads the case definition (``/input/case.json`` at evaluation time), runs the
audit, copies the exports and writes ``result.json`` with the parsed references,
the citation map, the unresolved/uncited findings and the QA report.

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

DEFAULT_FIELDS = ("references", "citations", "resolved", "unresolved", "merges", "qa", "exports")

ALIASES = {
    "references": ("reference", "bibliography", "refs", "参考文献"),
    "citations": ("citation", "intext", "markers", "引用"),
    "resolved": ("resolved", "map", "mapping", "对应"),
    "unresolved": ("unresolved", "missing", "dangling", "缺失"),
    "merges": ("merge", "dedupe", "去重"),
    "qa": ("qa", "checks", "audit", "核验"),
    "exports": ("export", "bib", "csl", "导出"),
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

    if not (args.work / "refs.json").exists():
        pdf = args.pdf or next(iter(sorted(Path("/input").glob("*.pdf"))), None)
        if pdf:
            subprocess.run([sys.executable, str(HERE / "prepare.py"), str(pdf),
                            "--out", str(args.work)], check=False)

    subprocess.run([sys.executable, str(HERE / "audit.py"), "--work", str(args.work)],
                   check=False, capture_output=True, text=True)

    report = load(args.work / "audit_report.json", {"status": "failed"})
    refs = load(args.work / "refs_parsed.json", [])
    citations = load(args.work / "citations_resolved.json", {})
    for name in ("refs.bib", "refs.csl.json", "citations.csv"):
        src = args.work / name
        if src.exists():
            shutil.copyfile(src, args.out / name)

    exports = {"bibtex": str(args.out / "refs.bib"),
               "csl_json": str(args.out / "refs.csl.json"),
               "citation_csv": str(args.out / "citations.csv")}
    ctx = {
        "references": [{k: r.get(k) for k in ("id", "key", "authors", "surname", "year",
                                              "title", "venue", "doi", "arxiv", "anchor")}
                       for r in refs],
        "citations": report.get("resolved_rows", []),
        "resolved": report.get("resolved_rows", []),
        "unresolved": report.get("unresolved_rows", []),
        "merges": report.get("merges", []),
        "qa": report,
        "exports": exports,
    }
    fields = contract_fields(case) or {name: name for name in DEFAULT_FIELDS}
    results, pending = {}, []
    for name in fields:
        ok, value = field_value(name, ctx)
        if ok:
            results[name] = value
        else:
            pending.append(name)

    status = report.get("status", "failed")
    if pending:
        status = "partial" if status == "success" else status
    findings = [{"where": item.get("where"), "detail": item.get("detail")}
                for item in report.get("review", [])]
    result = {
        "schema": "cite-audit/result/1.0",
        "case_id": case_id,
        "status": status,
        "task": {"excerpt": task.strip()[:500]},
        "output_contract": fields,
        "results": results,
        "pending_fields": pending,
        "paper": load(args.work / "paper.json", {}),
        "qa": report,
        "findings": findings,
        "run": {"finished_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                "references": len(refs), "citations": len(report.get("resolved_rows", [])),
                "merges": len(report.get("merges", []))},
    }
    (args.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    print("CASE_OK " + json.dumps({
        "case_id": case_id, "status": status, "references": len(refs),
        "resolved": report.get("resolved"), "unresolved": report.get("unresolved"),
        "uncited": report.get("uncited"), "merges": len(report.get("merges", [])),
        "hard_failures": report.get("hard_failures"), "fields": len(results),
        "pending": pending,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
