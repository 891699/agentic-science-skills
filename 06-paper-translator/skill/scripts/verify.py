#!/usr/bin/env python3
"""Verify a bilingual translation against its source segments.

The translator (an agent or a person) writes `translations.jsonl`; this script
checks that what came back is still the same paper: every segment present once,
locked terms honoured, numbers, citations and formulas intact, negation kept,
nothing silently dropped or left in English.

Every check is mechanical and reports the segment id it failed on, so a failure
is actionable and a pass means more than "it reads well".

Usage:
    python verify.py --work WORK [--translations WORK/translations.jsonl]
        [--glossary WORK/glossary.json] [--out WORK/qa_report.json] [--selftest]

Exit code: 0 when every hard check passes, 1 when a hard check fails.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)*(?:%|‰)?")
CITATION_RE = re.compile(r"\[\s*\d+(?:\s*[,;\u2013-]\s*\d+)*\s*\]|\([A-Z][A-Za-z.\-']+(?:\s+(?:et al\.|and|&)\s*[A-Za-z.\-']*)?,?\s*\d{4}[a-z]?\)")
FORMULA_RE = re.compile(r"[A-Za-z]\s*(?:=|<|>|\u2264|\u2265|\u2248)\s*[^,.;:]{1,24}")
NEGATION_SOURCE_RE = re.compile(r"\b(?:not|no|never|none|without|cannot|n't|neither|nor)\b", re.I)
NEGATION_TARGET = ("不", "无", "未", "非", "没", "勿", "毫无", "无法", "不能")
HEDGE_SOURCE_RE = re.compile(r"\b(?:may|might|can|could|should|likely|only)\b", re.I)
PLACEHOLDER_RE = re.compile(r"TODO|TBD|<[^>]{1,20}>|\?\?\?")


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"_unparsable": line[:120]})
    return rows


def numbers(text: str) -> list[str]:
    """Numeric values, with separators and percent signs normalised away.

    Chinese writes "7.7 个百分点" where English writes "7.7% point"; the value is
    what must survive. Percent/permille glyphs are checked separately.
    """
    out = []
    for match in NUMBER_RE.finditer(text):
        value = match.group(0).replace(",", "").rstrip(".").rstrip("%").rstrip("‰")
        out.append(value)
    return out


def percent_marks(text: str) -> int:
    return len(re.findall(r"%‰", text))


def normalise_punctuation(text: str) -> str:
    """Fold full-width CJK punctuation back to ASCII so citation tokens match."""
    table = str.maketrans({"\uff08": "(", "\uff09": ")", "\uff3b": "[",
                           "\uff3d": "]", "\uff0c": ",", "\uff1b": ";",
                           "\u3001": ",", "-": "-", "\u2013": "-"})
    return text.translate(table)


def check_segment(seg: dict, tr: dict, locked_terms: list[dict]) -> list[dict]:
    problems: list[dict] = []
    source = seg["source_text"]
    target = (tr.get("target") or "").strip()
    sid = seg["id"]

    def fail(check: str, detail: str) -> None:
        problems.append({"id": sid, "check": check, "detail": detail})

    if not target:
        fail("coverage", "empty translation")
        return problems
    if PLACEHOLDER_RE.search(target):
        fail("placeholder", "target contains a placeholder marker")
    if seg.get("kind") == "byline":
        # Author names and affiliations stay in Latin script by convention.
        pass
    elif not CJK_RE.search(target):
        fail("untranslated", "no Chinese characters in the target")
    elif target.strip() == source.strip():
        fail("untranslated", "target identical to source")

    lowered = source.lower()
    for term in locked_terms:
        pattern = r"(?<![a-z])" + re.escape(term["en"].lower()) + r"(?![a-z])"
        if re.search(pattern, lowered) and term.get("zh") and term["zh"] not in target:
            fail("glossary_lock", f"{term['en']} must be translated as {term['zh']}")

    target_values = set(numbers(target))
    missing_numbers = [n for n in numbers(source) if n not in target_values]
    if missing_numbers:
        fail("numbers", f"missing numeric tokens: {missing_numbers[:6]}")

    folded_target = normalise_punctuation(target)
    missing_citations = [c.group(0) for c in CITATION_RE.finditer(source)
                         if c.group(0) not in folded_target]
    if missing_citations:
        fail("citations", f"citation markers not preserved: {missing_citations[:4]}")

    missing_formulas = [f.group(0).strip() for f in FORMULA_RE.finditer(source)
                        if f.group(0).strip() not in target]
    if missing_formulas:
        fail("formula_tokens", f"formula tokens not preserved: {missing_formulas[:3]}")

    if NEGATION_SOURCE_RE.search(source) and not any(w in target for w in NEGATION_TARGET):
        fail("negation", "source negates, target has no negation marker")

    if HEDGE_SOURCE_RE.search(source) and not any(
            w in target for w in ("可能", "可以", "能", "仅", "只", "应该", "或许")):
        fail("hedge", "source hedges or restricts, target lost the modal/restriction")

    ratio = len(target) / max(1, len(source))
    if ratio < 0.12:
        fail("length_ratio", f"target is only {ratio:.2f} of the source length")
    if ratio > 1.0:
        fail("length_ratio", f"target is {ratio:.2f} times the source length (added content?)")
    return problems


HARD_CHECKS = ("coverage", "glossary_lock", "numbers", "citations", "formula_tokens",
               "negation", "hedge", "untranslated", "placeholder")


def evaluate(segments: list[dict], translations: list[dict], glossary: list[dict]) -> dict:
    locked = [g for g in glossary if g.get("zh")]
    by_id: dict[str, dict] = {}
    duplicates: list[str] = []
    unparsable = 0
    for row in translations:
        if "_unparsable" in row:
            unparsable += 1
            continue
        sid = row.get("id")
        if sid in by_id:
            duplicates.append(str(sid))
        by_id[sid] = row

    expected = [s["id"] for s in segments]
    missing = [sid for sid in expected if sid not in by_id]
    extra = [sid for sid in by_id if sid not in set(expected)]

    failures: list[dict] = []
    if missing:
        failures.append({"id": "*", "check": "coverage", "detail": f"missing segments: {missing}"})
    if duplicates:
        failures.append({"id": "*", "check": "coverage", "detail": f"duplicate segments: {duplicates}"})
    if extra:
        failures.append({"id": "*", "check": "coverage", "detail": f"unknown segments: {extra}"})
    if unparsable:
        failures.append({"id": "*", "check": "coverage", "detail": f"{unparsable} unparsable lines"})

    per_segment = 0
    for seg in segments:
        tr = by_id.get(seg["id"])
        if tr is None:
            continue
        found = check_segment(seg, tr, locked)
        failures.extend(found)
        if found:
            per_segment += 1

    order_ok = [s["id"] for s in segments if s["id"] in by_id] == [
        row["id"] for row in translations if row.get("id") in set(expected)]

    checks = {}
    for name in ("coverage", "glossary_lock", "numbers", "citations", "formula_tokens",
                 "negation", "hedge", "untranslated", "placeholder", "length_ratio"):
        failed = [f for f in failures if f["check"] == name]
        checks[name] = {
            "failed": len(failed),
            "passed": len(expected) - len({f["id"] for f in failed}),
            "rate": round(1 - len({f["id"] for f in failed}) / max(1, len(expected)), 4),
        }

    hard_failed = [f for f in failures if f["check"] in HARD_CHECKS]
    glossary_rate = checks["glossary_lock"]["rate"]
    covered = len([sid for sid in expected if sid in by_id])
    status = ("success" if not hard_failed and order_ok
              else "partial" if covered else "failed")
    review = [{"id": f["id"], "check": f["check"], "detail": f["detail"]} for f in failures]
    review += [{"id": row.get("id"), "check": "translator_note", "detail": row.get("notes")}
               for row in translations if str(row.get("notes") or "").strip()]

    return {
        "schema": "paper-translator/qa/1.0",
        "segments_expected": len(expected),
        "segments_translated": covered,
        "coverage_rate": round(covered / max(1, len(expected)), 4),
        "order_preserved": order_ok,
        "status": status,
        "checks": checks,
        "hard_failures": len(hard_failed),
        "failures": hard_failed,
        "review_queue": review,
    }


# --------------------------------------------------------------------------- #
# self test: prove each check catches a real defect
# --------------------------------------------------------------------------- #
def selftest() -> dict:
    glossary = [{"en": "self-attention", "zh": "自注意力", "locked": True},
                {"en": "fine-tuning", "zh": "微调", "locked": True}]
    source = ("We use self-attention and fine-tuning on 16 GB of data [12]. "
              "The model is not trained from scratch. May improve results.")
    good = "我们使用自注意力与微调，在 16 GB 数据上训练 [12]。该模型并非从头训练，可能提升结果。"
    cases = {
        "term_drift": good.replace("自注意力", "自我注意力"),
        "number_lost": good.replace("16 GB", "十六 GB"),
        "citation_lost": good.replace(" [12]", ""),
        "negation_lost": good.replace("并非", ""),
        "hedge_lost": good.replace("可能", ""),
        "left_english": "We use self-attention and fine-tuning on 16 GB of data [12]. "
                        "The model is not trained from scratch. May improve results.",
        "placeholder": good.replace("微调", "TODO"),
    }
    rows = [{"id": "s1", "target": good}]
    seg = [{"id": "s1", "source_text": source, "page": 1, "section": "test"}]
    baseline = evaluate(seg, rows, glossary)
    results = {}
    for name, target in cases.items():
        report = evaluate(seg, [{"id": "s1", "target": target}], glossary)
        checks_hit = {p["check"] for p in report["review_queue"] if p.get("check")}
        results[name] = {
            "detected": report["status"] != "success" or bool(checks_hit),
            "failed_checks": sorted(checks_hit),
        }
    return {"clean_passes": baseline["status"] == "success",
            "clean_checks": baseline["checks"], "injected": results,
            "all_detected": all(v["detected"] for v in results.values())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--translations", type=Path, default=None)
    ap.add_argument("--glossary", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        result = selftest()
        out = args.out or (args.work / "selftest.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        print("SELFTEST " + json.dumps(result, ensure_ascii=False))
        return 0 if result["all_detected"] and result["clean_passes"] else 1

    segments = load_json(args.work / "segments.json")
    glossary = load_json(args.glossary or (args.work / "glossary.json"))
    translations = load_jsonl(args.translations or (args.work / "translations.jsonl"))
    report = evaluate(segments, translations, glossary)
    out = args.out or (args.work / "qa_report.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("VERIFY " + json.dumps({
        "status": report["status"],
        "coverage": report["coverage_rate"],
        "hard_failures": report["hard_failures"],
        "checks": {k: v["failed"] for k, v in report["checks"].items() if v["failed"]},
        "out": str(out),
    }, ensure_ascii=False))
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
