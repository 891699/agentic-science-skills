#!/usr/bin/env python3
"""Apply a case contract to a parsed PDF.

Reads the case definition (`case.json`) and the task text (`task.md`), runs the
parser when needed, and writes `result.json` with every field the case's
`output_contract` names.  Structural fields are filled from the parse; fields
that require judgement (an answer, a translation, a comparison) are left for the
agent and listed under `pending_fields`, or supplied with `--answers`.

Usage:
    python run_case.py --case /input/case.json --task /input/task.md \
        --pdf /input/paper.pdf --work /app/work --out /app/output
    python run_case.py ... --answers answers.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pdf_evidence_parser import PdfEvidenceParser  # noqa: E402

CONTRACT_ALIASES = {
    "text": ("full_text", "text", "document_text", "content", "markdown", "body", "fulltext"),
    "sections": ("sections", "outline", "structure", "headings", "section_tree", "hierarchy"),
    "tables": ("tables", "table_list", "table_data"),
    "figures": ("figures", "figure_list", "images", "captions"),
    "formulas": ("formulas", "equations", "math", "math_blocks"),
    "references": ("references", "bibliography", "refs", "reference_list"),
    "meta": ("metadata", "meta", "title", "authors", "abstract", "front_matter", "byline"),
    "evidence": ("evidence", "sources", "anchors", "provenance", "page_map", "citations"),
    "stats": ("stats", "statistics", "coverage", "quality"),
    "status": ("status", "run_status", "outcome"),
}


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def load_json(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {"_value": data}
    except Exception:
        return {}


def find_pdf(case: dict, explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit)
    for key in ("pdf", "pdf_path", "paper", "document", "input", "file", "main_file"):
        value = case.get(key)
        if isinstance(value, str) and value.lower().endswith(".pdf"):
            return Path(value)
    for key in ("files", "materials", "inputs", "documents"):
        value = case.get(key)
        if isinstance(value, list):
            for item in value:
                path = item if isinstance(item, str) else (item or {}).get("path")
                if isinstance(path, str) and path.lower().endswith(".pdf"):
                    return Path(path)
    for base in (Path("/input"), Path(".")):
        if base.exists():
            hits = sorted(base.glob("*.pdf"))
            if hits:
                return hits[0]
    return None


def contract_fields(case: dict) -> dict[str, str]:
    """Return {field_name: description} from the case's output contract."""
    contract = case.get("output_contract") or case.get("outputs") or case.get("deliverables")
    fields: dict[str, str] = {}
    if isinstance(contract, dict):
        fields.update({k: str(v) for k, v in contract.items() if not str(k).startswith("_")})
        for key in ("fields", "properties", "required"):
            value = contract.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        fields.setdefault(item, "")
                    elif isinstance(item, dict) and "name" in item:
                        fields.setdefault(item["name"], str(item.get("description", "")))
            elif isinstance(value, dict):
                for k, v in value.items():
                    fields.setdefault(k, str(v))
    elif isinstance(contract, list):
        for item in contract:
            if isinstance(item, str):
                fields[item] = ""
            elif isinstance(item, dict) and "name" in item:
                fields[item["name"]] = str(item.get("description", ""))
    for item in case.get("questions") or []:
        if isinstance(item, dict):
            name = item.get("id") or item.get("name")
            if name:
                fields.setdefault(f"answer_{name}", str(item.get("text", "")))
        elif isinstance(item, str):
            fields.setdefault(f"answer_{norm(item)[:24]}", item)
    return fields


def build_metadata(parse: dict) -> dict:
    title = None
    authors = None
    abstract = None
    for sec in parse["sections"]:
        if sec["level"] != 0 and title is None and sec["title"] and sec["title"] != "(front matter)":
            title = sec["title"]
        for par in sec["paragraphs"]:
            if par["kind"] == "byline" and authors is None:
                authors = par["text"]
            if sec["title"].lower().strip() == "abstract" and abstract is None:
                abstract = par["text"]
    return {"title": title, "authors": authors, "abstract": abstract,
            "pages": parse["source"]["pages"], "sha256": parse["source"]["sha256"]}


def section_evidence(parse: dict) -> list[dict]:
    seen = set()
    out = []
    for sec in parse["sections"]:
        for ev in sec["evidence"]:
            key = ev["anchor"]
            if key in seen:
                continue
            seen.add(key)
            out.append({"anchor": ev["anchor"], "page": ev["page"], "block": ev.get("block"),
                        "bbox": ev.get("bbox"), "section": sec["title"]})
    for table in parse["tables"]:
        out.append({"anchor": table["evidence"]["anchor"], "page": table["page"],
                    "bbox": table["evidence"]["bbox"], "table": table["id"]})
    for figure in parse["figures"]:
        out.append({"anchor": figure["evidence"]["anchor"], "page": figure["page"],
                    "bbox": figure["evidence"]["bbox"], "figure": figure["id"]})
    return out


