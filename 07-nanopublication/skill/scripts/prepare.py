#!/usr/bin/env python3
"""Prepare a paper for claim-to-nanopublication extraction.

Produces the paper's own outline, its quotable candidate sentences (each with a
resolvable anchor) and the source metadata a nanopublication needs for provenance.

Usage:
    python prepare.py PAPER.pdf --out WORK [--max-sentences 8] [--parse-json PATH]

Outputs:
    candidates.json  quotable sentences: id, anchor, page, block, section, text
    segments.json    the paper outline the assertions must map onto
    paper.json       source metadata: title, authors, year, identifiers, hash
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

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*(?:%|\u2030)?")
CITATION_RE = re.compile(r"\[\s*\d+(?:\s*[,;\u2013-]\s*\d+)*\s*\]")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\u201c(])")
ABBREV = ("et al.", "e.g.", "i.e.", "fig.", "eq.", "sec.", "vs.", "cf.", "resp.", "app.")
KEYWORDS = (
    "we propose", "we show", "we find", "we argue", "we introduce", "we use",
    "we report", "limitation", "however", "only", "require", "assume", "because",
    "result", "accuracy", "error", "dataset", "training", "outperform", "improve",
    "state-of-the-art", "in this paper",
)
ARXIV_RE = re.compile(r"arXiv:\s*(\d{4}\.\d{4,5})(?:v(\d+))?", re.I)
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")


def split_sentences(text: str) -> list[str]:
    protected = text
    for i, token in enumerate(ABBREV):
        protected = protected.replace(token, token.replace(".", f"\u2024{i}\u2024"))
    out = []
    for part in SENTENCE_RE.split(protected):
        restored = re.sub(r"\u2024\d+\u2024", ".", part).strip()
        if restored:
            out.append(restored)
    return out


def features(sentence: str) -> dict:
    lowered = sentence.lower()
    return {
        "numbers": NUMBER_RE.findall(sentence),
        "citations": [m.group(0) for m in CITATION_RE.finditer(sentence)],
        "keywords": [k for k in KEYWORDS if k in lowered],
    }


def paper_metadata(parse: dict, pdf: Path, full_text: str) -> dict:
    title = None
    authors = None
    year = None
    for sec in parse["sections"]:
        if sec["level"] == 1 and title is None and sec["title"] and sec["title"] != "(front matter)":
            title = sec["title"].strip()
        for par in sec.get("paragraphs", []):
            if par.get("kind") == "byline" and authors is None:
                authors = par["text"].strip()
    # The arXiv stamp lives in a rotated margin block that the parser strips from
    # the body, so read the raw page text for identifiers and the deposit date.
    raw_head = ""
    try:
        import pymupdf
        doc = pymupdf.open(pdf)
        raw_head = "\n".join(doc[i].get_text("text") for i in range(min(2, doc.page_count)))
        doc.close()
    except Exception:
        raw_head = full_text[:6000]
    arxiv = ARXIV_RE.search(raw_head)
    doi = DOI_RE.search(raw_head)
    date = re.search(r"(\d{1,2})\s+([A-Z][a-z]{2})\s+((?:19|20)\d{2})", raw_head)
    if date:
        year = int(date.group(3))
    if year is None:
        for sec in parse["sections"]:
            for par in sec.get("paragraphs", []):
                match = re.search(r"\b(19|20)\d{2}\b", par.get("text", ""))
                if match:
                    year = int(match.group(0))
                    break
            if year:
                break
    identifiers = {}
    if doi:
        identifiers["doi"] = doi.group(0)
    if arxiv:
        identifiers["arxiv"] = arxiv.group(1)
        identifiers["arxiv_version"] = arxiv.group(2) or "1"
    return {
        "title": title,
        "authors": authors,
        "year": year,
        "identifiers": identifiers,
        "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "bytes": pdf.stat().st_size,
        "pages": parse["source"]["pages"],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-sentences", type=int, default=8)
    ap.add_argument("--parse-json", type=Path, default=None)
    args = ap.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    if args.parse_json and args.parse_json.exists():
        parse = json.loads(args.parse_json.read_text(encoding="utf-8"))
    else:
        parse = PdfEvidenceParser(args.pdf).parse()
        (args.out / "parse.json").write_text(json.dumps(parse, ensure_ascii=False, indent=1),
                                            encoding="utf-8")

    candidates: list[dict] = []
    segments: list[dict] = []
    for sec in parse["sections"]:
        title = sec["title"].strip()
        if not title or title == "(front matter)":
            continue
        count = 0
        ids: list[str] = []
        for par in sec["paragraphs"]:
            if par.get("kind") not in ("paragraph", "caption"):
                continue
            ev = par.get("evidence") or {}
            anchor = ev.get("anchor")
            if not anchor:
                continue
            for order, sentence in enumerate(split_sentences(par["text"])):
                if len(sentence) < 40 or count >= args.max_sentences:
                    continue
                feats = features(sentence)
                if not (feats["numbers"] or feats["citations"] or feats["keywords"]):
                    continue
                cid = f"{anchor}:s{order}"
                candidates.append({
                    "id": cid, "anchor": anchor, "page": ev.get("page"),
                    "block": ev.get("block"), "bone": ev.get("bbox"),
                    "section": title, "text": sentence,
                    "numbers": feats["numbers"], "citations": feats["citations"],
                })
                ids.append(cid)
                count += 1
        segments.append({"section": title, "level": sec["level"], "number": sec["number"],
                         "page": sec.get("page"), "paragraphs": len(sec["paragraphs"]),
                         "candidate_ids": ids})

    meta = paper_metadata(parse, args.pdf, parse.get("markdown", ""))
    (args.out / "candidates.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    (args.out / "segments.json").write_text(json.dumps(segments, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    (args.out / "paper.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    summary = {"sections": len(segments), "candidates": len(candidates),
               "pages": meta["pages"], "identifiers": meta["identifiers"],
               "sections_with_candidates": sum(1 for s in segments if s["candidate_ids"])}
    (args.out / "prepare_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                                   encoding="utf-8")
    print("PREPARE_OK " + json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
