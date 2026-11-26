#!/usr/bin/env python3
"""Apply a translation case contract: prepare -> verify -> result.json.

Reads the case definition (`case.json`, `/input/case.json` at evaluation time) and
the task text, then writes `result.json` with every field the contract names:
the aligned bilingual segments, the glossary that was enforced, the QA report,
the evidence anchors, and an honest status.

Translations come from the agent (or a person): this script never fabricates a
target text. When `translations.jsonl` is missing it prepares the work and exits
with status `blocked_on_translation`, listing the batches to translate.

Usage:
    python run_case.py --case /input/case.json --task /input/task.md \
        --pdf /input/paper.pdf --work /app/work --out /app/output
    python run_case.py ... --translations work/translations.jsonl
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

import prepare  # noqa: E402
import verify  # noqa: E402

DEFAULT_FIELDS = ("bilingual", "glossary", "qa", "target_text", "evidence", "untranslated")

ALIASES = {
    "bilingual": ("bilingual", "aligned", "pairs", "双语", "对照"),
    "glossary": ("glossary", "terms", "术语"),
    "qa": ("qa", "quality", "checks", "核验"),
    "target_text": ("translation", "target_text", "chinese", "译文"),
    "evidence": ("evidence", "sources", "anchors", "来源"),
    "untranslated": ("untranslated", "unresolved", "未译"),
}


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def load(path: Path | None, default):
    if path is None or not path.exists():
        return default
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
    ap.add_argument("--translations", type=Path, default=None)
    ap.add_argument("--pages", default="")
    ap.add_argument("--sections", default="")
    ap.add_argument("--max-paragraphs", type=int, default=12)
    ap.add_argument("--glossary", type=Path, default=HERE.parent / "glossary" / "seed-ml-zh.csv")
    ap.add_argument("--case-id", default=None)
    args = ap.parse_args(argv)

    case = load(args.case, {})
    task_text = args.task.read_text(encoding="utf-8", errors="replace") if (
        args.task and args.task.exists()) else ""
    case_id = args.case_id or case.get("case_id") or case.get("id") or "unknown"
    args.work.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)

    pdf = args.pdf or next(iter(sorted(Path("/input").glob("*.pdf"))), None)
    if pdf is None or not Path(pdf).exists():
        result = {"case_id": case_id, "status": "failed",
                  "reason": "no input PDF", "uncertainty": [{"item": "input"}]}
        (args.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
        print("CASE_FAIL " + json.dumps({"reason": result["reason"]}, ensure_ascii=False))
        return 1

    if not (args.work / "segments.json").exists():
        cmd = [sys.executable, str(HERE / "prepare.py"), str(pdf), "--out", str(args.work),
               "--max-paragraphs", str(args.max_paragraphs),
               "--glossary", str(args.glossary)]
        if args.pages:
            cmd += ["--pages", args.pages]
        if args.sections:
            cmd += ["--sections", args.sections]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
        print(proc.stdout.strip() or proc.stderr.strip())

    segments = load(args.work / "segments.json", [])
    glossary = load(args.work / "glossary.json", [])
    translations_path = args.translations or (args.work / "translations.jsonl")
    translations = verify.load_jsonl(translations_path)

    if not translations:
        result = {
            "schema": "paper-translator/result/1.0",
            "case_id": case_id,
            "status": "blocked_on_translation",
            "task": task_text[:400],
            "segments": len(segments),
            "batches": sorted(p.name for p in (args.work / "batches").glob("batch-*.json")),
            "next": "translate each batches/*.json into translations.jsonl, then rerun",
            "glossary_locked": [g for g in glossary if g.get("locked")],
        }
        (args.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
        print("CASE_BLOCKED " + json.dumps({"segments": len(segments),
                                            "batches": len(result["batches"])}, ensure_ascii=False))
        return 2

    qa_path = args.work / "qa_report.json"
    proc = subprocess.run([sys.executable, str(HERE / "verify.py"), "--work", str(args.work),
                           "--translations", str(translations_path), "--out", str(qa_path)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    qa = load(qa_path, {"status": "failed", "checks": {}, "failures": []})

    by_id = {row.get("id"): row for row in translations}
    pairs = []
    for seg in segments:
        row = by_id.get(seg["id"], {})
        pairs.append({
            "id": seg["id"],
            "page": seg["page"],
            "block": seg["block"],
            "bbox": seg["bbox"],
            "section": seg["section"],
            "kind": seg["kind"],
            "source": seg["source_text"],
            "target": row.get("target", ""),
            "terms": row.get("terms", []),
            "notes": row.get("notes", ""),
        })
    bilingual_md = "\n\n".join(
        f"**[{p['id']}]** p.{p['page']} · {p['section']}\n\n> {p['source']}\n\n{p['target']}"
        for p in pairs)
    target_md = "\n\n".join(p["target"] for p in pairs if p["target"])
    (args.work / "bilingual.md").write_text(bilingual_md, encoding="utf-8")
    (args.work / "translation.md").write_text(target_md, encoding="utf-8")

    fields = contract_fields(case)
    if not fields:
        # No case.json supplied: use the skill's own output contract so a bare run
        # still produces a complete, checkable result instead of an empty one.
        fields = {name: name for name in DEFAULT_FIELDS}
    ctx = {
        "bilingual": pairs,
        "glossary": glossary,
        "qa": qa,
        "target_text": target_md,
        "evidence": [{"id": p["id"], "page": p["page"], "block": p["block"],
                      "bbox": p["bbox"], "section": p["section"]} for p in pairs],
        "untranslated": [p["id"] for p in pairs if not p["target"]],
    }
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
        "schema": "paper-translator/result/1.0",
        "case_id": case_id,
        "status": status,
        "task": {"excerpt": task_text.strip()[:600]},
        "document": {"pdf": str(pdf), "pages": sorted({p["page"] for p in pairs})},
        "output_contract": fields,
        "results": results,
        "pending_fields": pending,
        "qa": qa,
        "glossary": glossary,
        "evidence": ctx["evidence"],
        "untranslated": ctx["untranslated"],
        "uncertainty": qa.get("review_queue", []),
        "change_records": [{"change": "glossary_lock_enforced",
                            "terms": len([g for g in glossary if g.get("locked")])}],
        "run": {"finished_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                "segments": len(segments), "translated": len([p for p in pairs if p["target"]]),
                "bilingual_md": str(args.work / "bilingual.md")},
    }
    (args.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    (args.out / "bilingual.md").write_text(bilingual_md, encoding="utf-8")
    (args.out / "translation.md").write_text(target_md, encoding="utf-8")
    print("CASE_OK " + json.dumps({
        "case_id": case_id, "status": status, "segments": len(segments),
        "translated": result["run"]["translated"],
        "coverage": qa.get("coverage_rate"), "hard_failures": qa.get("hard_failures"),
        "fields_filled": len(results), "pending": pending,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
