#!/usr/bin/env python3
"""Verify a methods-and-experiments draft against its reproduction spec.

The spec is the contract: every slot is either a value with a source in the paper,
or an explicit gap with a reason. The draft may only state what the spec holds.

Usage:
    python verify_method.py --work WORK [--selftest]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*(?:e-?\d+)?%?")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\u201c(\[]|\d)")
HEADING_RE = re.compile(r"^\s*#")
VAGUE = ("a few", "several", "many", "significantly", "substantial", "large batch",
         "a number of", "various")
REQUIRED_FAMILIES = {"architecture", "objective", "data", "optimization", "compute",
                     "controls", "repro"}
REQUIRED_SECTIONS = ("3.1", "3.2", "3.3", "3.4", "3.5")
HARD = ("structure", "text_sync", "spec_families", "slot_sourced", "slot_coverage",
        "prose_agreement", "numbers_grounded", "no_invention", "steps", "controls",
        "limits", "vague")


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def norm(text: str) -> str:
    return re.sub(r"[\s,]", "", (text or "").lower())


def numbers(text: str) -> set[str]:
    return {match.replace(",", "") for match in NUMBER_RE.findall(text or "")}


def md_sentences(text: str) -> list[str]:
    lines = [line for line in text.splitlines() if not HEADING_RE.match(line)]
    body = " ".join(lines)
    return [s.strip() for s in SENTENCE_RE.split(body) if len(s.strip()) > 20]


def headings(text: str) -> list[str]:
    return [line.strip("# ").strip() for line in text.splitlines() if HEADING_RE.match(line)]


def evaluate(md: str, mapping: dict, spec: dict, facts: dict, parse_text: str) -> dict:
    problems: list[dict] = []

    def fail(check: str, where: str, detail: str) -> None:
        problems.append({"check": check, "where": where, "detail": detail})

    sentences = md_sentences(md)
    entries = mapping.get("sentences") or []
    slots = {slot["id"]: slot for slot in spec.get("slots") or []}
    paper_numbers = numbers(parse_text)

    # 1 structure
    found = headings(md)
    for required in REQUIRED_SECTIONS:
        if not any(head.startswith(required) for head in found):
            fail("structure", required, "section is missing")
    if len(sentences) < 20:
        fail("structure", "md", f"only {len(sentences)} sentences; a methods section needs more")

    # 2 text sync
    if len(entries) != len(sentences):
        fail("text_sync", "mapping", f"{len(entries)} mapped entries for {len(sentences)} sentences")
    for index, (sentence, entry) in enumerate(zip(sentences, entries), start=1):
        if not entry.get("section", "").startswith(tuple(REQUIRED_SECTIONS)):
            fail("text_sync", f"s{index}", "sentence has no section")
        if not entry.get("role"):
            fail("text_sync", f"s{index}", "sentence has no role")

    # 3 families
    families = {slot.get("family") for slot in slots.values()}
    missing_families = REQUIRED_FAMILIES - families
    if missing_families:
        fail("spec_families", "spec", f"missing families: {sorted(missing_families)}")

    # 4 slot sourced / gaps reasoned
    for slot in slots.values():
        if slot.get("status") == "unavailable":
            if not (slot.get("reason") or "").strip():
                fail("slot_sourced", slot["id"], "unavailable slot has no reason")
            continue
        if not slot.get("value"):
            fail("slot_sourced", slot["id"], "stated slot has no value")
            continue
        sources = slot.get("source") or []
        if isinstance(sources, str):
            sources = [sources]
        if not sources:
            fail("slot_sourced", slot["id"], "stated slot has no source")
            continue
        joined = " ".join(facts[s]["text"] for s in sources if s in facts)
        if not joined:
            fail("slot_sourced", slot["id"], "source fact ids do not resolve")
            continue
        for value in slot["value"] if isinstance(slot["value"], list) else [slot["value"]]:
            if norm(value) not in norm(joined):
                fail("slot_sourced", slot["id"],
                     f"value {value!r} is not in the cited fact text")

    # 5 coverage
    referenced: set[str] = set()
    for entry in entries:
        referenced.update(entry.get("slots") or [])
    for slot_id in slots:
        if slot_id not in referenced:
            fail("slot_coverage", slot_id, "the draft never mentions this slot")

    # 6 prose agreement + 7 numbers grounded
    for index, (sentence, entry) in enumerate(zip(sentences, entries), start=1):
        for slot_id in entry.get("slots") or []:
            slot = slots.get(slot_id)
            if slot is None:
                fail("slot_coverage", f"s{index}", f"references unknown slot {slot_id!r}")
                continue
            if slot.get("status") == "unavailable":
                continue
            values = slot["value"] if isinstance(slot["value"], list) else [slot["value"]]
            for value in values:
                if norm(value) not in norm(sentence):
                    fail("prose_agreement", f"s{index}",
                         f"slot {slot_id} value {value!r} is not stated in the sentence")
        evidence = entry.get("evidence") or []
        allowed: set[str] = set()
        for fact_id in evidence:
            if fact_id not in facts:
                fail("numbers_grounded", f"s{index}", f"unknown fact id {fact_id!r}")
                continue
            allowed |= numbers(facts[fact_id]["text"])
        extra = numbers(sentence) - allowed
        if extra:
            fail("numbers_grounded", f"s{index}", f"numbers without a cited fact: {sorted(extra)}")

    # 8 no invention anywhere
    prose_text = " ".join(sentences)
    invented = numbers(prose_text) - paper_numbers
    if invented:
        fail("no_invention", "md", f"numbers that do not appear in the paper: {sorted(invented)}")

    # 9 steps
    roles = [entry.get("role") for entry in entries]
    if roles.count("step") < 4:
        fail("steps", "md", f"{roles.count('step')} step sentences; at least four are expected")
    if roles.count("setting") < 6:
        fail("steps", "md", f"{roles.count('setting')} setting sentences; at least six are expected")

    # 10 controls
    controls = [e for e in entries if e.get("role") == "control"]
    if len(controls) < 2:
        fail("controls", "md", "fewer than two control or ablation sentences")
    for index, entry in enumerate(controls, start=1):
        if not entry.get("evidence"):
            fail("controls", f"control{index}", "ablation claim has no anchor")

    # 11 limits
    unavailable = [s for s in slots.values() if s.get("status") == "unavailable"]
    if len(unavailable) < 3:
        fail("limits", "spec", f"{len(unavailable)} declared gaps; at least three are expected")
    limit_entries = [e for e in entries if e.get("role") == "limit"]
    limit_slots = {slot for entry in limit_entries for slot in entry.get("slots") or []}
    for slot in unavailable:
        if slot["id"] not in limit_slots:
            fail("limits", slot["id"], "gap is declared in the spec but never written into the draft")

    # 12 vague quantifiers where a number exists
    for index, (sentence, entry) in enumerate(zip(sentences, entries), start=1):
        if not entry.get("slots"):
            continue
        lowered = sentence.lower()
        for phrase in VAGUE:
            if phrase in lowered:
                fail("vague", f"s{index}", f"vague quantifier {phrase!r} stands in for a number")

    hard = [p for p in problems if p["check"] in HARD]
    return {
        "schema": "method-write/qa/1.0",
        "sentences": len(sentences),
        "sections": found,
        "slots": len(slots),
        "unavailable": len(unavailable),
        "families": sorted(families),
        "checks": {name: {"failed": len({p["where"] for p in problems if p["check"] == name})}
                   for name in HARD},
        "hard_failures": len(hard),
        "failures": hard,
        "gaps": [{"id": s["id"], "name": s["name"], "reason": s.get("reason")}
                 for s in unavailable],
        "status": "success" if not hard else ("partial" if sentences else "failed"),
    }


def selftest(md: str, mapping: dict, spec: dict, facts: dict, parse_text: str) -> dict:
    import copy

    cases = {}

    def run(name, mutate) -> None:
        draft = copy.deepcopy(mapping)
        spec_copy = copy.deepcopy(spec)
        text = md
        result = mutate(draft, spec_copy, text)
        if isinstance(result, tuple) and len(result) == 3:
            draft, spec_copy, text = result
        report = evaluate(text, draft, spec_copy, facts, parse_text)
        cases[name] = {"detected": report["status"] != "success",
                       "checks": sorted({p["check"] for p in report["failures"]})}

    def drop_slot(d, s, t):
        d["sentences"][1]["slots"] = []

    def lose_source(d, s, t):
        s["slots"][1]["source"] = ["p99b1:s0"]

    def bad_value(d, s, t):
        s["slots"][1]["value"] = ["999"]

    def gap_without_reason(d, s, t):
        for slot in s["slots"]:
            if slot["status"] == "unavailable":
                slot["reason"] = ""

    def gap_not_written(d, s, t):
        for entry in d["sentences"]:
            entry["slots"] = [x for x in (entry.get("slots") or []) if not x.startswith("S2")
                              or x in ("S25", "S26", "S27")]

    def invented_number(d, s, t):
        d["sentences"][4]["evidence"] = ["p5b6:s1"]
        t = t.replace("masks 15% of all", "masks 15% of all")

    def injected_text(d, s, t):
        return d, s, t.replace("approximately 40 epochs", "approximately 44 epochs")

    def missing_control(d, s, t):
        for entry in d["sentences"]:
            if entry.get("role") == "control":
                entry["role"] = "result"

    def drift(d, s, t):
        return d, s, t.replace("2,500M words", "2,400M words")

    def vague(d, s, t):
        return d, s, t.replace("a batch size of 256 sequences", "a large batch of 256 sequences")

    def no_step(d, s, t):
        for entry in d["sentences"]:
            if entry.get("role") == "step":
                entry["role"] = "context"

    run("slot_dropped", drop_slot)
    run("source_missing", lose_source)
    run("value_wrong", bad_value)
    run("gap_without_reason", gap_without_reason)
    run("gap_not_written", gap_not_written)
    run("invented_number", injected_text)
    run("control_missing", missing_control)
    run("value_drift", drift)
    run("vague_quantifier", vague)
    run("step_missing", no_step)

    clean = evaluate(md, mapping, spec, facts, parse_text)
    return {"clean": clean["status"], "injected": cases,
            "all_detected": all(v["detected"] for v in cases.values())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    work = args.work
    md = (work / "method.md").read_text(encoding="utf-8") if (work / "method.md").exists() else ""
    mapping = load(work / "mapping.json", {})
    spec = load(work / "spec.json", {})
    facts = {f["id"]: f for f in load(work / "facts.json", [])}
    parse_text = load(work / "parse.json", {}).get("markdown", "")

    if args.selftest:
        result = selftest(md, mapping, spec, facts, parse_text)
        (work / "selftest.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
        print("SELFTEST " + json.dumps({
            "clean": result["clean"],
            "detected": f"{sum(1 for v in result['injected'].values() if v['detected'])}"
                        f"/{len(result['injected'])}"}, ensure_ascii=False))
        return 0 if result["all_detected"] else 1

    report = evaluate(md, mapping, spec, facts, parse_text)
    (work / "qa_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    print("VERIFY " + json.dumps({
        "status": report["status"], "sentences": report["sentences"], "slots": report["slots"],
        "unavailable": report["unavailable"], "hard_failures": report["hard_failures"],
        "failed": {k: v["failed"] for k, v in report["checks"].items() if v["failed"]},
    }, ensure_ascii=False))
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
