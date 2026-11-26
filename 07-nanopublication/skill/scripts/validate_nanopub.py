#!/usr/bin/env python3
"""Validate claim-level nanopublications against their source and each other.

Checks the structure the Nanopublication model requires (head, assertion,
provenance, publication info), the atomicity of each assertion, that the evidence
sentence really occurs in the parsed paper, that the provenance chain reaches the
paper, content-hash integrity of the nanopublication URI, and duplicates.

TriG is parsed with rdflib when it is installed; without it the same checks run on
the graph blocks with a strict textual reader, and the report says which parser
was used.

Usage:
    python validate_nanopub.py --work WORK [--selftest]

Exit code 0 when every hard check passes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import emit_nanopub as emit

HARD = ("trig_parse", "structure", "assertion_atomic", "evidence_verbatim",
        "provenance_chain", "pubinfo_complete", "uri_integrity", "no_duplicates",
        "coverage")
COMPOUND = re.compile(r"\s+and\s+|、|；|;|\u4e14|\u4e26|\u5e76\u4e14")


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def parse_trig(trig: str) -> tuple[object | None, str, str | None]:
    try:
        import rdflib
    except Exception:
        blocks = re.findall(r"<([^>]+)>\s*\{", trig)
        return None, "fallback", (None if blocks else "no graph blocks found")
    try:
        dataset = rdflib.Dataset()
        dataset.parse(data=trig, format="trig")
        return dataset, "rdflib", None
    except Exception as exc:  # syntax error
        return None, "rdflib", str(exc)


def block_of(trig: str, graph_uri: str) -> str | None:
    match = re.search(r"<" + re.escape(graph_uri) + r">\s*\{(.*?)\n\}", trig, re.S)
    return match.group(1) if match else None


def evaluate(trig: str, records: list[dict], paper: dict, candidates: dict,
             source_text: str, vocab: dict) -> dict:
    problems: list[dict] = []

    def fail(check: str, where: str, detail: str) -> None:
        problems.append({"check": check, "where": where, "detail": detail})

    dataset, parser_name, parse_error = parse_trig(trig)
    if parse_error:
        fail("trig_parse", "*", f"{parser_name}: {parse_error}")

    relations = set((vocab.get("relations") or {}).keys())
    seen: dict[str, str] = {}
    covered_sections = set()

    for record in records:
        uri = record["uri"]
        where = uri.rsplit("/", 1)[-1][:12]
        assertion = record.get("assertion") or {}
        evidence = record.get("evidence") or {}

        # structure: head links the three graphs, and each block exists
        head = block_of(trig, uri)
        if head is None:
            fail("structure", where, "head graph missing")
        else:
            for part in ("hasAssertion", "hasProvenance", "hasPublicationInfo"):
                if part not in head:
                    fail("structure", where, f"head graph lacks np:{part}")
        for suffix in ("#assertion", "#provenance", "#pubinfo"):
            if block_of(trig, uri + suffix) is None:
                fail("structure", where, f"graph {suffix} missing")

        # atomicity: exactly one subject/relation/object, one relation, no conjunction
        relation = assertion.get("relation")
        if relation not in relations:
            fail("assertion_atomic", where, f"relation {relation!r} not in the controlled vocabulary")
        for field in ("subject", "object"):
            value = assertion.get(field)
            if not isinstance(value, str) or not value.strip():
                fail("assertion_atomic", where, f"{field} missing")
                continue
            if COMPOUND.search(value):
                fail("assertion_atomic", where, f"{field} contains a compound conjunction: {value[:60]!r}")
            if len(value) > 200:
                fail("assertion_atomic", where, f"{field} longer than 200 chars")
        assertion_block = block_of(trig, uri + "#assertion") or ""
        for prop in ("#subject", "#relation", "#object"):
            if assertion_block.count(prop) != 1:
                fail("assertion_atomic", where, f"expected exactly one {prop} triple")

        # evidence: verbatim in the source, resolvable anchor
        quote = evidence.get("quote") or ""
        if not quote:
            fail("evidence_verbatim", where, "no evidence quote")
        elif quote not in source_text:
            fail("evidence_verbatim", where, "quote does not occur verbatim in the parsed source")
        anchor = evidence.get("anchor") or ""
        if not re.match(r"^p\d+b\d+$", anchor):
            fail("evidence_verbatim", where, f"malformed anchor {anchor!r}")
        if not isinstance(evidence.get("page"), int):
            fail("evidence_verbatim", where, "evidence page is not an integer")
        candidate = candidates.get(quote and next(
            (cid for cid, c in candidates.items() if c["text"] == quote), None))
        if candidate is not None and candidate.get("anchor") != anchor:
            fail("evidence_verbatim", where, "anchor does not match the quoted sentence")
        if evidence.get("section"):
            covered_sections.add(evidence["section"])

        # provenance chain
        prov_block = block_of(trig, uri + "#provenance") or ""
        for token in ("prov#wasAttributedTo", "prov#used", "#sourceTitle",
                      "#sourceSha256", "#evidenceQuote", "#evidenceAnchor"):
            if token not in prov_block:
                fail("provenance_chain", where, f"provenance lacks {token}")
        if paper.get("sha256") and paper["sha256"] not in prov_block:
            fail("provenance_chain", where, "source sha256 not carried into provenance")
        if record.get("paper_uri") is None:
            fail("provenance_chain", where, "no source URI")
        else:
            ids = (paper.get("identifiers") or {})
            if ids.get("arxiv") and ids["arxiv"] not in record["paper_uri"]:
                fail("provenance_chain", where, "source URI does not name the arXiv id")

        # publication info
        pub_block = block_of(trig, uri + "#pubinfo") or ""
        for token in ("terms/creator", "terms/created", "terms/license", "pav/version"):
            if token not in pub_block:
                fail("pubinfo_complete", where, f"publication info lacks {token}")

        # content hash integrity
        recomputed = emit.content_hash(assertion, evidence, paper,
                                       record.get("creator") or emit.AGENT)
        if not uri.endswith(recomputed):
            fail("uri_integrity", where, "URI hash does not recompute from the content")

        # duplicates
        key = f"{assertion.get('subject')}|{relation}|{assertion.get('object')}"
        if key in seen:
            fail("no_duplicates", where, f"duplicates {seen[key]}")
        seen[key] = where

    if len(records) < 8:
        fail("coverage", "*", f"only {len(records)} nanopublications")
    if len(covered_sections) < 5:
        fail("coverage", "*", f"only {len(covered_sections)} sections carry assertions")

    hard_failed = [p for p in problems if p["check"] in HARD]
    checks = {}
    for name in HARD:
        checks[name] = {"failed": len([p for p in problems if p["check"] == name])}
    return {
        "schema": "paper-nanopub/qa/1.0",
        "nanopubs": len(records),
        "sections_with_assertions": len(covered_sections),
        "parser": parser_name,
        "checks": checks,
        "hard_failures": len(hard_failed),
        "status": "success" if not hard_failed else ("partial" if records else "failed"),
        "failures": hard_failed,
    }


def selftest(trig: str, records: list[dict], paper: dict, candidates: dict,
             source_text: str, vocab: dict) -> dict:
    import copy

    cases = {}

    def run(name: str, mutate_records=None, mutate_trig=None) -> None:
        recs = copy.deepcopy(records)
        text = trig
        if mutate_records:
            mutate_records(recs)
        if mutate_trig:
            text = mutate_trig(text)
        report = evaluate(text, recs, paper, candidates, source_text, vocab)
        cases[name] = {"detected": report["status"] != "success",
                       "checks": sorted({p["check"] for p in report["failures"]})}

    run("missing_provenance",
        mutate_trig=lambda t: re.sub(r"<[^>]*#provenance>\s*\{.*?\n\}", "", t, count=1, flags=re.S))
    run("compound_assertion",
        mutate_records=lambda r: r[0]["assertion"].update(
            {"object": "GLUE and MultiNLI and SQuAD"}))
    run("evidence_not_in_source",
        mutate_records=lambda r: r[0]["evidence"].update(
            {"quote": "This sentence does not appear anywhere in the parsed paper."}))
    run("duplicate_assertion",
        mutate_records=lambda r: (r[1]["assertion"].update(dict(r[0]["assertion"]))))
    run("hash_mismatch",
        mutate_records=lambda r: r[0].update({"uri": r[0]["uri"][:-6] + "AAAAAA"}))
    run("missing_creator",
        mutate_trig=lambda t: t.replace("terms/creator", "terms/contributor", 1))
    run("bad_relation",
        mutate_records=lambda r: r[0]["assertion"].update({"relation": "is-related-to"}))
    for name, result in cases.items():
        result["name"] = name
    return {"clean": evaluate(trig, records, paper, candidates, source_text, vocab)["status"],
            "injected": cases,
            "all_detected": all(v["detected"] for v in cases.values())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    work = args.work
    trig = (work / "nanopubs.trig").read_text(encoding="utf-8") if (work / "nanopubs.trig").exists() else ""
    records = load_jsonl(work / "nanopubs.jsonl")
    if records:
        records = [{**r, "creator": r.get("creator") or emit.AGENT} for r in records]
    paper = load(work / "paper.json", {})
    candidates = {c["id"]: c for c in load(work / "candidates.json", [])}
    source_text = load(work / "parse.json", {}).get("markdown", "")
    vocab = load(Path(__file__).resolve().parent.parent / "vocab" / "relations.json", {})

    if args.selftest:
        result = selftest(trig, records, paper, candidates, source_text, vocab)
        out = work / "selftest.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        print("SELFTEST " + json.dumps({
            "clean": result["clean"],
            "detected": f"{sum(1 for v in result['injected'].values() if v['detected'])}"
                        f"/{len(result['injected'])}"}, ensure_ascii=False))
        return 0 if result["all_detected"] else 1

    report = evaluate(trig, records, paper, candidates, source_text, vocab)
    out = work / "qa_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("VALIDATE " + json.dumps({
        "status": report["status"], "nanopubs": report["nanopubs"],
        "sections": report["sections_with_assertions"], "parser": report["parser"],
        "hard_failures": report["hard_failures"],
        "failed": {k: v["failed"] for k, v in report["checks"].items() if v["failed"]},
    }, ensure_ascii=False))
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
