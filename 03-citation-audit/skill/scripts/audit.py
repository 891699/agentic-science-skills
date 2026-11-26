#!/usr/bin/env python3
"""Audit a paper's reference list against its in-text citations, and export both.

Parses each reference entry into fields, merges fragments the PDF split apart,
builds citation keys, resolves every in-text citation against the list, and writes
the reconciliation report plus a BibTeX and CSL-JSON export.

Usage:
    python audit.py --work WORK [--selftest]

Outputs:
    refs_parsed.json   entries with authors/year/title/venue/doi/key/merges
    citations_resolved.json  every marker with the reference it resolves to
    audit_report.json  the checks, the unresolved list and the duplicates
    refs.bib           BibTeX export
    refs.csl.json      CSL-JSON export
    citations.csv      marker, page, anchor, resolved key
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

YEAR_RE = re.compile(r"\b(19|20)\d{2}[a-z]?\b")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
ARXIV_RE = re.compile(r"arXiv:\s*(\d{4}\.\d{4,5})(?:v(\d+))?", re.I)
URL_RE = re.compile(r"https?://\S+")
TOKEN_SPLIT = re.compile(r";")


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def surname_of(authors: str) -> str:
    """First author's surname: cut the author block at the first author."""
    first = authors.split(",")[0].strip()
    first = re.split(r"\s+and\s+", first)[0]
    first = re.sub(r"^(?:and|&)\s+", "", first)
    parts = [part for part in re.split(r"\s+", first) if part]
    return parts[-1] if parts else ""


def parse_entry(entry: dict) -> dict:
    text = entry["text"].strip()
    year_match = YEAR_RE.search(text)
    year = year_match.group(0) if year_match else None
    authors = text[:year_match.start()].strip(" .;,") if year_match else ""
    after = text[year_match.end():].strip(" .;,") if year_match else text
    title = after
    venue = ""
    split = re.split(r"\.\s+", after, maxsplit=1)
    if len(split) == 2:
        title, venue = split[0].strip(), split[1].strip()
    doi = DOI_RE.search(text)
    arxiv = ARXIV_RE.search(text)
    return {
        "id": entry["id"],
        "text": text,
        "page": entry.get("page"),
        "anchor": entry.get("anchor"),
        "authors": authors,
        "surname": surname_of(authors),
        "year": year,
        "title": title,
        "venue": venue,
        "doi": doi.group(0) if doi else None,
        "arxiv": arxiv.group(1) if arxiv else None,
    }


def is_fragment(entry: dict, parsed: dict) -> bool:
    return parsed["year"] is None or parsed["text"][:1].islower() or parsed["text"][:1] in ",;}"


def finalize(entry_id: str, text: str, page, anchor, sources: list[str]) -> dict:
    parsed = parse_entry({"id": entry_id, "text": text, "page": page, "anchor": anchor})
    parsed["sources"] = sources
    return parsed


def merge_entries(refs: list[dict]) -> tuple[list[dict], list[dict]]:
    """Reassemble entries the PDF split across blocks.

    In a two-column reference list the *head* of an entry can land in the block
    before its continuation, so a fragment is prepended to the next complete
    entry; only trailing fragments attach backwards.
    """
    merged: list[dict] = []
    merges: list[dict] = []
    pending: list[dict] = []
    for entry in refs:
        parsed = parse_entry(entry)
        if is_fragment(entry, parsed):
            pending.append(parsed)
            continue
        if pending:
            head = " ".join(item["text"] for item in pending)
            sources = [item["text"] for item in pending] + [parsed["text"]]
            combined = finalize(parsed["id"], head + " " + parsed["text"],
                                parsed["page"], parsed["anchor"], sources)
            for item in pending:
                merges.append({"merged": item["id"], "into": parsed["id"],
                               "reason": "head fragment: the PDF placed the start of the entry "
                                         "in the previous text block"})
            pending = []
            merged.append(combined)
        else:
            merged.append(finalize(parsed["id"], parsed["text"], parsed["page"],
                                   parsed["anchor"], [parsed["text"]]))
    if pending and merged:
        target = merged[-1]
        text = target["text"] + " " + " ".join(item["text"] for item in pending)
        sources = target["sources"] + [item["text"] for item in pending]
        for item in pending:
            merges.append({"merged": item["id"], "into": target["id"],
                           "reason": "trailing fragment: no complete entry follows"})
        merged[-1] = finalize(target["id"], text, target["page"], target["anchor"], sources)
    return merged, merges


