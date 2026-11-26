#!/usr/bin/env python3
"""Verify a drafted introduction and related work against its evidence map.

The draft is only as trustworthy as the binding between its sentences and the
paper: every sentence names a fact id, a citation key, or declares itself as the
author's judgement. This script re-checks that binding, the citation coverage, the
gap derivation, the contribution parity, the hype guard and the numbers.

Usage:
    python verify_draft.py --work WORK [--selftest]

Exit code 0 when every hard check passes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

YEAR_RE = re.compile(r"\b(19|20)\d{2}[a-z]?\b")
CITATION_RE = re.compile(r"\((?:[^()]*?\b(?:19|20)\d{2}[a-z]?[^()]*)\)")
NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)*(?:%|\u2030)?")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\u201c(])")
LIST_PREFIX = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
CONTRAST = ("however", "while", "whereas", "neither", "unlike", "only", "limited",
            "restrict", "lack", "remain", "gap", "but")
HYPE = ("first", "novel", "state-of-the-art", "best", "unprecedented")
RESULT_TOKENS = ("state-of-the-art", "obtains", "improve", "improves", "show", "shows",
                 "achieve", "achieves", "hurt", "hurts", "outperform")

HARD = ("structure", "text_sync", "evidence_present", "source_evidence", "citation_evidence",
        "citation_resolution", "citation_coverage", "gap_derivation", "contributions",
        "hype_guard", "numbers_grounded", "self_citation", "judgement_ratio")


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def md_sentences(text: str) -> list[str]:
    body = "\n".join(LIST_PREFIX.sub("", line) for line in text.splitlines())
    return [s.strip() for s in SENTENCE_RE.split(body) if len(s.strip()) > 25]


def citation_tokens(marker: str) -> list[dict]:
    inner = marker.strip("()[]")
    tokens = []
    for part in inner.split(";"):
        part = part.strip()
        match = YEAR_RE.search(part)
        if not match:
            continue
        before = part[:match.start()].strip(" ,;")
        # "Dai and Le, 2015" -> first author Dai, second Le; "Peters et al., 2018a" -> Peters
        and_parts = re.split(r"\s+and\s+", before)
        first = re.split(r"\s+et al\.?", and_parts[0])[0].strip()
        tokens.append({"surname": first, "year": match.group(0),
                       "second": and_parts[1].strip() if len(and_parts) > 1 else ""})
    return tokens


def resolve_tokens(markers: list[str], works: list[dict]) -> tuple[list[dict], list[dict]]:
    by_key = {w["key"]: w for w in works}
    by_sy: dict[tuple[str, str], list[dict]] = {}
    for work in works:
        by_sy.setdefault((norm(work["surname"]), work["year"] or ""), []).append(work)

    resolved, unresolved = [], []
    for marker in markers:
        for token in citation_tokens(marker):
            target = by_key.get(norm(token["surname"]) + token["year"])
            if target is None:
                words = token["surname"].split()
                for start in range(1, len(words)):
                    target = by_key.get(norm(" ".join(words[start:])) + token["year"])
                    if target:
                        break
            if target is None:
                base = token["year"].rstrip("abcd")
                candidates = by_sy.get((norm(token["surname"]), base), [])
                if not candidates:
                    words = token["surname"].split()
                    for start in range(1, len(words)):
                        candidates = by_sy.get((norm(" ".join(words[start:])), base), [])
                        if candidates:
                            break
                if len(candidates) == 1:
                    target = candidates[0]
                elif len(candidates) > 1 and token["second"]:
                    narrowed = [c for c in candidates if norm(token["second"]) in norm(c["authors"])]
                    if len(narrowed) == 1:
                        target = narrowed[0]
            if target is None:
                unresolved.append({"marker": marker, "token": token})
            else:
                resolved.append({"marker": marker, "token": token, "key": target["key"]})
    return resolved, unresolved


def units_of(claims: dict) -> list[dict]:
    units = []
    for key in ("intro", "related", "contributions"):
        for unit in claims.get(key) or []:
            units.append({**unit, "_bucket": key})
    return units


def evaluate(claims: dict, facts: dict, works: dict, parse_text: str,
             intro_md: str, related_md: str) -> dict:
    problems: list[dict] = []

    def fail(check: str, where: str, detail: str) -> None:
        problems.append({"check": check, "where": where, "detail": detail})

    units = units_of(claims)
    groups = claims.get("groups") or []
    work_by_key = {w["key"]: w for w in works.values()} if isinstance(works, dict) else works
    md_all = intro_md + "\n" + related_md

    # 1. structure
    roles = {unit.get("role") for unit in claims.get("intro") or []}
    for needed in ("background", "problem", "gap", "approach"):
        if needed not in roles:
            fail("structure", "intro", f"missing paragraph role {needed}")
    if len(claims.get("contributions") or []) < 3:
        fail("structure", "contributions", "fewer than three contribution items")
    if len(groups) < 3:
        fail("structure", "related", f"{len(groups)} groups; at least three routes are expected")

    # 2. the prose and the map must be the same text
    for unit in units:
        text = (unit.get("text") or "").strip()
        if not text:
            fail("text_sync", unit.get("id"), "unit has no text")
            continue
        bucket_md = intro_md if unit["_bucket"] in ("intro", "contributions") else related_md
        if text not in bucket_md:
            fail("text_sync", unit.get("id"), "unit text is not in the markdown draft")
    covered = " ".join((unit.get("text") or "") for unit in units)
    for sentence in md_sentences(md_all):
        if sentence not in covered:
            fail("text_sync", "md", f"draft sentence has no evidence unit: {sentence[:80]!r}")

    # 3..5 evidence
    judgement = 0
    cited_keys: set[str] = set()
    numbers_in_facts = " ".join(facts[f]["text"] for f in facts)
    for unit in units:
        uid = unit.get("id")
        evidence = unit.get("evidence") or []
        if not evidence:
            fail("evidence_present", uid, "no evidence at all")
            continue
        source_refs = [e for e in evidence if e.get("type") == "source"]
        citation_refs = [e for e in evidence if e.get("type") == "citation"]
        if evidence and all(e.get("type") == "judgement" for e in evidence):
            judgement += 1
            if not (unit.get("note") or evidence[0].get("note")):
                fail("judgement_ratio", uid, "judgement unit has no note explaining the basis")
        for ref in source_refs:
            fact = facts.get(ref.get("ref"))
            if fact is None:
                fail("source_evidence", uid, f"unknown fact id {ref.get('ref')!r}")
                continue
            if fact["text"] not in parse_text:
                fail("source_evidence", uid, f"fact {fact['id']} is not verbatim in the paper")
        markers = [m.group(0) for m in CITATION_RE.finditer(unit.get("text") or "")]
        resolved, unresolved = resolve_tokens(markers, list(work_by_key.values()))
        for item in unresolved:
            fail("citation_resolution", uid, f"{item['marker']} does not resolve to a reference")
        resolved_keys = {item["key"] for item in resolved}
        cited_keys |= resolved_keys
        for ref in citation_refs:
            if ref.get("ref") not in work_by_key:
                fail("citation_evidence", uid, f"unknown citation key {ref.get('ref')!r}")
            elif ref.get("ref") not in resolved_keys:
                fail("citation_evidence", uid,
                     f"{ref.get('ref')} is claimed as evidence but not cited in the sentence")

        # numbers must come from the source facts of this unit
        stripped = CITATION_RE.sub("", unit.get("text") or "")
        text_numbers = set(NUMBER_RE.findall(stripped))
        if text_numbers:
            allowed = " ".join(facts[e["ref"]]["text"] for e in source_refs
                               if e.get("ref") in facts)
            allowed_numbers = set(NUMBER_RE.findall(allowed))
            missing = text_numbers - allowed_numbers
            if missing:
                fail("numbers_grounded", uid, f"numbers not in the cited facts: {sorted(missing)}")

        for word in HYPE:
            if re.search(rf"\b{re.escape(word)}\b", (unit.get("text") or "").lower()):
                if not any(word in facts[e["ref"]]["text"].lower()
                           for e in source_refs if e.get("ref") in facts):
                    fail("hype_guard", uid, f"{word!r} is not supported by the cited fact")

    ratio = judgement / max(1, len(units))
    if ratio > 0.4:
        fail("judgement_ratio", "*", f"{judgement}/{len(units)} units are pure judgement")

    # 6. coverage
    if len(cited_keys) < 8:
        fail("citation_coverage", "*", f"only {len(cited_keys)} distinct works cited")

    # 7. gap derivation
    gap_units = [u for u in claims.get("intro") or [] if u.get("role") == "gap"]
    if not gap_units:
        fail("gap_derivation", "intro", "no paragraph marks the gap")
    else:
        gap_keys: set[str] = set()
        gap_has_contrast = False
        gap_has_source = False
        for unit in gap_units:
            markers = [m.group(0) for m in CITATION_RE.finditer(unit.get("text") or "")]
            resolved, _ = resolve_tokens(markers, list(work_by_key.values()))
            gap_keys |= {item["key"] for item in resolved}
            gap_has_contrast = gap_has_contrast or any(
                word in (unit.get("text") or "").lower() for word in CONTRAST)
            gap_has_source = gap_has_source or any(
                e.get("type") == "source" for e in unit.get("evidence") or [])
        if len(gap_keys) < 2:
            fail("gap_derivation", "intro", "the gap must be derived from at least two cited works")
        if not gap_has_contrast:
            fail("gap_derivation", "intro", "the gap paragraph states no contrast or shortcoming")
        if not gap_has_source:
            fail("gap_derivation", "intro", "the gap paragraph cites no fact from the paper")

    # 8. contributions
    for unit in claims.get("contributions") or []:
        uid = unit.get("id")
        source_refs = [e for e in unit.get("evidence") or [] if e.get("type") == "source"]
        if not source_refs:
            fail("contributions", uid, "contribution has no fact backing it")
            continue
        if not (unit.get("maps_to") or "").strip():
            fail("contributions", uid, "contribution does not name the part of the paper it maps to")
        text = " ".join(facts[e["ref"]]["text"].lower() for e in source_refs
                        if e.get("ref") in facts)
        if not any(token in text for token in RESULT_TOKENS) and not NUMBER_RE.search(text):
            fail("contributions", uid, "the backing fact states no result, number or finding")

    # 9. group membership
    for group in groups:
        members = group.get("members") or []
        if len(members) < 2:
            fail("citation_coverage", group.get("name"), "a related-work group needs at least two works")
        group_units = [u for u in claims.get("related") or [] if u.get("group") == group.get("name")]
        group_markers = " ".join(u.get("text") or "" for u in group_units)
        resolved, _ = resolve_tokens([m.group(0) for m in CITATION_RE.finditer(group_markers)],
                                     list(work_by_key.values()))
        in_group = {item["key"] for item in resolved}
        missing = [m for m in members if m not in in_group]
        if missing:
            fail("citation_coverage", group.get("name"), f"members never cited in the group: {missing}")

    # 10. no self citation
    paper_surnames = {norm(w) for w in (claims.get("paper_authors") or [])}
    for key in cited_keys:
        work = work_by_key.get(key) or {}
        if norm(work.get("surname")) in paper_surnames:
            fail("self_citation", key, "the draft cites the paper it is written for")

    hard = [p for p in problems if p["check"] in HARD]
    checks = {name: {"failed": len({p["where"] for p in problems if p["check"] == name})}
              for name in HARD}
    return {
        "schema": "intro-draft/qa/1.0",
        "units": len(units),
        "judgement_units": judgement,
        "groups": len(groups),
        "cited_works": len(cited_keys),
        "checks": checks,
        "hard_failures": len(hard),
        "failures": hard,
        "review": [{k: unit.get(k) for k in ("id", "role", "note")}
                   for unit in units if unit.get("role") == "judgement"],
        "status": "success" if not hard else ("partial" if units else "failed"),
    }


HARD_CHECKS = HARD


def selftest(claims: dict, facts: dict, works: dict, parse_text: str,
             intro_md: str, related_md: str) -> dict:
    import copy

    cases = {}

    def run(name: str, fn) -> None:
        c = copy.deepcopy(claims)
        intro, related = intro_md, related_md
        result = fn(c, intro, related)
        if isinstance(result, tuple) and len(result) == 2:
            intro, related = result
        report = evaluate(c, facts, works, parse_text, intro, related)
        cases[name] = {"detected": report["status"] != "success",
                       "checks": sorted({p["check"] for p in report["failures"]})}

    run("unit_without_evidence", lambda c, i, r: c["intro"][0].update({"evidence": []}))
    run("text_out_of_sync", lambda c, i, r: (c["intro"][0].update(
        {"text": c["intro"][0]["text"] + " Added later in the map only."}), i, r))
    run("unknown_citation", lambda c, i, r: c["related"][0]["evidence"].append(
        {"type": "citation", "ref": "nobody1999"}))
    run("dangling_fact", lambda c, i, r: c["intro"][0]["evidence"].append(
        {"type": "source", "ref": "p99b99:s0"}))
    run("ungrounded_number", lambda c, i, r: (c["intro"][0].update(
        {"text": c["intro"][0]["text"].replace("many natural", "42 natural")}), i, r))
    run("unsupported_hype", lambda c, i, r: (c["intro"][0].update(
        {"text": "This is the first framework for natural language processing."}), i, r))
    def gap_single_citation(c, intro, related):
        # rewrite every gap sentence so that the whole paragraph cites one work only
        replacements = []
        for index, unit in enumerate([u for u in c["intro"] if u.get("role") == "gap"]):
            original = unit["text"]
            updated = ("The shared objective is the limitation of a unidirectional model "
                       "(Peters et al., 2018a)." if index == 0 else
                       "We argue that this restriction weakens the pre-trained representation "
                       "(Peters et al., 2018a).")
            unit["text"] = updated
            replacements.append((original, updated))
        for original, updated in replacements:
            intro = intro.replace(original, updated)
        return c, intro, related

    run("gap_single_source", gap_single_citation)
    run("contribution_without_fact", lambda c, i, r: c["contributions"][0].update(
        {"evidence": [{"type": "citation", "ref": "peters2018a"}]}))
    run("group_too_small", lambda c, i, r: c["groups"][0].update({"members": ["peters2018a"]}))
    run("self_citation", lambda c, i, r: (c["intro"][0]["evidence"].append(
        {"type": "citation", "ref": "devlin2019"}), i, r))
    run("judgement_without_note", lambda c, i, r: c["related"][1].update(
        {"evidence": [{"type": "judgement", "ref": None}], "note": ""}))
    for name, result in cases.items():
        result["name"] = name
    clean = evaluate(claims, facts, works, parse_text, intro_md, related_md)
    return {"clean": clean["status"], "injected": cases,
            "all_detected": all(v["detected"] for v in cases.values())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    work = args.work
    facts_list = load(work / "facts.json", [])
    facts = {f["id"]: f for f in facts_list}
    works_list = load(work / "works.json", [])
    works = {w["key"]: w for w in works_list}
    claims = load(work / "claims.json", {})
    parse_text = load(work / "parse.json", {}).get("markdown", "")
    intro_md = (work / "intro.md").read_text(encoding="utf-8") if (work / "intro.md").exists() else ""
    related_md = (work / "related.md").read_text(encoding="utf-8") if (
        work / "related.md").exists() else ""

    if args.selftest:
        result = selftest(claims, facts, works, parse_text, intro_md, related_md)
        (work / "selftest.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
        print("SELFTEST " + json.dumps({
            "clean": result["clean"],
            "detected": f"{sum(1 for v in result['injected'].values() if v['detected'])}"
                        f"/{len(result['injected'])}"}, ensure_ascii=False))
        return 0 if result["all_detected"] else 1

    report = evaluate(claims, facts, works, parse_text, intro_md, related_md)
    (work / "qa_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    print("VERIFY " + json.dumps({
        "status": report["status"], "units": report["units"], "groups": report["groups"],
        "cited_works": report["cited_works"], "judgement_units": report["judgement_units"],
        "hard_failures": report["hard_failures"],
        "failed": {k: v["failed"] for k, v in report["checks"].items() if v["failed"]},
    }, ensure_ascii=False))
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
