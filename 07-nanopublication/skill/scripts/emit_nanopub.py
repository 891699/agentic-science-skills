#!/usr/bin/env python3
"""Emit claim-level nanopublications from authored assertions.

Each assertion becomes one nanopublication in TriG with the four named graphs the
Nanopublication model expects: the head graph links the other three, the assertion
graph holds one subject-relation-object, the provenance graph carries the source
paper and the evidence sentence, and the publication-info graph carries creator,
date, licence and version.

The nanopublication URI is content-addressed: a SHA-256 over the assertion, the
evidence and the source metadata. The creation timestamp is deliberately excluded
so the same claim always yields the same URI — re-running on the same assertions
is idempotent, and a changed claim changes the URI.

Usage:
    python emit_nanopub.py --work WORK [--assertions WORK/assertions.json]
        [--out WORK/nanopubs.trig] [--jsonl WORK/nanopubs.jsonl]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

NP = "http://www.nanopub.org/nschema#"
PROV = "http://www.w3.org/ns/prov#"
DCT = "http://purl.org/dc/terms/"
PAV = "http://purl.org/pav/"
VOCAB = "https://w3id.org/paper-nanopub/vocab#"
NP_BASE = "https://w3id.org/np/RA"
AGENT = "https://w3id.org/paper-nanopub/agent/deepseek-harness"
LICENSE = "https://creativecommons.org/licenses/by/4.0/"


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def esc(text: str) -> str:
    return (str(text).replace("\\", "\\\\").replace('"', '\\"')
            .replace("\n", "\\n").replace("\r", " "))


def canonical(assertion: dict, evidence: dict, paper: dict, creator: str) -> str:
    payload = {
        "assertion": {k: assertion.get(k) for k in
                      ("subject", "relation", "object", "qualifiers", "evidence_kind")},
        "evidence": {k: evidence.get(k) for k in ("quote", "page", "block", "anchor", "section")},
        "paper": {k: paper.get(k) for k in ("title", "authors", "year", "identifiers", "sha256")},
        "creator": creator,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(assertion: dict, evidence: dict, paper: dict, creator: str) -> str:
    digest = hashlib.sha256(canonical(assertion, evidence, paper, creator).encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def build(assertion: dict, candidates: dict, paper: dict, creator: str,
          created: str) -> tuple[str, str, dict]:
    quote = candidates.get(assertion.get("quote_id"))
    if quote is None:
        raise ValueError(f"assertion {assertion.get('id')} references unknown quote "
                         f"{assertion.get('quote_id')}")
    evidence = {"quote": quote["text"], "page": quote["page"], "block": quote.get("block"),
                "anchor": quote["anchor"], "section": quote["section"]}
    digest = content_hash(assertion, evidence, paper, creator)
    uri = f"{NP_BASE}{digest}"
    assertion_uri = f"{uri}#assertion"
    provenance_uri = f"{uri}#provenance"
    pubinfo_uri = f"{uri}#pubinfo"
    paper_uri = paper.get("uri") or f"https://arxiv.org/abs/{paper['identifiers'].get('arxiv', 'unknown')}"
    qualifiers = assertion.get("qualifiers") or {}

    triples = []
    triples.append(f"<{uri}> {{")
    triples.append(f"  <{uri}> <{NP}hasAssertion> <{assertion_uri}> ;")
    triples.append(f"    <{NP}hasProvenance> <{provenance_uri}> ;")
    triples.append(f"    <{NP}hasPublicationInfo> <{pubinfo_uri}> .")
    triples.append("}")
    triples.append("")
    triples.append(f"<{assertion_uri}> {{")
    triples.append(f"  <{assertion_uri}> a <{NP}Assertion> ;")
    triples.append(f"    <{VOCAB}subject> \"{esc(assertion['subject'])}\" ;")
    triples.append(f"    <{VOCAB}relation> <{VOCAB}{assertion['relation']}> ;")
    triples.append(f"    <{VOCAB}object> \"{esc(assertion['object'])}\" ;")
    if qualifiers:
        triples.append(f"    <{VOCAB}qualifiers> \"{esc(json.dumps(qualifiers, ensure_ascii=False, sort_keys=True))}\" ;")
    triples.append(f"    <{VOCAB}evidenceKind> \"{esc(assertion.get('evidence_kind', 'direct'))}\" ;")
    triples.append(f"    <{VOCAB}confidence> \"{esc(assertion.get('confidence', 'high'))}\" .")
    triples.append("}")
    triples.append("")
    triples.append(f"<{provenance_uri}> {{")
    triples.append(f"  <{provenance_uri}> a <{PROV}Activity> ;")
    triples.append(f"    <{PROV}wasAttributedTo> <{AGENT}> ;")
    triples.append(f"    <{PROV}used> <{paper_uri}> ;")
    triples.append(f"    <{PROV}generatedAtTime> \"{created}\"^^<http://www.w3.org/2001/XMLSchema#dateTime> ;")
    triples.append(f"    <{VOCAB}sourceTitle> \"{esc(paper.get('title') or '')}\" ;")
    triples.append(f"    <{VOCAB}sourceAuthors> \"{esc(paper.get('authors') or '')}\" ;")
    triples.append(f"    <{VOCAB}sourceYear> \"{paper.get('year')}\"^^<http://www.w3.org/2001/XMLSchema#gYear> ;")
    triples.append(f"    <{VOCAB}sourceSha256> \"{esc(paper.get('sha256') or '')}\" ;")
    triples.append(f"    <{VOCAB}evidenceQuote> \"{esc(evidence['quote'])}\" ;")
    triples.append(f"    <{VOCAB}evidencePage> \"{evidence['page']}\"^^<http://www.w3.org/2001/XMLSchema#integer> ;")
    triples.append(f"    <{VOCAB}evidenceAnchor> \"{esc(evidence['anchor'])}\" ;")
    triples.append(f"    <{VOCAB}evidenceSection> \"{esc(evidence['section'])}\" .")
    triples.append("}")
    triples.append("")
    triples.append(f"<{pubinfo_uri}> {{")
    triples.append(f"  <{pubinfo_uri}> a <{NP}PublicationInfo> ;")
    triples.append(f"    <{DCT}creator> <{AGENT}> ;")
    triples.append(f"    <{DCT}created> \"{created}\"^^<http://www.w3.org/2001/XMLSchema#dateTime> ;")
    triples.append(f"    <{DCT}license> <{LICENSE}> ;")
    triples.append(f"    <{PAV}version> \"1.0.0\" .")
    triples.append("}")
    record = {"uri": uri, "hash": digest,
              "assertion": {"subject": assertion["subject"], "relation": assertion["relation"],
                            "object": assertion["object"], "qualifiers": qualifiers,
                            "evidence_kind": assertion.get("evidence_kind", "direct"),
                            "confidence": assertion.get("confidence", "high")},
              "evidence": evidence, "paper_uri": paper_uri,
              "created": created, "trig": "\n".join(triples)}
    return uri, "\n".join(triples), record


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--assertions", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--jsonl", type=Path, default=None)
    ap.add_argument("--created", default=None)
    args = ap.parse_args(argv)

    work = args.work
    assertions_doc = load(args.assertions or (work / "assertions.json"), {})
    assertions = assertions_doc.get("assertions") or []
    candidates = {c["id"]: c for c in load(work / "candidates.json", [])}
    paper = load(work / "paper.json", {})
    creator = assertions_doc.get("creator", AGENT)
    created = args.created or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    blocks, records, errors = [], [], []
    for assertion in assertions:
        try:
            uri, trig, record = build(assertion, candidates, paper, creator, created)
        except ValueError as exc:
            errors.append({"assertion": assertion.get("id"), "error": str(exc)})
            continue
        blocks.append(trig)
        records.append(record)

    header = [
        f"@prefix np: <{NP}> .",
        f"@prefix prov: <{PROV}> .",
        f"@prefix dct: <{DCT}> .",
        f"@prefix pav: <{PAV}> .",
        f"@prefix vocab: <{VOCAB}> .",
        "",
    ]
    trig = "\n".join(header) + "\n\n".join(blocks) + "\n"
    out = args.out or (work / "nanopubs.trig")
    out.write_text(trig, encoding="utf-8")
    jsonl = args.jsonl or (work / "nanopubs.jsonl")
    jsonl.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
                     encoding="utf-8")
    print("EMIT_OK " + json.dumps({"nanopubs": len(records), "errors": errors,
                                    "trig": str(out)}, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
