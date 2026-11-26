#!/usr/bin/env python3
"""Assemble claims.json from the drafted markdown and an evidence mapping.

The prose lives in ``intro.md`` / ``related.md``; the evidence lives in a mapping
file whose entries are positional. This script zips them by sentence, so a draft
sentence can never end up without a mapping (or a mapping without a sentence) — the
two files cannot drift apart silently.

Usage:
    python assemble.py --work WORK [--mapping WORK/mapping.json]

Outputs:
    claims.json   units with id, bucket, role, text (from the markdown), evidence
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from verify_draft import md_sentences  # noqa: E402


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=Path("work"))
    ap.add_argument("--mapping", type=Path, default=None)
    args = ap.parse_args(argv)

    work = args.work
    mapping = load(args.mapping or (work / "mapping.json"), {})
    files = {"intro_md": work / "intro.md", "related_md": work / "related.md"}
    sentences = {}
    for key, path in files.items():
        if not path.exists():
            print("ASSEMBLE_FAIL " + json.dumps({"missing": str(path)}))
            return 2
        sentences[key] = md_sentences(path.read_text(encoding="utf-8"))

    problems = []
    buckets = {"intro": [], "related": [], "contributions": []}
    counters = {"intro": 0, "related": 0, "contributions": 0}
    prefixes = {"intro": "I", "related": "R", "contributions": "C"}

    for file_key in ("intro_md", "related_md"):
        entries = mapping.get(file_key) or []
        if len(entries) != len(sentences[file_key]):
            problems.append({"file": file_key, "mapping": len(entries),
                             "sentences": len(sentences[file_key]),
                             "detail": "the mapping and the draft disagree on sentence count"})
            continue
        for sentence, entry in zip(sentences[file_key], entries):
            bucket = entry.get("bucket") or ("related" if file_key == "related_md" else "intro")
            counters[bucket] += 1
            unit = {
                "id": f"{prefixes[bucket]}{counters[bucket]}",
                "bucket": bucket,
                "text": sentence,
                "evidence": entry.get("evidence") or [],
            }
            for field in ("role", "group", "note", "maps_to"):
                if entry.get(field) is not None:
                    unit[field] = entry[field]
            buckets[bucket].append(unit)

    claims = {
        "schema": "intro-draft/claims/1.0",
        "paper_authors": mapping.get("paper_authors") or [],
        "groups": mapping.get("groups") or [],
        "intro": buckets["intro"],
        "related": buckets["related"],
        "contributions": buckets["contributions"],
    }
    (work / "claims.json").write_text(json.dumps(claims, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    summary = {"intro": len(buckets["intro"]), "related": len(buckets["related"]),
               "contributions": len(buckets["contributions"]),
               "sentences": {k: len(v) for k, v in sentences.items()},
               "problems": problems}
    (work / "assemble_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                                encoding="utf-8")
    print("ASSEMBLE_OK " + json.dumps(summary, ensure_ascii=False))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
