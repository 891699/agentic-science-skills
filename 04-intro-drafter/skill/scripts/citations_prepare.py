#!/usr/bin/env python3
"""Prepare a paper for a reference/citation audit.

Extracts the reference list entries and every in-text citation with its anchor, so
the audit can compare the two lists instead of trusting a bibliography export.

Usage:
    python prepare.py PAPER.pdf --out WORK [--parse-json PATH]

Outputs:
    refs.json       reference entries: id, text, page, anchor
    citations.json  in-text citations: marker, page, anchor, section, sentence
    paper.json      title, authors, year, identifiers, sha256, pages
    prepare_summary.json
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

CITATION_RE = re.compile(r"\((?:[^()]*?\b(?:19|20)\d{2}[a-z]?[^()]*)\)")
BRACKET_RE = re.compile(r"\[(\d+(?:\s*[,;\u2013-]\s*\d+)*)\]")
ARXIV_RE = re.compile(r"arXiv:\s*(\d{4}\.\d{4,5})(?:v(\d+))?", re.I)
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")


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
    arxiv = ARXIV_RE.search(raw)
    doi = DOI_RE.search(raw)
    year = None
    date = re.search(r"(\d{1,2})\s+([A-Z][a-z]{2})\s+((?:19|20)\d{2})", raw)
    if date:
        year = int(date.group(3))
    identifiers = {}
    if arxiv:
        identifiers["arxiv"] = arxiv.group(1)
    if doi:
        identifiers["doi"] = doi.group(0)
    return {"title": title, "authors": authors, "year": year, "identifiers": identifiers,
            "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "pages": parse["source"]["pages"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--parse-json", type=Path, default=None)
    args = ap.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    if args.parse_json and args.parse_json.exists():
        parse = json.loads(args.parse_json.read_text(encoding="utf-8"))
    else:
        parse = PdfEvidenceParser(args.pdf).parse()
        (args.out / "parse.json").write_text(json.dumps(parse, ensure_ascii=False, indent=1),
                                            encoding="utf-8")

    refs = []
    for index, entry in enumerate(parse.get("references", {}).get("entries") or [], start=1):
        ev = entry.get("evidence") or {}
        refs.append({"id": f"ref-{index:03d}", "index": index, "text": entry["text"],
                     "page": ev.get("page"), "anchor": ev.get("anchor")})

    citations = []
    for sec in parse["sections"]:
        for par in sec["paragraphs"]:
            if par.get("kind") not in ("paragraph", "caption"):
                continue
            ev = par.get("evidence") or {}
            text = par.get("text") or ""
            for match in CITATION_RE.finditer(text):
                inner = match.group(0)[1:-1]
                citations.append({"marker": match.group(0), "inner": inner,
                                  "kind": "author-year", "page": ev.get("page"),
                                  "anchor": ev.get("anchor"), "section": sec["title"]})
            for match in BRACKET_RE.finditer(text):
                for number in re.findall(r"\d+", match.group(1)):
                    citations.append({"marker": match.group(0), "inner": number,
                                      "kind": "numeric", "page": ev.get("page"),
                                      "anchor": ev.get("anchor"), "section": sec["title"]})

    meta = paper_metadata(parse, args.pdf)
    (args.out / "refs.json").write_text(json.dumps(refs, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    (args.out / "citations.json").write_text(json.dumps(citations, ensure_ascii=False, indent=1),
                                             encoding="utf-8")
    (args.out / "paper.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    styles = sorted({c["kind"] for c in citations})
    summary = {"references": len(refs), "citations": len(citations),
               "citation_styles": styles, "pages": meta["pages"],
               "identifiers": meta["identifiers"],
               "reference_pages": sorted({r["page"] for r in refs if r["page"]})}
    (args.out / "prepare_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                                   encoding="utf-8")
    print("PREPARE_OK " + json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
