#!/usr/bin/env python3
"""Extract a note skeleton and quotable candidates from a paper.

The skeleton is the paper's own section tree with anchors; the candidates are the
sentences a note is allowed to quote, each carrying the exact anchor it came from.
Notes are then written *against candidate ids*, so a quote cannot drift from the
source by accident — the verifier compares it with the source again anyway.

Usage:
    python prepare.py PAPER.pdf --out WORK [--max-sentences 12] [--parse-json PATH]

Outputs:
    segments.json    section tree with page, level, paragraph and anchor counts
    candidates.json  quotable sentences: id, anchor, page, section, text, features
    prepare_summary.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pdf_evidence_parser import PdfEvidenceParser  # noqa: E402

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*(?:%|\u2030)?")
CITATION_RE = re.compile(r"\[\s*\d+(?:\s*[,;\u2013-]\s*\d+)*\s*\]|\([A-Z][A-Za-z.\-']+"
                         r"(?:\s+(?:et al\.|and|&)\s*[A-Za-z.\-']*)?,?\s*\d{4}[a-z]?\)")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\u201c(])")
KEYWORDS = (
    "we propose", "we show", "we find", "we argue", "we introduce", "we use",
    "in this paper", "limitation", "however", "only", "require", "assume",
    "because", "in contrast", "result", "accuracy", "error", "dataset",
    "training", "state-of-the-art", "outperform", "improve",
)
ABBREV = ("et al.", "e.g.", "i.e.", "fig.", "eq.", "sec.", "vs.", "cf.", "resp.")


def split_sentences(text: str) -> list[str]:
    protected = text
    for i, token in enumerate(ABBREV):
        protected = protected.replace(token, token.replace(".", f"\u2024{i}\u2024"))
    parts = SENTENCE_RE.split(protected)
    out = []
    for part in parts:
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-sentences", type=int, default=12)
    ap.add_argument("--parse-json", type=Path, default=None)
    args = ap.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    if args.parse_json and args.parse_json.exists():
        parse = json.loads(args.parse_json.read_text(encoding="utf-8"))
    else:
        parse = PdfEvidenceParser(args.pdf).parse()
        (args.out / "parse.json").write_text(json.dumps(parse, ensure_ascii=False, indent=1),
                                            encoding="utf-8")

    segments: list[dict] = []
    candidates: list[dict] = []
    for sec in parse["sections"]:
        title = sec["title"].strip()
        if not title or title == "(front matter)":
            continue
        heading_ev = (sec.get("evidence") or [{}])[0]
        sentences_here = 0
        seg_ids = []
        for par in sec["paragraphs"]:
            if par.get("kind") not in ("paragraph", "caption", "footnote"):
                continue
            ev = par.get("evidence") or {}
            anchor = ev.get("anchor")
            if not anchor:
                continue
            for order, sentence in enumerate(split_sentences(par["text"])):
                if len(sentence) < 30:
                    continue
                feats = features(sentence)
                if not (feats["numbers"] or feats["citations"] or feats["keywords"]):
                    continue
                if sentences_here >= args.max_sentences:
                    break
                cid = f"{anchor}:s{order}"
                candidates.append({
                    "id": cid,
                    "anchor": anchor,
                    "page": ev.get("page"),
                    "block": ev.get("block"),
                    "section": title,
                    "text": sentence,
                    "features": feats,
                })
                seg_ids.append(cid)
                sentences_here += 1
        segments.append({
            "section": title,
            "level": sec["level"],
            "number": sec["number"],
            "page": sec.get("page"),
            "heading_anchor": heading_ev.get("anchor"),
            "paragraphs": len(sec["paragraphs"]),
            "candidate_ids": seg_ids,
        })

    (args.out / "segments.json").write_text(json.dumps(segments, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    (args.out / "candidates.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    summary = {
        "sections": len(segments),
        "candidates": len(candidates),
        "pages": parse["source"]["pages"],
        "tables": len(parse["tables"]),
        "figures": len(parse["figures"]),
        "references": parse["references"]["count"],
        "sections_with_candidates": sum(1 for s in segments if s["candidate_ids"]),
    }
    (args.out / "prepare_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                                   encoding="utf-8")
    print("PREPARE_OK " + json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
