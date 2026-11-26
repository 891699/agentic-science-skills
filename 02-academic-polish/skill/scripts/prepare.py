#!/usr/bin/env python3
"""Prepare a paper for academic language polishing.

Produces paragraph-level segments with stable ids plus the facts a polish must not
break: numeric values, citation markers, protected terms (acronyms and model
names), hedging/negation markers, and a style baseline for the before/after report.

Usage:
    python prepare.py PAPER.pdf --out WORK [--max-paragraphs 8] [--parse-json PATH]

Outputs:
    segments.json   paragraph segments: id, page, block, section, text, facts
    terms.json      protected terms with their first occurrence
    style.json      per-segment and aggregate style baseline
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

NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)*(?:%|\u2030)?")
CITATION_RE = re.compile(r"\[\s*\d+(?:\s*[,;\u2013-]\s*\d+)*\s*\]|\("
                         r"[A-Z][A-Za-z.\-']+(?:\s+(?:et al\.|and|&)\s*[A-Za-z.\-']*)?,?\s*\d{4}[a-z]?\)")
ACRONYM_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,6}\b")
MODEL_RE = re.compile(r"\b(?:BERT|GPT|ELMo|GLUE|MultiNLI|SQuAD|SWAG|CoLA|MNLI|QQP|QNLI|RTE|MRPC|SST-2|STS-B)\b")
HEDGES = ("may", "might", "can", "could", "should", "likely", "suggest", "indicate",
          "appear", "seem", "often", "typically", "generally")
NEGATIONS = ("not", "no", "never", "none", "without", "cannot", "n't", "neither", "nor")
WEASELS = ("very", "quite", "really", "a lot of", "lots of", "obviously", "clearly",
           "of course", "basically", "actually")
CONTRACTIONS = ("n't", "'re", "'ve", "'ll", "'d", "it's", "don't", "doesn't", "can't")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\u201c(])")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_RE.split(text) if s.strip()]


def facts(text: str) -> dict:
    lowered = text.lower()
    sents = sentences(text)
    words = re.findall(r"[A-Za-z']+", text)
    return {
        "numbers": sorted({m.group(0).replace(",", "") for m in NUMBER_RE.finditer(text)}),
        "citations": sorted({m.group(0) for m in CITATION_RE.finditer(text)}),
        "acronyms": sorted({m.group(0) for m in ACRONYM_RE.finditer(text)}),
        "models": sorted({m.group(0) for m in MODEL_RE.finditer(text)}),
        "hedges": [h for h in HEDGES if re.search(rf"\b{h}\b", lowered)],
        "negations": [n for n in NEGATIONS if re.search(rf"\b{re.escape(n)}\b", lowered)],
        "weasels": [w for w in WEASELS if w in lowered],
        "contractions": [c for c in CONTRACTIONS if c in lowered],
        "sentences": len(sents),
        "words": len(words),
        "avg_sentence_words": round(len(words) / max(1, len(sents)), 2),
        "passive_hits": len(re.findall(r"\b(?:is|are|was|were|be|been|being)\s+\w+ed\b", lowered)),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-paragraphs", type=int, default=8)
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
    for sec in parse["sections"]:
        title = sec["title"].strip()
        if not title or title == "(front matter)":
            continue
        for par in sec["paragraphs"]:
            if par.get("kind") not in ("paragraph",):
                continue
            ev = par.get("evidence") or {}
            text = (par.get("text") or "").strip()
            if len(text) < 120 or not ev.get("anchor"):
                continue
            segments.append({
                "id": ev["anchor"],
                "page": ev.get("page"),
                "block": ev.get("block"),
                "section": title,
                "text": text,
                "facts": facts(text),
            })
            if len(segments) >= args.max_paragraphs:
                break
        if len(segments) >= args.max_paragraphs:
            break

    terms: dict[str, dict] = {}
    for segment in segments:
        for term in segment["facts"]["acronyms"] + segment["facts"]["models"]:
            entry = terms.setdefault(term, {"term": term, "count": 0, "pages": [],
                                            "first_segment": segment["id"]})
            entry["count"] += 1
            if segment["page"] not in entry["pages"]:
                entry["pages"].append(segment["page"])

    totals = {
        "segments": len(segments),
        "words": sum(s["facts"]["words"] for s in segments),
        "sentences": sum(s["facts"]["sentences"] for s in segments),
        "avg_sentence_words": round(sum(s["facts"]["words"] for s in segments)
                                    / max(1, sum(s["facts"]["sentences"] for s in segments)), 2),
        "numbers": sum(len(s["facts"]["numbers"]) for s in segments),
        "citations": sum(len(s["facts"]["citations"]) for s in segments),
        "protected_terms": len(terms),
        "weasels": sum(len(s["facts"]["weasels"]) for s in segments),
        "contractions": sum(len(s["facts"]["contractions"]) for s in segments),
        "passive_hits": sum(s["facts"]["passive_hits"] for s in segments),
        "hedged_segments": sum(1 for s in segments if s["facts"]["hedges"]),
        "negated_segments": sum(1 for s in segments if s["facts"]["negations"]),
    }
    (args.out / "segments.json").write_text(json.dumps(segments, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    (args.out / "terms.json").write_text(json.dumps(sorted(terms.values(),
                                                           key=lambda t: -t["count"]),
                                                    ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    (args.out / "style.json").write_text(json.dumps(totals, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    (args.out / "prepare_summary.json").write_text(json.dumps(totals, ensure_ascii=False, indent=1),
                                                   encoding="utf-8")
    print("PREPARE_OK " + json.dumps(totals, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
