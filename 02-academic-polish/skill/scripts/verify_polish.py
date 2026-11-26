#!/usr/bin/env python3
"""Verify a polish against the draft it edits.

The point of a polish is that the prose improves and the science does not move.
This script checks the second half mechanically: every number, citation, protected
term, negation and hedge survives; the edit is minimal in length and sentence
count; every claimed change really occurs in the pair of texts; and the style
metrics moved in the intended direction.

Usage:
    python verify_polish.py --work WORK [--polished WORK/polished.jsonl] [--selftest]

Exit code 0 when every hard check passes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

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
CONTRACTIONS = ("n't", "'re", "'ve", "'ll", "'d", "it's")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\u201c(])")

HARD = ("coverage", "numbers", "citations", "protected_terms", "negation", "hedges",
        "change_log", "length_ratio", "sentence_delta", "contractions", "style")


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


def nums(text: str) -> list[str]:
    return sorted({m.group(0).replace(",", "") for m in NUMBER_RE.finditer(text)})


def cites(text: str) -> list[str]:
    return sorted({m.group(0) for m in CITATION_RE.finditer(text)})


def terms(text: str) -> list[str]:
    return sorted({m.group(0) for m in ACRONYM_RE.finditer(text)}
                  | {m.group(0) for m in MODEL_RE.finditer(text)})


def count_words(items, text: str) -> int:
    lowered = text.lower()
    return sum(len(re.findall(rf"\b{re.escape(w)}\b", lowered)) for w in items)


def sentences(text: str) -> int:
    return len([s for s in SENTENCE_RE.split(text) if s.strip()])


def words(text: str) -> int:
    return len(re.findall(r"[A-Za-z']+", text))


def style(text: str) -> dict:
    return {
        "words": words(text),
        "sentences": sentences(text),
        "avg_sentence_words": round(words(text) / max(1, sentences(text)), 2),
        "weasels": count_words(WEASELS + () if False else WEASELS, text),
        "passive_hits": len(re.findall(r"\b(?:is|are|was|were|be|been|being)\s+\w+ed\b",
                                       text.lower())),
    }


def evaluate(segments: list[dict], polished: list[dict]) -> dict:
    problems: list[dict] = []

    def fail(check: str, where: str, detail: str) -> None:
        problems.append({"check": check, "where": where, "detail": detail})

    by_id = {row.get("id"): row for row in polished}
    expected = [s["id"] for s in segments]
    for sid in expected:
        if sid not in by_id:
            fail("coverage", sid, "segment missing from the polish")
    for sid in by_id:
        if sid not in expected:
            fail("coverage", sid, "polish contains an unknown segment id")
    order_ok = [s["id"] for s in segments if s["id"] in by_id] == [
        row["id"] for row in polished if row.get("id") in set(expected)]

    before_style = {"words": 0, "sentences": 0, "weasels": 0, "passive_hits": 0}
    after_style = dict(before_style)
    total_changes = 0

    for segment in segments:
        row = by_id.get(segment["id"])
        if row is None:
            continue
        src = segment["text"]
        dst = (row.get("polished") or "").strip()
        where = segment["id"]
        if not dst:
            fail("coverage", where, "empty polished text")
            continue

        if nums(src) != nums(dst):
            missing = [n for n in nums(src) if n not in nums(dst)]
            added = [n for n in nums(dst) if n not in nums(src)]
            fail("numbers", where, f"numbers changed: missing={missing} added={added}")
        if cites(src) != cites(dst):
            missing = [c for c in cites(src) if c not in dst]
            added = [c for c in cites(dst) if c not in src]
            fail("citations", where, f"citations changed: missing={missing} added={added}")
        dropped_terms = [t for t in terms(src) if t not in set(terms(dst))]
        if dropped_terms:
            fail("protected_terms", where, f"protected terms dropped: {dropped_terms}")

        src_neg = count_words(NEGATIONS, src)
        dst_neg = count_words(NEGATIONS, dst)
        if dst_neg < src_neg:
            fail("negation", where, f"negation lost or weakened ({src_neg} -> {dst_neg})")
        src_hedge = count_words(HEDGES, src)
        dst_hedge = count_words(HEDGES, dst)
        if dst_hedge < src_hedge:
            fail("hedges", where, f"hedging lost or weakened ({src_hedge} -> {dst_hedge})")

        changes = row.get("changes") or []
        if dst != src and not changes:
            fail("change_log", where, "text changed but no change is recorded")
        if dst == src and changes:
            fail("change_log", where, "changes recorded but the text is unchanged")
        for index, change in enumerate(changes):
            before = change.get("before") or ""
            after = change.get("after") or ""
            if not before or before not in src:
                fail("change_log", where, f"change {index} 'before' is not in the draft")
            if not after or after not in dst:
                fail("change_log", where, f"change {index} 'after' is not in the polish")
            if not change.get("type"):
                fail("change_log", where, f"change {index} has no type")
            if len((change.get("reason") or "").strip()) < 10:
                fail("change_log", where, f"change {index} has no usable reason")
        total_changes += len(changes)

        ratio = words(dst) / max(1, words(src))
        if not 0.85 <= ratio <= 1.15:
            fail("length_ratio", where, f"length ratio {ratio:.2f} outside the minimal-edit band")
        delta = sentences(dst) - sentences(src)
        if not -1 <= delta <= 2:
            fail("sentence_delta", where, f"sentence count moved by {delta}")
        bad = [c for c in CONTRACTIONS if c in dst.lower()]
        if bad:
            fail("contractions", where, f"informal contractions: {bad}")

        b, a = style(src), style(dst)
        for key in before_style:
            before_style[key] += b.get(key, 0) if key != "words" and key != "sentences" else b[key]
            after_style[key] += a.get(key, 0) if key != "words" and key != "sentences" else a[key]
        if a["weasels"] > b["weasels"]:
            fail("style", where, "polish adds intensifier padding")
        if b["passive_hits"] and a["passive_hits"] > b["passive_hits"]:
            fail("style", where, "polish adds passive constructions")

    if not order_ok:
        fail("coverage", "*", "segment order changed")

    hard = [p for p in problems if p["check"] in HARD]
    print_style = {
        "before": {"words": before_style["words"], "sentences": before_style["sentences"],
                   "avg_sentence_words": round(before_style["words"]
                                               / max(1, before_style["sentences"]), 2),
                   "weasels": before_style["weasels"],
                   "passive_hits": before_style["passive_hits"]},
        "after": {"words": after_style["words"], "sentences": after_style["sentences"],
                  "avg_sentence_words": round(after_style["words"]
                                              / max(1, after_style["sentences"]), 2),
                  "weasels": after_style["weasels"],
                  "passive_hits": after_style["passive_hits"]},
    }
    checks = {name: {"failed": len({p["where"] for p in problems if p["check"] == name})}
              for name in HARD}
    return {
        "schema": "paper-polish/qa/1.0",
        "segments": len(segments),
        "polished": len(by_id),
        "changes": total_changes,
        "order_preserved": order_ok,
        "checks": checks,
        "hard_failures": len(hard),
        "failures": hard,
        "style": print_style,
        "status": "success" if not hard else ("partial" if by_id else "failed"),
    }


def selftest(segments: list[dict], polished: list[dict]) -> dict:
    import copy

    cases = {}

    def first_row(rows):
        return rows[0]

    def run(name: str, fn) -> None:
        rows = copy.deepcopy(polished)
        fn(rows)
        report = evaluate(segments, rows)
        cases[name] = {"detected": report["status"] != "success",
                       "checks": sorted({p["check"] for p in report["failures"]})}

    def mutate_first(rows, needle, replacement):
        for row in rows:
            if needle in row["polished"]:
                row["polished"] = row["polished"].replace(needle, replacement, 1)
                return True
        return False

    run("number_changed", lambda r: mutate_first(r, "80.5", "80.6"))
    run("citation_dropped", lambda r: mutate_first(
        r, "(Peters et al., 2018a; Radford et al., 2018)", ""))
    run("term_dropped", lambda r: first_row(r).update(
        {"polished": first_row(r)["polished"].replace("BERT", "the model")}))
    run("hedge_lost", lambda r: r[4].update(
        {"polished": r[4]["polished"].replace("could be very harmful", "is very harmful")}))
    run("bad_change_log", lambda r: first_row(r)["changes"][0].update(
        {"before": "this phrase is not in the draft"}))
    run("silent_rewrite", lambda r: first_row(r).update({"changes": []}))
    run("informal", lambda r: r[0].update(
        {"polished": r[0]["polished"] + " It's a big win."}))
    for name, result in cases.items():
        result["name"] = name
    clean = evaluate(segments, polished)
    return {"clean": clean["status"], "injected": cases,
            "all_detected": all(v["detected"] for v in cases.values())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--polished", type=Path, default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    segments = load(args.work / "segments.json", [])
    polished = load_jsonl(args.polished or (args.work / "polished.jsonl"))

    if args.selftest:
        result = selftest(segments, polished)
        (args.work / "selftest.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                                 encoding="utf-8")
        print("SELFTEST " + json.dumps({
            "clean": result["clean"],
            "detected": f"{sum(1 for v in result['injected'].values() if v['detected'])}"
                        f"/{len(result['injected'])}"}, ensure_ascii=False))
        return 0 if result["all_detected"] else 1

    report = evaluate(segments, polished)
    (args.work / "qa_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    print("VERIFY " + json.dumps({
        "status": report["status"], "segments": report["segments"],
        "changes": report["changes"], "hard_failures": report["hard_failures"],
        "failed": {k: v["failed"] for k, v in report["checks"].items() if v["failed"]},
        "style": report["style"],
    }, ensure_ascii=False))
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