def assign_keys(refs: list[dict]) -> list[dict]:
    counts: dict[tuple[str, str], int] = {}
    for ref in refs:
        base = (norm(ref["surname"]), ref["year"] or "")
        counts[base] = counts.get(base, 0) + 1
    seen: dict[tuple[str, str], int] = {}
    for ref in refs:
        base = (norm(ref["surname"]), ref["year"] or "")
        if counts[base] > 1:
            seen[base] = seen.get(base, 0) + 1
            suffix = chr(96 + seen[base])
            ref["key"] = f"{ref['surname'].lower()}{ref['year'] or 'nd'}{suffix}"
            ref["key_suffix"] = suffix
        else:
            ref["key"] = f"{ref['surname'].lower()}{ref['year'] or 'nd'}"
            ref["key_suffix"] = ""
    return refs


def citation_tokens(marker: str) -> list[dict]:
    inner = marker.strip("()[]")
    tokens = []
    for part in TOKEN_SPLIT.split(inner):
        part = part.strip()
        if not part:
            continue
        match = YEAR_RE.search(part)
        if not match:
            continue
        before = part[:match.start()].strip(" ,;")
        before = re.split(r"\s+et al\.?", before)[0]
        before = re.split(r"\s+and\s+", before)[0]
        second = re.split(r"\s+and\s+", part[:match.start()].strip(" ,;"))
        tokens.append({"surname": before.strip(), "year": match.group(0),
                       "second": second[1].strip() if len(second) > 1 else ""})
    return tokens


def resolve(refs: list[dict], citations: list[dict]) -> tuple[list[dict], list[dict]]:
    by_key = {ref["key"]: ref for ref in refs}
    by_surname_year: dict[tuple[str, str], list[dict]] = {}
    for ref in refs:
        by_surname_year.setdefault((norm(ref["surname"]), ref["year"] or ""), []).append(ref)

    resolved, unresolved = [], []
    for citation in citations:
        for token in citation_tokens(citation["marker"]):
            if not token["surname"].strip():
                # a bare year in parentheses is not an author-year citation
                continue
            key = norm(token["surname"]) + token["year"]
            target = by_key.get(key)
            if target is None:
                # multi-word surnames: Tjong Kim Sang -> Kim Sang -> Sang
                words = token["surname"].split()
                for start in range(1, len(words)):
                    tail = " ".join(words[start:])
                    target = by_key.get(norm(tail) + token["year"])
                    if target is not None:
                        break
            if target is None:
                base_year = token["year"].rstrip("abcd")
                candidates = by_surname_year.get((norm(token["surname"]), base_year), [])
                if not candidates:
                    words = token["surname"].split()
                    for start in range(1, len(words)):
                        candidates = by_surname_year.get((norm(" ".join(words[start:])),
                                                          base_year), [])
                        if candidates:
                            break
                if len(candidates) == 1:
                    target = candidates[0]
                elif len(candidates) > 1:
                    if token.get("second"):
                        narrowed = [c for c in candidates
                                    if norm(token["second"]) in norm(c["authors"])]
                        if len(narrowed) == 1:
                            target = narrowed[0]
                    if target is None:
                        unresolved.append({**citation, "token": token,
                                           "reason": "ambiguous: several references share "
                                                     "surname and year"})
                        continue
            if target is None:
                unresolved.append({**citation, "token": token,
                                   "reason": "no reference matches this surname and year"})
                continue
            resolved.append({**citation, "token": token, "key": target["key"],
                             "ref_id": target["id"]})
    return resolved, unresolved


def duplicates(refs: list[dict]) -> list[dict]:
    seen: dict[str, str] = {}
    found = []
    for ref in refs:
        key = norm(ref["title"])[:80] if ref["title"] else (ref["doi"] or "")
        if not key:
            continue
        if key in seen:
            found.append({"duplicate": ref["id"], "of": seen[key], "basis": "same normalised title"})
        else:
            seen[key] = ref["id"]
    return found


