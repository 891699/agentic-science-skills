#!/usr/bin/env python3
"""Extract the materials a methods section is written from.

Three products, all anchored to a page and block of the paper:

* ``facts.json``   sentences that can be quoted, with the numbers they contain
* ``params.json``  candidate parameters, each with its value, unit and sentence
* ``tables.json``  table rows that carry numbers, kept apart from prose

The point is to make every number in the draft traceable to a location before a
single sentence is written. A parameter the extractor cannot find is a gap the
draft has to declare, not a value it may invent.

Usage:
    python prepare.py PAPER.pdf --out WORK [--max-facts 260]
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

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\u201c(\[]|\d)")
ABBREV = ("et al.", "e.g.", "i.e.", "fig.", "eq.", "sec.", "vs.", "cf.", "resp.", "app.", "no.")
NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)*(?:%|\u2030)?")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

# parameter families: (family, name, pattern, unit)
PATTERNS: list[tuple[str, str, str, str]] = [
    # architecture
    ("architecture", "layers", r"\bL\s*=\s*(\d+)\b", "layers"),
    ("architecture", "hidden_size", r"\bH\s*=\s*(\d+)\b", "dim"),
    ("architecture", "attention_heads", r"\bA\s*=\s*(\d+)\b", "heads"),
    ("architecture", "parameters", r"\b(\d+(?:\.\d+)?)\s*M\s+parameters", "M"),
    ("architecture", "model_parameters", r"contains\s+(\d+)\s*M\s+parameters", "M"),
    ("architecture", "encoder_layers", r"\b(\d+)\s+layers", "layers"),
    ("architecture", "hidden_dim", r"hidden size of (\d+)", "dim"),
    ("architecture", "self_attention_heads", r"(\d+)\s+self-attention heads", "heads"),
    ("architecture", "vocab_size", r"vocabulary of (\d+)", "tokens"),
    ("architecture", "activation", r"(gelu|relu|swish)\s+activation", "name"),
    # data
    ("data", "books_corpus_words", r"BooksCorpus\D{0,40}?(\d+(?:,\d+)*)\s*M\s+words", "M words"),
    ("data", "wikipedia_words", r"Wikipedia\D{0,40}?(\d+(?:,\d+)*)\s*M\s+words", "M words"),
    ("data", "corpus_words", r"(\d+(?:\.\d+)?)\s*billion\s*word corpus", "billion words"),
    ("data", "dropout", r"dropout probability of (0\.\d+)", "rate"),
    # objective
    ("objective", "mask_rate", r"mask(?:s|ed)?\s+(\d+(?:\.\d+)?)\s*%\s*of", "%"),
    ("objective", "mask_rate_positions", r"chooses\s+(\d+)\s*%\s*of the token positions", "%"),
    ("objective", "mask_random", r"\b(80)\s*%", "%"),
    ("objective", "mask_keep", r"\b(10)\s*%", "%"),
    ("objective", "nsp", r"next sentence prediction", "task"),
    # optimization
    ("optimization", "optimizer", r"\b(Adam|AdamW|SGD|LAMB)\b", "name"),
    ("optimization", "batch_size", r"batch size of (\d+)", "sequences"),
    ("optimization", "tokens_per_batch", r"([\d,]+)\s*tokens/batch", "tokens"),
    ("optimization", "learning_rate", r"learning rate of ([\d.]+(?:e-?\d+)?)", "lr"),
    ("optimization", "pretrain_learning_rate", r"learning rate of (1e-4)", "lr"),
    ("optimization", "weight_decay", r"L2 weight decay of (0\.\d+)", "rate"),
    ("optimization", "beta1", r"\u03b21\s*=\s*(0\.\d+)", "rate"),
    ("optimization", "beta2", r"\u03b22\s*=\s*(0\.\d+)", "rate"),
    ("optimization", "train_steps", r"([\d,]+)\s+steps", "steps"),
    ("optimization", "warmup_steps", r"warmup[^.]{0,40}?([\d,]+)\s*steps", "steps"),
    ("optimization", "epochs", r"(\d+)\s+epochs", "epochs"),
    ("optimization", "approx_epochs", r"approximately\s+(\d+)\s+epochs", "epochs"),
    ("optimization", "sequence_length", r"sequence length of (\d+)", "tokens"),
    ("optimization", "max_seq_length", r"maximum sequence length[^.]{0,20}?(\d+)", "tokens"),
    # compute
    ("compute", "tpu_chips", r"(\d+)\s+TPU chips", "chips"),
    ("compute", "cloud_tpus", r"(\d+)\s+Cloud TPUs?", "TPUs"),
    ("compute", "training_days", r"(\d+)\s+days", "days"),
    ("compute", "training_hours", r"([\d.]+)\s+hours?", "hours"),
]


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
    return {"title": title, "authors": authors,
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
                if len(sentence) < 20:
                    continue
                facts.append({"id": f"{anchor}:s{order}", "anchor": anchor,
                              "page": ev.get("page"), "block": ev.get("block"),
                              "section": title, "text": sentence,
                              "numbers": NUMBER_RE.findall(sentence)})
                if len(facts) >= limit:
                    return facts
    return facts


def build_params(facts: list[dict]) -> list[dict]:
    found: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for fact in facts:
        text = fact["text"]
        for family, name, pattern, unit in PATTERNS:
            for match in re.finditer(pattern, text, re.I):
                value = match.group(1) if match.groups() else match.group(0)
                key = (name, value)
                if key in seen:
                    continue
                seen.add(key)
                found.append({
                    "id": f"p{len(found) + 1:03d}",
                    "family": family, "name": name, "value": value.strip(),
                    "unit": unit, "fact": fact["id"], "page": fact["page"],
                    "anchor": fact["anchor"], "section": fact["section"],
                    "quote": text,
                })
    return found


def build_tables(parse: dict) -> list[dict]:
    rows = []
    for index, table in enumerate(parse.get("tables") or [], start=1):
        ev = table.get("evidence") or {}
        rows.append({"id": f"t{index:03d}", "anchor": ev.get("anchor"),
                     "page": ev.get("page"), "caption": table.get("caption"),
                     "text": table.get("text") or "",
                     "numbers": NUMBER_RE.findall(table.get("text") or "")})
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-facts", type=int, default=420)
    args = ap.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    parse = PdfEvidenceParser(args.pdf).parse()
    (args.out / "parse.json").write_text(json.dumps(parse, ensure_ascii=False, indent=1),
                                         encoding="utf-8")

    facts = build_facts(parse, args.max_facts)
    params = build_params(facts)
    tables = build_tables(parse)
    works, _ = refmod.merge_entries(parse.get("references", {}).get("entries") or [])
    works = refmod.assign_keys(works)

    meta = paper_metadata(parse, args.pdf)
    for name, payload in (("facts", facts), ("params", params), ("tables", tables),
                          ("works", works), ("paper", meta)):
        (args.out / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                               encoding="utf-8")
    summary = {"facts": len(facts), "params": len(params), "tables": len(tables),
               "works": len(works), "pages": meta["pages"], "arxiv": meta["arxiv"],
               "families": sorted({p["family"] for p in params})}
    (args.out / "prepare_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                                   encoding="utf-8")
    print("PREPARE_OK " + json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
