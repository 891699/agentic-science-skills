#!/usr/bin/env python3
"""Apply a methods-section case contract: draft + spec -> result.json.

Writes the section, the reproduction spec, the gap list (what the paper does not
say) and the QA report, plus a human-readable checklist.

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
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import verify_method as vm  # noqa: E402

DEFAULT_FIELDS = ("method_section", "spec", "checklist", "gaps", "evidence", "qa")

ALIASES = {
    "method_section": ("method", "section", "draft", "方法与实验", "正文"),
    "spec": ("spec", "parameters", "参数", "复现契约"),
    "checklist": ("checklist", "table", "清单"),
    "gaps": ("gap", "unavailable", "missing", "缺口", "待确认"),
    "evidence": ("evidence", "anchor", "provenance", "证据"),
    "qa": ("qa", "checks", "verify", "核验"),
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


def checklist(spec: dict, mapping: dict) -> list[dict]:
    """One row per slot: value, status, source, and the sentence that states it."""
    references: dict[str, int] = {}
    for index, entry in enumerate(mapping.get("sentences") or [], start=1):
        for slot_id in entry.get("slots") or []:
            references.setdefault(slot_id, index)
    rows = []
    for slot in spec.get("slots") or []:
        rows.append({
            "id": slot["id"], "family": slot.get("family"), "name": slot.get("name"),
            "value": slot.get("value"), "unit": slot.get("unit"),
            "status": slot.get("status"), "source": slot.get("source"),
            "reason": slot.get("reason"), "sentence": references.get(slot["id"]),
        })
    return rows


def render_checklist(rows: list[dict]) -> str:
    lines = ["| id | family | parameter | value | unit | status | source | sentence |",
             "|---|---|---|---|---|---|---|---|"]
    for row in rows:
        value = row["value"] if row["value"] is not None else "—"
        if isinstance(value, list):
            value = ", ".join(value)
        lines.append(f"| {row['id']} | {row['family']} | {row['name']} | {value} | "
                     f"{row['unit'] or ''} | {row['status']} | {row['source'] or ''} | "
                     f"{row['sentence'] or ''} |")
    return "\n".join(lines) + "\n"


def render_gaps(rows: list[dict]) -> str:
    gaps = [row for row in rows if row["status"] == "unavailable"]
    lines = ["# Open questions for the author", "",
             "Each item is missing from the paper. The draft marks it unavailable instead of "
             "guessing; a human must supply it before the section is submission-ready.", ""]
    for index, row in enumerate(gaps, start=1):
        lines.append(f"{index}. **{row['name']}** ({row['family']}) — {row['reason']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", type=Path, default=None)
    ap.add_argument("--task", type=Path, default=None)
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

    md_path = args.work / "method.md"
    if not md_path.exists():
        print("CASE_BLOCKED {\"reason\": \"method.md missing\"}")
        return 2
    md = md_path.read_text(encoding="utf-8")
    mapping = load(args.work / "mapping.json", {})
    spec = load(args.work / "spec.json", {})
    facts = {f["id"]: f for f in load(args.work / "facts.json", [])}
    parse_text = load(args.work / "parse.json", {}).get("markdown", "")

    qa = vm.evaluate(md, mapping, spec, facts, parse_text)
    (args.work / "qa_report.json").write_text(json.dumps(qa, ensure_ascii=False, indent=1),
                                              encoding="utf-8")

    rows = checklist(spec, mapping)
    (args.out / "checklist.md").write_text(render_checklist(rows), encoding="utf-8")
    (args.out / "gaps.md").write_text(render_gaps(rows), encoding="utf-8")
    shutil.copyfile(md_path, args.out / "method.md")

    evidence = []
    for index, entry in enumerate(mapping.get("sentences") or [], start=1):
        evidence.append({
            "sentence": index, "section": entry.get("section"), "role": entry.get("role"),
            "slots": entry.get("slots") or [],
            "anchors": [{"fact": f, "page": (facts.get(f) or {}).get("page"),
                         "anchor": (facts.get(f) or {}).get("anchor")}
                        for f in entry.get("evidence") or []],
        })

    sections = [{"title": head, "sentences": sum(
        1 for entry in mapping.get("sentences") or []
        if (entry.get("section") or "").startswith(head.split()[0]))}
        for head in qa["sections"]]

    ctx = {
        "method_section": {"sections": sections, "text": md, "sentences": qa["sentences"]},
        "spec": {"slots": spec.get("slots") or [], "count": qa["slots"]},
        "checklist": rows,
        "gaps": [row for row in rows if row["status"] == "unavailable"],
        "evidence": evidence,
        "qa": qa,
    }
    fields = contract_fields(case) or {name: name for name in DEFAULT_FIELDS}
    results, pending = {}, []
    for name in fields:
        ok, value = field_value(name, ctx)
        if ok:
            results[name] = value
        else:
            pending.append(name)

    status = qa["status"]
    if pending:
        status = "partial" if status == "success" else status
    result = {
        "schema": "method-write/result/1.0",
        "case_id": case_id,
        "status": status,
        "task": {"excerpt": task.strip()[:500]},
        "output_contract": fields,
        "results": results,
        "pending_fields": pending,
        "paper": load(args.work / "paper.json", {}),
        "qa": qa,
        "run": {"finished_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                "sentences": qa["sentences"], "slots": qa["slots"],
                "unavailable": qa["unavailable"]},
    }
    (args.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    print("CASE_OK " + json.dumps({
        "case_id": case_id, "status": status, "sentences": qa["sentences"],
        "slots": qa["slots"], "gaps": qa["unavailable"],
        "hard_failures": qa["hard_failures"], "fields": len(results), "pending": pending,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