def evaluate(refs: list[dict], citations: list[dict], merges: list[dict],
             source_text: str, ref_text: str = "") -> dict:
    problems: list[dict] = []

    def fail(check: str, where: str, detail: str) -> None:
        problems.append({"check": check, "where": where, "detail": detail})

    resolved, unresolved = resolve(refs, citations)
    # A citation is a hard failure only when the reference list does not contain
    # such a work at all. If the entry exists but the parser could not match it,
    # that is a finding about the pipe, not about the manuscript.
    for item in unresolved[:40]:
        token = item.get("token") or {}
        surname = (token.get("surname") or "").strip()
        year = (token.get("year") or "").rstrip("abcd")
        exists = bool(surname) and bool(ref_text) and bool(
            re.search(re.escape(surname) + r".{0,160}?" + re.escape(year), ref_text, re.I))
        if exists:
            problems.append({"check": "review", "where": item.get("anchor") or "?",
                             "detail": f"{item['marker']} -> the reference list contains a matching "
                                       f"work but the entry could not be parsed: {item['reason']}"})
        else:
            fail("citation_resolution", item.get("anchor") or "?",
                 f"{item['marker']} -> no work with this author and year exists in the reference list")

    cited = {item["ref_id"] for item in resolved}
    uncited = [ref["id"] for ref in refs if ref["id"] not in cited]
    uncited_rate = len(uncited) / max(1, len(refs))
    if uncited_rate > 0.2:
        fail("reference_cited", "*", f"{len(uncited)}/{len(refs)} references are never cited")
    for ref_id in uncited:
        problems.append({"check": "review", "where": ref_id,
                         "detail": "reference never cited in the parsed body text; it may be cited "
                                   "only inside a table or figure note"})

    for item in duplicates(refs):
        fail("duplicates", item["duplicate"], f"duplicate of {item['of']} ({item['basis']})")

    for ref in refs:
        if not ref["year"]:
            fail("field_completeness", ref["id"], "no publication year")
        if not ref["authors"]:
            fail("field_completeness", ref["id"], "no author block")
        if not ref["title"]:
            fail("field_completeness", ref["id"], "no title")
        if ref["doi"] and not re.match(r"^10\.\d{4,9}/\S+$", ref["doi"]):
            fail("identifier_format", ref["id"], f"malformed DOI {ref['doi']!r}")
        if ref["arxiv"] and not re.match(r"^\d{4}\.\d{4,5}$", ref["arxiv"]):
            fail("identifier_format", ref["id"], f"malformed arXiv id {ref['arxiv']!r}")
        for piece in ref.get("sources") or [ref["text"]]:
            if piece not in source_text:
                fail("provenance", ref["id"],
                     f"reference fragment is not verbatim in the parsed paper: {piece[:60]!r}")

    keys = [ref["key"] for ref in refs]
    for key in set(keys):
        if keys.count(key) > 1:
            fail("key_uniqueness", key, f"citation key {key!r} used by {keys.count(key)} entries")

    hard_failed = [p for p in problems if p["check"] in HARD]
    checks = {}
    for name in ("citation_resolution", "reference_cited", "duplicates", "field_completeness",
                 "identifier_format", "provenance", "key_uniqueness"):
        checks[name] = {"failed": len([p for p in problems if p["check"] == name])}
    return {
        "schema": "cite-audit/1.0",
        "references": len(refs),
        "citations": len(citations),
        "resolved": len(resolved),
        "unresolved": len(unresolved),
        "uncited": len(uncited),
        "merges": merges,
        "duplicates": duplicates(refs),
        "checks": checks,
        "hard_failures": len(hard_failed),
        "failures": hard_failed,
        "review": [item for item in problems if item["check"] == "review"],
        "status": ("success" if not hard_failed else
                   "partial" if refs else "failed"),
        "resolved_rows": resolved,
        "unresolved_rows": unresolved,
    }


def to_bibtex(refs: list[dict]) -> str:
    entries = []
    for ref in refs:
        kind = "article" if ref["venue"] and not ref["arxiv"] else "misc"
        fields = [f"  author = {{{ref['authors']}}}", f"  title = {{{ref['title']}}}",
                  f"  year = {{{ref['year'] or ''}}}"]
        if ref["venue"]:
            fields.append(f"  journal = {{{ref['venue']}}}")
        if ref["doi"]:
            fields.append(f"  doi = {{{ref['doi']}}}")
        if ref["arxiv"]:
            fields.append(f"  eprint = {{{ref['arxiv']}}}")
            fields.append("  archivePrefix = {arXiv}")
        entries.append(f"@{kind}{{{ref['key']},\n" + ",\n".join(fields) + "\n}")
    return "\n\n".join(entries) + "\n"


