#!/usr/bin/env python3
"""Verify a structured note against the paper it claims to summarise.

The note is written against candidate ids extracted from the PDF, so every claim
carries a sentence that really exists in the paper. This script re-checks that
end to end: the quote resolves and appears verbatim in the source, every number
in the claim is present in its quote, every paper section is accounted for, and
the card fields are complete.

Usage:
    python verify_notes.py --work WORK [--notes WORK/notes.json] [--selftest]

Exit code 0 when every hard check passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*(?:%|\u2030)?")


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def numbers(text: str) -> set[str]:
    return {m.group(0).replace(",", "").rstrip(".").rstrip("%") for m in NUMBER_RE.finditer(text)}


def claim_entries(notes: dict) -> list[dict]:
    """Flatten the card and the section notes into one list of claims."""
    out = []
    card = notes.get("card") or {}
    for key in ("research_question", "data", "method", "reuse"):
        item = card.get(key)
        if isinstance(item, dict) and item.get("claim"):
            out.append({"where": f"card.{key}", "claim": item["claim"],
                        "quote_id": item.get("quote_id")})
    for key in ("conditions", "findings", "limitations"):
        for i, item in enumerate(card.get(key) or []):
            if isinstance(item, dict) and item.get("claim"):
                out.append({"where": f"card.{key}[{i}]", "claim": item["claim"],
                            "quote_id": item.get("quote_id")})
    for sec in notes.get("sections") or []:
        for i, item in enumerate(sec.get("notes") or []):
            if isinstance(item, dict) and item.get("claim"):
                out.append({"where": f"section:{sec.get('section')}[{i}]",
                            "claim": item["claim"], "quote_id": item.get("quote_id")})
    return out


HARD = ("quote_resolution", "quote_verbatim", "number_grounding", "section_coverage",
        "anchor_resolution", "card_completeness", "claim_uniqueness")


def evaluate(parse: dict, candidates: list[dict], segments: list[dict], notes: dict) -> dict:
    problems: list[dict] = []
    by_candidate = {c["id"]: c for c in candidates}
    by_section = {s["section"]: s for s in segments}
    source_text = parse.get("markdown", "") or ""
    claims = claim_entries(notes)

    def fail(check: str, where: str, detail: str) -> None:
        problems.append({"check": check, "where": where, "detail": detail})

    # 1. every quote id resolves
    for claim in claims:
        qid = claim.get("quote_id")
        if not qid:
            fail("quote_resolution", claim["where"], "claim has no quote_id")
            continue
        if qid not in by_candidate:
            fail("quote_resolution", claim["where"], f"unknown quote_id {qid}")

    # 2. every quote appears verbatim in the source document
    for claim in claims:
        cand = by_candidate.get(claim.get("quote_id"))
        if not cand:
            continue
        if cand["text"] not in source_text:
            fail("quote_verbatim", claim["where"],
                 f"quote {cand['id']} is not verbatim in the parsed source")

    # 3. no number in a claim that its quote does not contain
    for claim in claims:
        cand = by_candidate.get(claim.get("quote_id"))
        if not cand:
            continue
        extra = numbers(claim["claim"]) - numbers(cand["text"])
        if extra:
            fail("number_grounding", claim["where"],
                 f"numbers absent from the quote: {sorted(extra)}")

    # 4. every paper section accounted for, with a role when it has no notes
    noted = {s.get("section") for s in (notes.get("sections") or [])}
    for segment in segments:
        name = segment["section"]
        if name not in noted:
            fail("section_coverage", name, "section missing from the note")
            continue
        entry = next(s for s in notes["sections"] if s.get("section") == name)
        if not (entry.get("notes") or []):
            if len((entry.get("role") or "").strip()) < 6:
                fail("section_coverage", name, "section has no notes and no role line")

    # 5. every quote anchor resolves to a real section in the parse
    parse_sections = {s["title"].strip() for s in parse.get("sections", [])}
    for claim in claims:
        cand = by_candidate.get(claim.get("quote_id"))
        if not cand:
            continue
        if cand["section"] not in parse_sections:
            fail("anchor_resolution", claim["where"],
                 f"quote section {cand['section']!r} not in the parsed outline")
        if not re.match(r"^p\d+b\d+", str(cand["anchor"])):
            fail("anchor_resolution", claim["where"], f"bad anchor {cand['anchor']}")

    # 6. card completeness
    card = notes.get("card") or {}
    required_scalars = ("research_question", "data", "method", "reuse")
    for key in required_scalars:
        item = card.get(key)
        if not isinstance(item, dict) or not item.get("claim"):
            fail("card_completeness", f"card.{key}", "missing")
    for key, minimum in (("findings", 2), ("limitations", 1), ("conditions", 1)):
        if len([x for x in (card.get(key) or []) if x.get("claim")]) < minimum:
            fail("card_completeness", f"card.{key}", f"needs at least {minimum}")

    # 7. unique claims, and enough sections carrying evidence
    seen: dict[str, str] = {}
    for claim in claims:
        key = claim["claim"].strip()
        if key in seen:
            fail("claim_uniqueness", claim["where"], f"duplicates {seen[key]}")
        seen[key] = claim["where"]
    sections_with_claims = len({c["where"].split(":")[1].split("[")[0]
                                for c in claims if c["where"].startswith("section:")})

    hard = [p for p in problems if p["check"] in HARD]
    checks = {}
    for name in HARD:
        checks[name] = {"failed": len([p for p in problems if p["check"] == name])}
    checks["sections_with_claims"] = {"value": sections_with_claims}

    return {
        "schema": "paper-note/qa/1.0",
        "claims": len(claims),
        "sections_in_paper": len(segments),
        "sections_in_note": len(noted),
        "sections_with_claims": sections_with_claims,
        "checks": checks,
        "hard_failures": len(hard),
        "failures": hard,
        "status": ("success" if not hard and len(claims) >= 8 and sections_with_claims >= 5
                   else "partial" if claims else "failed"),
        "review_queue": [
            {"where": c["where"], "detail": f"{len(numbers(c['claim']))} numbers in claim"}
            for c in claims if len(numbers(c["claim"])) >= 4
        ],
    }


def selftest(parse: dict, candidates: list[dict], segments: list[dict], notes: dict) -> dict:
    """Inject one defect per check and require the verifier to catch it."""
    import copy

    def mutate(fn) -> dict:
        broken = copy.deepcopy(notes)
        fn(broken)
        report = evaluate(parse, candidates, segments, broken)
        return {"status": report["status"],
                "checks": sorted({p["check"] for p in report["failures"]})}

    first = candidates[0]["id"]
    cases = {
        "unknown_quote": lambda n: n["sections"][1]["notes"].append(
            {"claim": "无来源的论断", "quote_id": "p999b999:s0"}),
        "invented_number": lambda n: n["card"]["findings"][0].update(
            {"claim": "本文报告 99.9% 的准确率"}),
        "missing_section": lambda n: n["sections"].pop(),
        "no_role": lambda n: next(s for s in n["sections"] if not s["notes"]).update({"role": ""}),
        "empty_card": lambda n: n["card"].pop("limitations"),
        "duplicate_claim": lambda n: n["sections"][1]["notes"].append(
            dict(n["sections"][1]["notes"][0])),
        "bad_anchor": lambda n: n["card"]["method"].update({"quote_id": first + "x"}),
    }
    results = {name: mutate(fn) for name, fn in cases.items()}
    for name, result in results.items():
        result["detected"] = result["status"] != "success" or bool(result["checks"])
    return {"clean_status": evaluate(parse, candidates, segments, notes)["status"],
            "injected": results,
            "all_detected": all(r["detected"] for r in results.values())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--notes", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    parse = load(args.work / "parse.json", {})
    candidates = load(args.work / "candidates.json", [])
    segments = load(args.work / "segments.json", [])
    notes = load(args.notes or (args.work / "notes.json"), {})

    if args.selftest:
        result = selftest(parse, candidates, segments, notes)
        out = args.out or (args.work / "selftest.json")
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        print("SELFTEST " + json.dumps({
            "clean": result["clean_status"],
            "detected": f"{sum(1 for v in result['injected'].values() if v['detected'])}"
                        f"/{len(result['injected'])}",
        }, ensure_ascii=False))
        return 0 if result["all_detected"] else 1

    report = evaluate(parse, candidates, segments, notes)
    out = args.out or (args.work / "qa_report.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("VERIFY " + json.dumps({
        "status": report["status"], "claims": report["claims"],
        "hard_failures": report["hard_failures"],
        "sections": f"{report['sections_in_note']}/{report['sections_in_paper']}",
        "failed": {k: v["failed"] for k, v in report["checks"].items()
                   if isinstance(v, dict) and v.get("failed")},
        "out": str(out),
    }, ensure_ascii=False))
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
