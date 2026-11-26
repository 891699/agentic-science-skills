#!/usr/bin/env python3
"""Apply a polish case contract: draft + polish + change log -> result.json.

Reads the case definition (``/input/case.json`` at evaluation time), verifies the
polish against the draft, and writes ``result.json`` with the polished text, the
paragraph alignment, the sentence-level change log and the QA/style report.

The polished text is authored by the agent; this script never rewrites prose.

Usage:
    python run_case.py --case /input/case.json --task /input/task.md \
        --pdf /input/paper.pdf --work /app/work --out /app/output
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import verify_polish as vp  # noqa: E402

DEFAULT_FIELDS = ("polished_text", "changes", "segments", "qa", "style")

ALIASES = {
    "polished_text": ("polished", "text", "full_text", "rewrite", "润色"),
    "changes": ("change", "edit", "diff", "修改"),
    "segments": ("segment", "paragraph", "alignment", "段落"),
    "qa": ("qa", "checks", "validation", "核验"),
    "style": ("style", "readability", "metrics", "风格"),
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
    ap.add_argument("--polished", type=Path, default=None)
    ap.add_argument("--case-id", default=None)
    args = ap.parse_args(argv)

    case = load(args.case, {}) if args.case else {}
    task = args.task.read_text(encoding="utf-8", errors="replace") if (
        args.task and args.task.exists()) else ""
    args.work.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    case_id = args.case_id or case.get("case_id") or case.get("id") or "unknown"

    if not (args.work / "segments.json").exists():
        pdf = args.pdf or next(iter(sorted(Path("/input").glob("*.pdf"))), None)
        if pdf:
            subprocess.run([sys.executable, str(HERE / "prepare.py"), str(pdf),
                            "--out", str(args.work)], check=False)

    segments = load(args.work / "segments.json", [])
    polished = vp.load_jsonl(args.polished or (args.work / "polished.jsonl"))
    if not polished:
        result = {"case_id": case_id, "status": "blocked_on_polish",
                  "reason": "polished.jsonl missing; polish segments.json and record the changes",
                  "segments": len(segments)}
        (args.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
        print("CASE_BLOCKED " + json.dumps({"segments": len(segments)}, ensure_ascii=False))
        return 2

    qa = vp.evaluate(segments, polished)
    (args.work / "qa_report.json").write_text(json.dumps(qa, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    by_id = {row["id"]: row for row in polished}
    pairs, changes = [], []
    for segment in segments:
        row = by_id.get(segment["id"], {})
        pairs.append({
            "id": segment["id"],
            "page": segment["page"],
            "block": segment.get("block"),
            "section": segment["section"],
            "source": segment["text"],
            "polished": row.get("polished", ""),
            "changes": row.get("changes") or [],
            "notes": row.get("notes", ""),
        })
        for change in row.get("changes") or []:
            changes.append({"id": segment["id"], **change})
    polished_text = "\n\n".join(p["polished"] for p in pairs if p["polished"])
    source_text = "\n\n".join(p["source"] for p in pairs)
    (args.out / "polished.md").write_text("# Polished draft\n\n" + polished_text + "\n",
                                          encoding="utf-8")
    (args.out / "changes.md").write_text(
        "# Change log\n\n" + "\n\n".join(
            f"**{c['id']}** · {c.get('type')}\n\n- before: `{c.get('before')}`\n"
            f"- after: `{c.get('after')}`\n- why: {c.get('reason')}"
            for c in changes) + "\n", encoding="utf-8")

    ctx = {"polished_text": polished_text, "changes": changes, "segments": pairs,
           "qa": qa, "style": qa.get("style")}
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
        "schema": "paper-polish/result/1.0",
        "case_id": case_id,
        "status": status,
        "task": {"excerpt": task.strip()[:500]},
        "output_contract": fields,
        "results": results,
        "pending_fields": pending,
        "qa": qa,
        "style": qa.get("style"),
        "uncertainty": qa.get("failures", []),
        "run": {"finished_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                "segments": len(pairs), "changes": len(changes),
                "source_words": len(re.findall(r"[A-Za-z']+", source_text)),
                "polished_words": len(re.findall(r"[A-Za-z']+", polished_text))},
    }
    (args.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    print("CASE_OK " + json.dumps({
        "case_id": case_id, "status": status, "segments": len(pairs), "changes": len(changes),
        "hard_failures": qa.get("hard_failures"), "fields": len(results), "pending": pending,
        "style": qa.get("style"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