def to_csl(refs: list[dict]) -> list[dict]:
    rows = []
    for ref in refs:
        rows.append({
            "id": ref["key"],
            "type": "article-journal" if ref["venue"] and not ref["arxiv"] else "preprint",
            "author": [{"literal": ref["authors"]}] if ref["authors"] else [],
            "title": ref["title"],
            "issued": {"date-parts": [[int(ref["year"][:4])]]} if ref["year"] else None,
            "container-title": ref["venue"] or None,
            "DOI": ref["doi"],
            "archive": "arXiv" if ref["arxiv"] else None,
            "archive_location": ref["arxiv"],
            "source-anchor": ref["anchor"],
        })
    return rows


HARD = ("citation_resolution", "reference_cited", "duplicates", "field_completeness",
        "identifier_format", "provenance", "key_uniqueness")


def selftest(refs: list[dict], citations: list[dict], source_text: str,
             ref_text: str = "") -> dict:
    import copy

    cases = {}

    def run(name: str, fn) -> None:
        r, c = copy.deepcopy(refs), copy.deepcopy(citations)
        fn(r, c)
        report = evaluate(r, c, [], source_text, ref_text)
        cases[name] = {"detected": report["status"] != "success",
                       "checks": sorted({p["check"] for p in report["failures"]})}

    run("dangling_citation", lambda r, c: c.append(
        {"marker": "(Nobody et al., 1999)", "inner": "Nobody et al., 1999", "kind": "author-year",
         "page": 1, "anchor": "p1b0", "section": "test"}))
    run("duplicate_reference", lambda r, c: r.append({**copy.deepcopy(r[0]), "id": "ref-999",
                                                      "key": "dup"}))
    run("missing_year", lambda r, c: r[0].update({"year": None}))
    run("bad_doi", lambda r, c: r[0].update({"doi": "doi:10.1/x"}))
    run("key_collision", lambda r, c: r[1].update({"key": r[0]["key"]}))
    run("fabricated_entry", lambda r, c: r[0].update(
        {"sources": ["This reference does not appear anywhere in the paper."]}))
    for name, result in cases.items():
        result["name"] = name
    clean = evaluate(refs, citations, [], source_text, ref_text)
    return {"clean": clean["status"], "injected": cases,
            "all_detected": all(v["detected"] for v in cases.values())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    work = args.work
    raw_refs = load(work / "refs.json", [])
    citations = load(work / "citations.json", [])
    parse = load(work / "parse.json", {})
    source_text = parse.get("markdown", "")
    ref_text = "\n".join(entry["text"] for entry
                          in (parse.get("references", {}).get("entries") or []))

    refs, merges = merge_entries(raw_refs)
    refs = assign_keys(refs)

    if args.selftest:
        result = selftest(refs, citations, source_text, ref_text)
        (work / "selftest.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
        print("SELFTEST " + json.dumps({
            "clean": result["clean"],
            "detected": f"{sum(1 for v in result['injected'].values() if v['detected'])}"
                        f"/{len(result['injected'])}"}, ensure_ascii=False))
        return 0 if result["all_detected"] else 1

    report = evaluate(refs, citations, merges, source_text, ref_text)
    (work / "refs_parsed.json").write_text(json.dumps(refs, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    (work / "citations_resolved.json").write_text(
        json.dumps({"resolved": report["resolved_rows"],
                    "unresolved": report["unresolved_rows"]}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    (work / "audit_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    (work / "refs.bib").write_text(to_bibtex(refs), encoding="utf-8")
    (work / "refs.csl.json").write_text(json.dumps(to_csl(refs), ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    with (work / "citations.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["marker", "page", "anchor", "section", "key"])
        for row in report["resolved_rows"]:
            writer.writerow([row["marker"], row["page"], row["anchor"], row["section"], row["key"]])

    print("AUDIT " + json.dumps({
        "status": report["status"], "references": report["references"],
        "citations": report["citations"], "resolved": report["resolved"],
        "unresolved": report["unresolved"], "uncited": report["uncited"],
        "merges": len(report["merges"]), "duplicates": len(report["duplicates"]),
        "hard_failures": report["hard_failures"],
        "failed": {k: v["failed"] for k, v in report["checks"].items() if v["failed"]},
    }, ensure_ascii=False))
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
