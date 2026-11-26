#!/usr/bin/env python3
"""Prepare a paper for bilingual translation.

Turns a PDF into paragraph-level segments with stable ids and a term glossary
skeleton, then writes translation batches small enough to stay inside a model's
context budget. The translation itself is done by the agent (this script never
invents a target text); the script's job is to make the *source side* exact and
repeatable: paragraph ids that map 1:1 to the PDF, a glossary that later checks
can enforce, and batches that carry the locked terms every time.

Usage:
    python prepare.py PAPER.pdf --out WORK [--pages 1,2] [--sections Abstract,Introduction]
        [--max-paragraphs 12] [--batch 4] [--glossary submission/glossary/seed-ml-zh.csv]

Outputs under WORK:
    segments.json   ordered segments with id/page/block/bbox/section/text
    glossary.json   term table (seed + extracted candidates, zh filled only when known)
    batches/batch-001.json ... batches with the glossary subset each batch needs
    prompt.md       the exact instruction block for one batch
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pdf_evidence_parser import PdfEvidenceParser  # noqa: E402

ACRONYM_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,6}\b")
CAP_PHRASE_RE = re.compile(r"\b[A-Z][a-z]+(?:[ -][A-Z][a-z]+)+\b")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")

STOP_ACRONYMS = {"I", "II", "III", "A", "B", "C", "D", "E", "F", "GPU", "CPU", "URL", "PDF", "THE"}


def load_seed(path: Path | None) -> dict[str, dict]:
    seed: dict[str, dict] = {}
    if path is None or not path.exists():
        return seed
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            en = (row.get("en") or "").strip()
            if not en:
                continue
            seed[en.lower()] = {
                "en": en,
                "zh": (row.get("zh") or "").strip(),
                "note": (row.get("note") or "").strip(),
                "source": "seed",
            }
    return seed


def select_segments(parse: dict, pages: set[int] | None, sections: list[str] | None,
                    max_paragraphs: int | None, include_headings: bool = True) -> list[dict]:
    wanted_sections = [s.lower() for s in sections] if sections else None
    segments: list[dict] = []
    used_ids: set[str] = set()
    for sec in parse["sections"]:
        title = sec["title"].strip()
        if wanted_sections is not None:
            if not any(title.lower().startswith(w) or w in title.lower() for w in wanted_sections):
                continue
        heading_ev = (sec.get("evidence") or [{}])[0]
        heading_page = heading_ev.get("page")
        if (include_headings and title and title != "(front matter)" and len(title) >= 6
                and (not pages or heading_page in pages)):
            heading_id = heading_ev.get("anchor") or f"h-{sec['id']}"
            if heading_id not in used_ids:
                used_ids.add(heading_id)
                segments.append({
                    "id": heading_id,
                    "page": heading_page,
                    "block": heading_ev.get("block"),
                    "bbox": heading_ev.get("bbox"),
                    "section": title,
                    "section_level": sec["level"],
                    "kind": "heading",
                    "source_text": title,
                    "chars": len(title),
                })
        for par in sec["paragraphs"]:
            ev = par.get("evidence") or {}
            page = ev.get("page")
            if pages and page not in pages:
                continue
            text = (par.get("text") or "").strip()
            if len(text) < 20:
                continue
            sid = ev.get("anchor") or f"{sec['id']}-{par['id']}"
            if sid in used_ids:
                continue
            used_ids.add(sid)
            segments.append({
                "id": sid,
                "page": page,
                "block": ev.get("block"),
                "bbox": ev.get("bbox"),
                "section": title,
                "section_level": sec["level"],
                "kind": par.get("kind"),
                "source_text": text,
                "chars": len(text),
            })
    if max_paragraphs:
        segments = segments[:max_paragraphs]
    for order, seg in enumerate(segments, start=1):
        seg["order"] = order
    return segments


def extract_terms(segments: list[dict], seed: dict[str, dict], min_count: int = 2) -> list[dict]:
    counts: dict[str, dict] = {}
    for seg in segments:
        text = seg["source_text"]
        for match in ACRONYM_RE.finditer(text):
            term = match.group(0)
            if term in STOP_ACRONYMS or len(term) < 2:
                continue
            entry = counts.setdefault(term.lower(), {"en": term, "count": 0, "pages": set()})
            entry["count"] += 1
            entry["pages"].add(seg["page"])
        for match in CAP_PHRASE_RE.finditer(text):
            term = match.group(0)
            if len(term.split()) > 4:
                continue
            entry = counts.setdefault(term.lower(), {"en": term, "count": 0, "pages": set()})
            entry["count"] += 1
            entry["pages"].add(seg["page"])

    glossary: list[dict] = []
    seen: set[str] = set()
    for key, info in sorted(counts.items(), key=lambda kv: -kv[1]["count"]):
        if info["count"] < min_count and key not in seed:
            continue
        entry = {
            "en": info["en"],
            "zh": seed.get(key, {}).get("zh", ""),
            "note": seed.get(key, {}).get("note", ""),
            "count": info["count"],
            "pages": sorted(info["pages"]),
            "source": "seed" if key in seed else "extracted",
            "locked": bool(seed.get(key, {}).get("zh")),
        }
        glossary.append(entry)
        seen.add(key)
    for key, seed_entry in seed.items():
        if key in seen:
            continue
        if any(key in seg["source_text"].lower() for seg in segments):
            glossary.append({
                "en": seed_entry["en"], "zh": seed_entry["zh"], "note": seed_entry["note"],
                "count": sum(seg["source_text"].lower().count(key) for seg in segments),
                "pages": sorted({seg["page"] for seg in segments}),
                "source": "seed", "locked": bool(seed_entry["zh"]),
            })
    glossary.sort(key=lambda g: (-int(g["locked"]), -g["count"]))
    return glossary


def terms_in_text(text: str, glossary: list[dict]) -> list[dict]:
    lowered = text.lower()
    hits = []
    for entry in glossary:
        pattern = r"(?<![a-z])" + re.escape(entry["en"].lower()) + r"(?![a-z])"
        if re.search(pattern, lowered):
            hits.append({"en": entry["en"], "zh": entry["zh"], "locked": entry["locked"]})
    return hits


def build_batches(segments: list[dict], glossary: list[dict], size: int) -> list[list[dict]]:
    batches = []
    for start in range(0, len(segments), size):
        chunk = segments[start:start + size]
        locked = [g for g in glossary if g["locked"] and any(
            g["en"].lower() in seg["source_text"].lower() for seg in chunk)]
        batches.append({"batch": len(batches) + 1, "segments": chunk,
                        "locked_terms": locked})
    return batches


PROMPT = """Translate every segment below from English into Simplified Chinese.

