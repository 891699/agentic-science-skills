#!/usr/bin/env python3
"""Apply an introduction/related-work case contract: draft + evidence map -> result.json.

Writes the deliverable and the audit trail together:

* ``result.json``      contract fields: intro, related work, contributions, evidence map, QA
* ``intro.md`` / ``related.md``  the prose, copied for the reader
* ``evidence_map.md``  one row per sentence: what it claims, what backs it, where
* ``coverage.json``    which works each group cites, and which cited works are unused

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

import verify_draft as vd  # noqa: E402

DEFAULT_FIELDS = ("intro", "related", "contributions", "groups", "evidence_map", "coverage", "qa")

ALIASES = {
    "intro": ("introduction", "background", "引言", "背景"),
    "related": ("related", "related_work", "相关工作"),
    "contributions": ("contribution", "贡献"),
    "groups": ("group", "routes", "分组"),
    "evidence_map": ("evidence", "map", "provenance", "证据"),
    "coverage": ("coverage", "cited", "覆盖"),
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


def evidence_rows(claims: dict, facts: dict, works: dict) -> list[dict]:
    rows = []
    for unit in vd.units_of(claims):
        parts = []
        for item in unit.get("evidence") or []:
            kind = item.get("type")
            ref = item.get("ref")
            if kind == "source" and ref in facts:
                fact = facts[ref]
                parts.append({"type": "source", "ref": ref, "page": fact.get("page"),
                              "anchor": fact.get("anchor"), "quote": fact.get("text")})
            elif kind == "citation" and ref in works:
                work = works[ref]
                parts.append({"type": "citation", "ref": ref, "author": work.get("surname"),
                              "year": work.get("year"), "title": work.get("title"),
                              "anchor": work.get("anchor")})
            else:
                parts.append({"type": kind, "ref": ref,
                              "note": item.get("note") or unit.get("note")})
        rows.append({"id": unit.get("id"), "bucket": unit.get("_bucket"),
                     "role": unit.get("role"), "group": unit.get("group"),
                     "text": unit.get("text"), "maps_to": unit.get("maps_to"),
                     "evidence": parts, "note": unit.get("note")})
    return rows


def render_map(rows: list[dict]) -> str:
    lines = ["# Evidence map", "",
             "One row per sentence of the draft. `source` rows point at a sentence of the paper "
             "with its page and block; `citation` rows point at a reference entry; `judgement` "
             "rows are the author's inference and say so.", "",
             "| id | part | role | sentence | evidence |", "|---|---|---|---|---|"]
    for row in rows:
        bits = []
        for item in row["evidence"]:
            if item["type"] == "source":
                bits.append(f"source `{item['ref']}` p.{item.get('page')} ({item.get('anchor')})")
            elif item["type"] == "citation":
                bits.append(f"cite `{item['ref']}` {item.get('author')} {item.get('year')}")
            else:
                bits.append("judgement")
        sentence = (row.get("text") or "").replace("|", "\\|")
        lines.append(f"| {row['id']} | {row['bucket']} | {row.get('role') or ''} | "
                     f"{sentence} | {'; '.join(bits)} |")
    return "\n".join(lines) + "\n"


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

    claims = load(args.work / "claims.json", {})
    if not claims.get("intro"):
        result = {"case_id": case_id, "status": "blocked_on_draft",
                  "reason": "claims.json missing; assemble the draft before applying the contract"}
        (args.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
        print("CASE_BLOCKED " + json.dumps({"reason": result["reason"]}, ensure_ascii=False))
        return 2

    facts = {f["id"]: f for f in load(args.work / "facts.json", [])}
    works = {w["key"]: w for w in load(args.work / "works.json", [])}
    parse_text = load(args.work / "parse.json", {}).get("markdown", "")
    intro_md = (args.work / "intro.md").read_text(encoding="utf-8")
    related_md = (args.work / "related.md").read_text(encoding="utf-8")

    qa = vd.evaluate(claims, facts, works, parse_text, intro_md, related_md)
    (args.work / "qa_report.json").write_text(json.dumps(qa, ensure_ascii=False, indent=1),
                                              encoding="utf-8")

    rows = evidence_rows(claims, facts, works)
    shutil.copyfile(args.work / "intro.md", args.out / "intro.md")
    shutil.copyfile(args.work / "related.md", args.out / "related.md")
    (args.out / "evidence_map.md").write_text(render_map(rows), encoding="utf-8")

    cited_by_group = {}
    for group in claims.get("groups") or []:
        units = " ".join(u.get("text") or "" for u in claims.get("related") or []
                         if u.get("group") == group.get("name"))
        resolved, _ = vd.resolve_tokens([m.group(0) for m in vd.CITATION_RE.finditer(units)],
                                        list(works.values()))
        cited_by_group[group.get("name")] = sorted({item["key"] for item in resolved})
    # count every work the whole draft cites, not only the ones inside a group
    body_markers = [m.group(0) for m in vd.CITATION_RE.finditer(intro_md + "\n" + related_md)]
    body_resolved, _ = vd.resolve_tokens(body_markers, list(works.values()))
    all_cited = sorted({item["key"] for item in body_resolved})
    coverage = {
        "groups": cited_by_group,
        "cited_works": len(all_cited),
        "cited_keys": all_cited,
        "works_in_reference_list": len(works),
        "uncited_works": len(works) - len(all_cited),
        "judgement_units": qa.get("judgement_units"),
        "units": qa.get("units"),
    }
    (args.out / "coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=1),
                                            encoding="utf-8")

    ctx = {
        "intro": claims.get("intro"),
        "related": claims.get("related"),
        "contributions": claims.get("contributions"),
        "groups": claims.get("groups"),
        "evidence_map": rows,
        "coverage": coverage,
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

    status = qa.get("status", "failed")
    if pending:
        status = "partial" if status == "success" else status
    result = {
        "schema": "intro-draft/result/1.0",
        "case_id": case_id,
        "status": status,
        "task": {"excerpt": task.strip()[:500]},
        "output_contract": fields,
        "results": results,
        "pending_fields": pending,
        "paper": load(args.work / "paper.json", {}),
        "qa": qa,
        "coverage": coverage,
        "run": {"finished_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                "units": qa.get("units"), "groups": qa.get("groups"),
                "cited_works": qa.get("cited_works")},
    }
    (args.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    print("CASE_OK " + json.dumps({
        "case_id": case_id, "status": status, "units": qa.get("units"),
        "groups": qa.get("groups"), "cited_works": qa.get("cited_works"),
        "judgement_units": qa.get("judgement_units"),
        "hard_failures": qa.get("hard_failures"), "fields": len(results), "pending": pending,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