def fill_field(name: str, parse: dict, meta: dict, pdf_text: str) -> tuple[bool, object]:
    key = norm(name)
    for family, aliases in CONTRACT_ALIASES.items():
        if key in aliases or key.startswith(family):
            if family == "text":
                return True, pdf_text
            if family == "sections":
                return True, [{"id": s["id"], "title": s["title"], "level": s["level"],
                               "number": s["number"], "page": s["page"],
                               "paragraphs": len(s["paragraphs"]),
                               "evidence": s["evidence"][:1]} for s in parse["sections"]]
            if family == "tables":
                return True, [{"id": t["id"], "page": t["page"], "rows": t["rows"],
                               "cols": t["cols"], "grid": t["grid"], "markdown": t["markdown"],
                               "evidence": t["evidence"]} for t in parse["tables"]]
            if family == "figures":
                return True, parse["figures"]
            if family == "formulas":
                return True, parse["formulas"]
            if family == "references":
                return True, parse["references"]
            if family == "meta":
                return True, meta
            if family == "evidence":
                return True, section_evidence(parse)
            if family == "stats":
                return True, parse["stats"]
            if family == "status":
                return True, "ok"
    if key.endswith("count"):
        base = key[:-5]
        for family, aliases in CONTRACT_ALIASES.items():
            if base in aliases or aliases and base.startswith(family):
                value = fill_field(family if family != "meta" else "meta", parse, meta, pdf_text)[1]
                if family == "references":
                    return True, parse["references"]["count"]
                if isinstance(value, list):
                    return True, len(value)
    # A field named after a section of the document is answered by that section.
    for sec in parse["sections"]:
        if norm(sec["title"]).startswith(key) and len(key) >= 4:
            return True, {"section": sec["title"], "page": sec["page"],
                          "text": "\n\n".join(p["text"] for p in sec["paragraphs"]),
                          "evidence": sec["evidence"]}
    return False, None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Apply a case contract to a parsed PDF")
    ap.add_argument("--case", type=Path, default=None)
    ap.add_argument("--task", type=Path, default=None)
    ap.add_argument("--pdf", type=Path, default=None)
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--out", type=Path, default=Path("output"))
    ap.add_argument("--answers", type=Path, default=None)
    ap.add_argument("--case-id", default=None)
    args = ap.parse_args(argv)

    case = load_json(args.case) if args.case and args.case.exists() else {}
    task_text = args.task.read_text(encoding="utf-8", errors="replace") if (
        args.task and args.task.exists()) else ""

    pdf = find_pdf(case, str(args.pdf) if args.pdf else None)
    args.work.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)

    if pdf is None or not Path(pdf).exists():
        result = {
            "case_id": args.case_id or case.get("case_id") or case.get("id") or "unknown",
            "status": "failed",
            "reason": "no input PDF found next to case.json",
            "uncertainty": [{"item": "input", "detail": "case declares no readable PDF path"}],
        }
        (args.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
        print("CASE_FAIL " + json.dumps({"reason": result["reason"]}, ensure_ascii=False))
        return 1

    parse_path = args.work / "parse.json"
    if parse_path.exists():
        parse = load_json(parse_path)
    else:
        parser = PdfEvidenceParser(Path(pdf))
        parse = parser.parse()
        parse_path.write_text(json.dumps(parse, ensure_ascii=False, indent=1), encoding="utf-8")
    (args.work / "document.md").write_text(parse.get("markdown", ""), encoding="utf-8")
    pdf_text = parse.get("markdown", "")
    meta = build_metadata(parse)

    fields = contract_fields(case)
    answers = load_json(args.answers) if args.answers and args.answers.exists() else {}
    filled: dict[str, object] = {}
    pending: list[str] = []
    for name in fields:
        if name in answers:
            filled[name] = answers[name]
            continue
        ok, value = fill_field(name, parse, meta, pdf_text)
        if ok:
            filled[name] = value
        else:
            pending.append(name)

    unreadable = [p["page"] for p in parse.get("unreadable_pages", [])]
    coverage = parse.get("stats", {}).get("char_coverage", 1.0)
    if not pdf_text.strip():
        status = "failed"
    elif unreadable or (isinstance(coverage, (int, float)) and coverage < 0.98):
        status = "partial"
    else:
        status = "success"

    uncertainty = list(parse.get("uncertainty", []))
    if unreadable:
        uncertainty.append({"item": "text_layer",
                            "detail": f"pages without a usable text layer: {unreadable}"})
    for name in pending:
        uncertainty.append({
            "item": f"field:{name}",
            "detail": "requires reading and judgement; the structural parse cannot fill it automatically",
        })

    result = {
        "schema": "pdf-evidence-reader/case-result/1.0",
        "case_id": args.case_id or case.get("case_id") or case.get("id") or Path(pdf).stem,
        "status": status,
        "task": {"source": str(args.task) if args.task else None,
                 "excerpt": task_text.strip()[:600]},
        "document": meta,
        "output_contract": fields,
        "results": filled,
        "pending_fields": pending,
        "evidence": section_evidence(parse),
        "uncertainty": uncertainty,
        "limits": parse.get("limits", []),
        "change_records": parse.get("change_records", []),
        "stats": parse.get("stats", {}),
        "run": {
            "parsed_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "parser": parse.get("source", {}).get("parser"),
            "pdf": str(pdf),
            "parse_json": str(parse_path),
            "document_md": str(args.work / "document.md"),
            "filled_fields": sorted(filled),
            "pending_fields": pending,
        },
    }
    (args.out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                          encoding="utf-8")

    lines = [
        f"# {meta.get('title') or Path(pdf).name}",
        "",
        f"- case_id: `{result['case_id']}`  status: **{status}**",
        f"- pages: {meta.get('pages')}  sections: {len(parse['sections'])}  "
        f"tables: {len(parse['tables'])}  figures: {len(parse['figures'])}  "
        f"references: {parse['references']['count']}",
        f"- char coverage: {coverage}  unreadable pages: {unreadable or 'none'}",
        f"- contract fields filled: {len(filled)}/{len(fields)}",
    ]
    if pending:
        lines.append(f"- pending: {', '.join(pending)}")
    (args.out / "result.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("CASE_OK " + json.dumps({
        "case_id": result["case_id"],
        "status": status,
        "pages": meta.get("pages"),
        "sections": len(parse["sections"]),
        "tables": len(parse["tables"]),
        "figures": len(parse["figures"]),
        "references": parse["references"]["count"],
        "char_coverage": coverage,
        "filled": len(filled),
        "contract_fields": len(fields),
        "pending": pending,
        "out": str(args.out / "result.json"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