Rules, in priority order:
1. Each segment id is a paragraph in the source paper. Return exactly one object
   per id, in the same order, and never merge, split, drop or reorder segments.
2. A locked term must be translated exactly as its `zh` value wherever it occurs.
   If a locked term is wrong for this context, say so in `notes` and still use it.
3. Preserve verbatim: citation markers ([12], (Devlin et al., 2019)), numbers and
   units, section numbers, formula tokens, and figure/table labels.
4. Keep negation, quantifiers and hedges: "not", "no", "only", "may", "can",
   "without" must survive as 不/无/仅/可能/可/未, not disappear.
5. Chinese academic register; no added explanation, no omitted clauses.
6. If a sentence cannot be translated with the information present, translate what
   is there and add a `notes` entry naming what is missing. Never guess.

Return JSONL, one line per segment:
{"id": "<id>", "target": "<Chinese translation>", "terms": ["locked terms used"], "notes": ""}
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pages", default="")
    ap.add_argument("--sections", default="")
    ap.add_argument("--max-paragraphs", type=int, default=None)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--glossary", type=Path, default=None)
    ap.add_argument("--parse-json", type=Path, default=None, help="reuse an existing parse.json")
    args = ap.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    if args.parse_json and args.parse_json.exists():
        parse = json.loads(args.parse_json.read_text(encoding="utf-8"))
    else:
        parse = PdfEvidenceParser(args.pdf).parse()
        (args.out / "parse.json").write_text(json.dumps(parse, ensure_ascii=False, indent=1),
                                            encoding="utf-8")

    pages = {int(p) for p in args.pages.split(",") if p.strip()} or None
    sections = [s for s in args.sections.split(",") if s.strip()] or None
    segments = select_segments(parse, pages, sections, args.max_paragraphs)
    seed = load_seed(args.glossary)
    glossary = extract_terms(segments, seed)
    batches = build_batches(segments, glossary, args.batch)

    (args.out / "segments.json").write_text(json.dumps(segments, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    (args.out / "glossary.json").write_text(json.dumps(glossary, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    batch_dir = args.out / "batches"
    batch_dir.mkdir(exist_ok=True)
    for batch in batches:
        name = f"batch-{batch['batch']:03d}.json"
        payload = {
            "batch": batch["batch"],
            "instructions": PROMPT,
            "locked_terms": batch["locked_terms"],
            "segments": [{"id": s["id"], "page": s["page"], "section": s["section"],
                          "text": s["source_text"]} for s in batch["segments"]],
        }
        (batch_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    (args.out / "prompt.md").write_text(PROMPT, encoding="utf-8")

    stats = {
        "segments": len(segments),
        "source_chars": sum(s["chars"] for s in segments),
        "pages": sorted({s["page"] for s in segments}),
        "sections": sorted({s["section"] for s in segments}),
        "glossary_terms": len(glossary),
        "locked_terms": sum(1 for g in glossary if g["locked"]),
        "batches": len(batches),
    }
    (args.out / "prepare_summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1),
                                                  encoding="utf-8")
    print("PREPARE_OK " + json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
