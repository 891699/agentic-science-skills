#!/usr/bin/env python3
"""Reference-list normalisation shared by the drafting pipeline.

The PDF splits some reference entries across text blocks and the author block of a
multi-author entry can start in one block and end in the next. Both problems make
the first author — and therefore the citation key — wrong, so the same
fragment-merge and key-assignment rules are applied here before anything is cited.
"""

from __future__ import annotations

import re

YEAR_RE = re.compile(r"\b(19|20)\d{2}[a-z]?\b")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
ARXIV_RE = re.compile(r"arXiv:\s*(\d{4}\.\d{4,5})(?:v(\d+))?", re.I)


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def surname_of(authors: str) -> str:
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
    split = re.split(r"\.\s+", after, maxsplit=1)
    title = split[0].strip() if split else after
    venue = split[1].strip() if len(split) > 1 else ""
    doi = DOI_RE.search(text)
    arxiv = ARXIV_RE.search(text)
    return {
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


def is_fragment(parsed: dict) -> bool:
    text = parsed["text"]
    return (parsed["year"] is None or text[:1].islower()
            or text[:1] in ",;}" or len(parsed["authors"]) < 3)


def merge_entries(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    merged: list[dict] = []
    merges: list[dict] = []
    pending: list[dict] = []
    for index, entry in enumerate(entries, start=1):
        parsed = parse_entry(entry)
        parsed["id"] = f"ref-{index:03d}"
        if is_fragment(parsed):
            pending.append(parsed)
            continue
        if pending:
            head = " ".join(item["text"] for item in pending)
            sources = [item["text"] for item in pending] + [parsed["text"]]
            combined = parse_entry({"text": head + " " + parsed["text"],
                                    "page": parsed["page"], "anchor": parsed["anchor"]})
            combined["id"] = parsed["id"]
            combined["sources"] = sources
            for item in pending:
                merges.append({"merged": item["id"], "into": parsed["id"],
                               "reason": "head fragment: the PDF placed the start of the entry "
                                         "in the previous text block"})
            pending = []
            merged.append(combined)
        else:
            parsed["sources"] = [parsed["text"]]
            merged.append(parsed)
    if pending and merged:
        target = merged[-1]
        text = target["text"] + " " + " ".join(item["text"] for item in pending)
        sources = target["sources"] + [item["text"] for item in pending]
        for item in pending:
            merges.append({"merged": item["id"], "into": target["id"],
                           "reason": "trailing fragment: no complete entry follows"})
        rebuilt = parse_entry({"text": text, "page": target["page"], "anchor": target["anchor"]})
        rebuilt["id"] = target["id"]
        rebuilt["sources"] = sources
        merged[-1] = rebuilt
    return merged, merges


def assign_keys(works: list[dict]) -> list[dict]:
    counts: dict[tuple[str, str], int] = {}
    for work in works:
        base = (norm(work["surname"]), work["year"] or "")
        counts[base] = counts.get(base, 0) + 1
    seen: dict[tuple[str, str], int] = {}
    for work in works:
        base = (norm(work["surname"]), work["year"] or "")
        if counts[base] > 1:
            seen[base] = seen.get(base, 0) + 1
            work["key"] = f"{work['surname'].lower()}{work['year'] or 'nd'}{chr(96 + seen[base])}"
            work["key_suffix"] = chr(96 + seen[base])
        else:
            work["key"] = f"{work['surname'].lower()}{work['year'] or 'nd'}"
            work["key_suffix"] = ""
    return works
