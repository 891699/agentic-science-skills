#!/usr/bin/env python3
"""Apply a LaTeX case contract: compiled project + reports -> result.json."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

DEFAULT_FIELDS = ("latex_source", "pdf", "build_report", "static_checks", "log_summary")

ALIASES = {
    "latex_source": ("source", "tex", "latex", "源码", "稿"),
    "pdf": ("pdf", "compiled", "产物"),
    "build_report": ("build", "compile", "编译"),
    "static_checks": ("check", "static", "lint", "检查"),
    "log_summary": ("log", "errors", "日志"),
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
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--case", type=Path, default=None)
    ap.add_argument("--task", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=Path("output"))
    ap.add_argument("--case-id", default=None)
    args = ap.parse_args(argv)

    case = load(args.case, {}) if args.case else {}
    task = args.task.read_text(encoding="utf-8", errors="replace") if (
        args.task and args.task.exists()) else ""
    args.out.mkdir(parents=True, exist_ok=True)
    case_id = args.case_id or case.get("case_id") or case.get("id") or "unknown"

    build = load(args.project / "build_report.json", {})
    before = load(args.project.parent / "check_before.json", {})
    after = load(args.project.parent / "check_after.json", {})

    source_files = {}
    for path in sorted(args.project.rglob("*.tex")):
        source_files[path.relative_to(args.project).as_posix()] = path.read_text(encoding="utf-8")
    for path in sorted(args.project.rglob("*.bib")):
        source_files[path.relative_to(args.project).as_posix()] = path.read_text(encoding="utf-8")

    pdf = args.project / "main.pdf"
    if pdf.exists():
        shutil.copyfile(pdf, args.out / "main.pdf")
    (args.out / "main.tex").write_text(source_files.get("main.tex", ""), encoding="utf-8")
    (args.out / "build_report.json").write_text(json.dumps(build, ensure_ascii=False, indent=1),
                                                encoding="utf-8")
    (args.out / "checks.json").write_text(
        json.dumps({"before": before, "after": after}, ensure_ascii=False, indent=1),
        encoding="utf-8")

    rounds = build.get("rounds") or []
    repairs = [repair for item in rounds for repair in item.get("repairs") or []]
    ctx = {
        "latex_source": source_files,
        "pdf": {"path": str(args.out / "main.pdf"), "bytes": pdf.stat().st_size if pdf.exists() else 0},
        "build_report": build,
        "static_checks": {"before": before, "after": after},
        "log_summary": {"rounds": len(rounds), "repairs": repairs,
                        "final": build.get("final", {})},
    }
    fields = contract_fields(case) or {name: name for name in DEFAULT_FIELDS}
    results, pending = {}, []
    for name in fields:
        ok, value = field_value(name, ctx)
        if ok:
            results[name] = value
        else:
            pending.append(name)

    status = build.get("status", "failed")
    if pending:
        status = "partial" if status == "success" else status
    result = {
        "schema": "latex-write/result/1.0",
        "case_id": case_id,
        "status": status,
        "task": {"excerpt": task.strip()[:500]},
        "output_contract": fields,
        "results": results,
        "pending_fields": pending,
        "build": build,
        "checks": {"before": {"errors": before.get("errors"),
                              "categories": before.get("categories")},
                   "after": {"errors": after.get("errors"),
                             "categories": after.get("categories")}},
        "run": {"finished_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                "rounds": len(rounds), "repairs": len(repairs),
                "pdf_bytes": ctx["pdf"]["bytes"]},
    }
    (args.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    print("CASE_OK " + json.dumps({
        "case_id": case_id, "status": status, "rounds": len(rounds),
        "repairs": repairs, "pdf_bytes": ctx["pdf"]["bytes"],
        "fields": len(results), "pending": pending,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
