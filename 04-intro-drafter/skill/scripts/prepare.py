#!/usr/bin/env python3
"""Build the fact base for drafting an introduction and related work.

Extracts three things from the paper, all anchored:

* ``facts.json``    quotable sentences: claim candidates with page/block/anchor
* ``works.json``    the cited works with their citation keys, fields and anchors
* ``outline.json``  the paper's own outline, so contributions can point at sections

The drafting step may only use these three files. Anything a draft says must be
traceable to a fact id, a work key, or be declared as author judgement.

Usage:
    python prepare.py PAPER.pdf --out WORK [--max-facts 60] [--parse-json PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pdf_evidence_parser import PdfEvidenceParser  # noqa: E402
import refs as refmod  # noqa: E402

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*(?:%|\u2030)?")
CITATION_RE = re.compile(r"\((?:[^()]*?\b(?:19|20)\d{2}[a-z]?[^()]*)\)")
YEAR_RE = re.compile(r"\b(19|20)\d{2}[a-z]?\b")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\u201c(])")
ABBREV = ("et al.", "e.g.", "i.e.", "fig.", "eq.", "sec.", "vs.", "cf.", "resp.", "app.")
CLAIM_WORDS = (
    "we introduce", "we propose", "we present", "we show", "we find", "we argue",
    "we demonstrate", "we use", "we report", "in this paper", "our", "contribution",
    "however", "limitation", "only", "require", "assume", "because", "improve",
    "outperform", "state-of-the-art", "unidirectional", "bidirectional",
)


def split_sentences(text: str) -> list[str]:
    protected = text
    for index, token in enumerate(ABBREV):
        protected = protected.replace(token, token.replace(".", f"\u2024{index}\u2024"))
    out = []
    for part in SENTENCE_RE.split(protected):
        restored = re.sub(r"\u2024\d+\u2024", ".", part).strip()
        if restored:
            out.append(restored)
    return out


def paper_metadata(parse: dict, pdf: Path) -> dict:
    title = None
    authors = None
    for sec in parse["sections"]:
        if sec["level"] == 1 and title is None and sec["title"] != "(front matter)":
            title = sec["title"].strip()
        for par in sec.get("paragraphs", []):
            if par.get("kind") == "byline" and authors is None:
                authors = par["text"].strip()
    raw = ""
    try:
        import pymupdf
        doc = pymupdf.open(pdf)
        raw = "\n".join(doc[i].get_text("text") for i in range(min(2, doc.page_count)))
        doc.close()
    except Exception:
        raw = parse.get("markdown", "")[:4000]
    arxiv = re.search(r"arXiv:\s*(\d{4}\.\d{4,5})(?:v(\d+))?", raw, re.I)
    year = None
    date = re.search(r"(\d{1,2})\s+([A-Z][a-z]{2})\s+((?:19|20)\d{2})", raw)
    if date:
        year = int(date.group(3))
    return {"title": title, "authors": authors, "year": year,
            "arxiv": arxiv.group(1) if arxiv else None,
            "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "pages": parse["source"]["pages"]}


def build_facts(parse: dict, limit: int) -> list[dict]:
    facts: list[dict] = []
    for sec in parse["sections"]:
        title = sec["title"].strip()
        if not title or title == "(front matter)" or title.lower().startswith("references"):
            continue
        for par in sec["paragraphs"]:
            if par.get("kind") not in ("paragraph", "caption"):
                continue
            ev = par.get("evidence") or {}
            anchor = ev.get("anchor")
            if not anchor:
                continue
            for order, sentence in enumerate(split_sentences(par.get("text") or "")):
                if len(sentence) < 45:
                    continue
                # every sentence is a potential evidence anchor for a draft; the
                # drafting step decides what it needs, so do not pre-filter by keyword
                facts.append({
                    "id": f"{anchor}:s{order}",
                    "anchor": anchor,
                    "page": ev.get("page"),
                    "block": ev.get("block"),
                    "section": title,
                    "text": sentence,
                    "numbers": NUMBER_RE.findall(sentence),
                    "cites": [m.group(0) for m in CITATION_RE.finditer(sentence)],
                })
                if len(facts) >= limit:
                    return facts
    return facts


def build_works(parse: dict) -> list[dict]:
    """Merge split entries and assign citation keys, then keep the cited-work view."""
    entries = parse.get("references", {}).get("entries") or []
    merged, _merges = refmod.merge_entries(entries)
    merged = refmod.assign_keys(merged)
    works = []
    for work in merged:
        works.append({
            "key": work["key"],
            "surname": work["surname"],
            "year": work["year"],
            "authors": work["authors"],
            "title": work["title"],
            "venue": work["venue"],
            "doi": work["doi"],
            "arxiv": work["arxiv"],
            "text": work["text"],
            "anchor": work["anchor"],
            "page": work["page"],
            "sources": work.get("sources", []),
        })
    return works


def build_outline(parse: dict) -> list[dict]:
    return [{"section": sec["title"], "level": sec["level"], "number": sec["number"],
             "page": sec.get("page"),
             "anchor": (sec.get("evidence") or [{}])[0].get("anchor"),
             "paragraphs": len(sec["paragraphs"])}
            for sec in parse["sections"]
            if sec["title"] and sec["title"] != "(front matter)"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-facts", type=int, default=60)
    ap.add_argument("--parse-json", type=Path, default=None)
    args = ap.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    if args.parse_json and args.parse_json.exists():
        parse = json.loads(args.parse_json.read_text(encoding="utf-8"))
    else:
        parse = PdfEvidenceParser(args.pdf).parse()
        (args.out / "parse.json").write_text(json.dumps(parse, ensure_ascii=False, indent=1),
                                            encoding="utf-8")

    facts = build_facts(parse, args.max_facts)
    works = build_works(parse)
    outline = build_outline(parse)
    meta = paper_metadata(parse, args.pdf)

    (args.out / "facts.json").write_text(json.dumps(facts, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    (args.out / "works.json").write_text(json.dumps(works, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    (args.out / "outline.json").write_text(json.dumps(outline, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    (args.out / "paper.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    summary = {"facts": len(facts), "works": len(works), "sections": len(outline),
               "pages": meta["pages"], "arxiv": meta["arxiv"]}
    (args.out / "prepare_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                                   encoding="utf-8")
    print("PREPARE_OK " + json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
