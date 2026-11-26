#!/usr/bin/env python3
"""Apply a note case contract: assemble result.json from the note and its checks.

Reads the case definition (``/input/case.json`` at evaluation time), attaches the
verbatim quote to every claim from ``candidates.json``, renders ``note.md`` and
writes ``result.json`` with the card, the section notes, the evidence anchors and
the QA report.

The note itself is written by the agent; this script never invents a claim.

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

import verify_notes  # noqa: E402

DEFAULT_FIELDS = ("card", "section_notes", "evidence", "coverage", "qa", "note_markdown")

ALIASES = {
    "card": ("card", "paper_card", "fields", "卡片"),
    "section_notes": ("section", "sections", "notes", "章节"),
    "evidence": ("evidence", "anchors", "sources", "来源"),
    "coverage": ("coverage", "completeness", "覆盖"),
    "qa": ("qa", "checks", "quality", "核验"),
    "note_markdown": ("markdown", "note", "summary", "笔记"),
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


def attach_quotes(notes: dict, by_candidate: dict) -> dict:
    """Attach the verbatim quote and its page to every claim in the note."""
    out = {"paper": notes.get("paper", {}), "card": {}, "sections": []}

    def with_quote(item: dict) -> dict:
        cand = by_candidate.get(item.get("quote_id"), {})
        return {**item, "quote": cand.get("text"), "page": cand.get("page"),
                "anchor": cand.get("anchor"), "quote_section": cand.get("section")}

    card = notes.get("card") or {}
    for key, value in card.items():
        if isinstance(value, list):
            out["card"][key] = [with_quote(v) for v in value if isinstance(v, dict)]
        elif isinstance(value, dict):
            out["card"][key] = with_quote(value)
        else:
            out["card"][key] = value
    for sec in notes.get("sections") or []:
        out["sections"].append({
            "section": sec.get("section"),
            "role": sec.get("role"),
            "notes": [with_quote(n) for n in (sec.get("notes") or [])],
        })
    return out


def render_markdown(note: dict) -> str:
    paper = note.get("paper", {})
    lines = [f"# {paper.get('title', 'Note')}", ""]
    if paper.get("authors"):
        lines.append(f"*{paper['authors']}* — {paper.get('pages', '?')} pages")
        lines.append("")
    lines.append("## Paper card")
    lines.append("")
    lines.append("| Field | Claim | Page | Anchor | Quote |")
    lines.append("|---|---|---|---|---|")
    for key, value in (note.get("card") or {}).items():
        items = value if isinstance(value, list) else [value]
        for item in items:
            if not isinstance(item, dict):
                continue
            quote = (item.get("quote") or "").replace("|", "\\|")
            claim = (item.get("claim") or "").replace("|", "\\|")
            lines.append(f"| {key} | {claim} | p.{item.get('page')} | `{item.get('anchor')}` | {quote[:160]} |")
    lines.append("")
    lines.append("## Section notes")
    for sec in note.get("sections") or []:
        lines.append("")
        lines.append(f"### {sec['section']}")
        if sec.get("role"):
            lines.append(f"*{sec['role']}*")
        for item in sec.get("notes") or []:
            lines.append("")
            lines.append(f"- **{item.get('claim')}**  ")
            lines.append(f"  p.{item.get('page')} `{item.get('anchor')}` — “{item.get('quote')}”")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", type=Path, default=None)
    ap.add_argument("--task", type=Path, default=None)
    ap.add_argument("--pdf", type=Path, default=None)
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--out", type=Path, default=Path("output"))
    ap.add_argument("--notes", type=Path, default=None)
    ap.add_argument("--case-id", default=None)
    ap.add_argument("--prepare", action="store_true", help="run prepare.py first when work is empty")
    args = ap.parse_args(argv)

    case = load(args.case, {}) if args.case else {}
    task_text = args.task.read_text(encoding="utf-8", errors="replace") if (
        args.task and args.task.exists()) else ""
    args.work.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    case_id = args.case_id or case.get("case_id") or case.get("id") or "unknown"

    if args.prepare and not (args.work / "candidates.json").exists():
        pdf = args.pdf or next(iter(sorted(Path("/input").glob("*.pdf"))), None)
        if pdf:
            subprocess.run([sys.executable, str(HERE / "prepare.py"), str(pdf),
                            "--out", str(args.work)], check=False)

    parse = load(args.work / "parse.json", {})
    candidates = load(args.work / "candidates.json", [])
    segments = load(args.work / "segments.json", [])
    notes = load(args.notes or (args.work / "notes.json"), {})

    if not notes or not notes.get("sections"):
        result = {"case_id": case_id, "status": "blocked_on_notes",
                  "reason": "notes.json missing; write notes against candidates.json",
                  "candidates": len(candidates), "sections": len(segments)}
        (args.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
        print("CASE_BLOCKED " + json.dumps({"candidates": len(candidates)}, ensure_ascii=False))
        return 2

    by_candidate = {c["id"]: c for c in candidates}
    note = attach_quotes(notes, by_candidate)
    qa = verify_notes.evaluate(parse, candidates, segments, notes)
    (args.work / "qa_report.json").write_text(json.dumps(qa, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    markdown = render_markdown(note)
    (args.work / "note.md").write_text(markdown, encoding="utf-8")

    evidence = []
    for item in verify_notes.claim_entries(notes):
        cand = by_candidate.get(item.get("quote_id"), {})
        if cand:
            evidence.append({"where": item["where"], "anchor": cand["anchor"],
                             "page": cand["page"], "block": cand.get("block"),
                             "quote_id": cand["id"]})
    coverage = {
        "sections_in_paper": qa["sections_in_paper"],
        "sections_in_note": qa["sections_in_note"],
        "sections_with_claims": qa["sections_with_claims"],
        "claims": qa["claims"],
        "coverage_rate": round(qa["sections_in_note"] / max(1, qa["sections_in_paper"]), 4),
    }
    ctx = {
        "card": note.get("card"),
        "section_notes": note.get("sections"),
        "evidence": evidence,
        "coverage": coverage,
        "qa": qa,
        "note_markdown": markdown,
    }
    fields = contract_fields(case) or {name: name for name in DEFAULT_FIELDS}
    results, pending = {}, []
    for name in fields:
        ok, value = field_value(name, ctx)
        if ok:
            results[name] = value
        else:
            pending.append(name)

    status = qa["status"] if not pending else ("partial" if qa["status"] == "success"
                                               else qa["status"])
    result = {
        "schema": "paper-note/result/1.0",
        "case_id": case_id,
        "status": status,
        "task": {"excerpt": task_text.strip()[:500]},
        "document": {"pdf": str(args.pdf) if args.pdf else None,
                     "pages": parse.get("source", {}).get("pages")},
        "output_contract": fields,
        "results": results,
        "pending_fields": pending,
        "coverage": coverage,
        "qa": qa,
        "uncertainty": qa["failures"],
        "run": {"finished_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                "claims": qa["claims"], "note_md": str(args.work / "note.md")},
    }
    (args.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    (args.out / "note.md").write_text(markdown, encoding="utf-8")
    print("CASE_OK " + json.dumps({
        "case_id": case_id, "status": status, "claims": qa["claims"],
        "sections": f"{qa['sections_in_note']}/{qa['sections_in_paper']}",
        "hard_failures": qa["hard_failures"], "fields": len(results), "pending": pending,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
