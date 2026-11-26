---
name: cite-audit
description: "Audit a paper's reference list against its in-text citations and export a clean bibliography: parse entries, reassemble fragments the PDF split apart, build citation keys, resolve every marker, find dangling citations, duplicates and malformed identifiers, then emit BibTeX, CSL-JSON and a citation CSV. Trigger on: reference list check, 参考文献, citation audit, 引用管理, bibliography cleanup, dangling citation, BibTeX export, CSL-JSON, 'check the references', 'are all citations defined', 'convert to BibTeX', 'dedupe the bibliography'."
---

# Cite Audit

## Requirements

- Python 3.10 or newer.
- PyMuPDF for PDF access: `pip install pymupdf==2.0` (the Docker image pins the same version).
- No other dependencies; the run needs no network access.


A bibliography can look fine and still be wrong: a citation pointing at nothing, a
duplicate entry under two titles, a year that lost its letter. This skill compares
the two halves of the paper — the in-text markers and the reference list — and
exports a bibliography that another tool can load without cleanup.

## What it guarantees

| Requirement | Mechanism |
|---|---|
| **挂得对 / 对得上** citations resolve | every in-text marker is parsed into author-year tokens and matched to a key; a citation whose work does not exist in the list is a hard failure |
| **编得顺** keys are stable and unique | keys are `surname+year`, with `a`/`b` suffixes when two works share both; a collision without a suffix fails |
| **收得净** fragments and duplicates | reference blocks the PDF split are reassembled with a recorded reason; duplicate titles are reported |
| **格式可用** exports | BibTeX, CSL-JSON and a citation CSV with page/block anchors |

**Existence is judged on the reference-list text, not on the parser.** A citation
whose work appears in the list but whose entry could not be parsed is a *finding*
about the tooling; a citation whose work does not appear at all is a *defect in the
manuscript*. The audit keeps those apart instead of blaming the author for a parser
miss.

## Run it

Paths are relative to **this skill's own directory**. `cd` there first or use
absolute paths.

```bash
python scripts/prepare.py PAPER.pdf --out WORK          # refs + citations + anchors
python scripts/audit.py --work WORK                     # parse, merge, resolve, export
python scripts/audit.py --work WORK --selftest          # proves the checks fire
python scripts/run_case.py --case /input/case.json --task /input/task.md \
    --pdf PAPER.pdf --work WORK --out /app/output
```

## What the audit produces

| File | Content |
|---|---|
| `refs_parsed.json` | entries: key, authors, surname, year, title, venue, DOI, arXiv, anchor, source fragments |
| `citations_resolved.json` | every marker with the key it resolves to, plus the unresolved list |
| `audit_report.json` | checks, duplicates, merges, review queue |
| `refs.bib` | BibTeX with stable keys |
| `refs.csl.json` | CSL-JSON for reference managers |
| `citations.csv` | marker, page, anchor, section, key |

## What the audit checks

| Check | Hard? | Fails when |
|---|---|---|
| `citation_resolution` | yes | a citation's author+year does not occur anywhere in the reference-list text |
| `reference_cited` | over 20% | more than a fifth of the references are never cited in the body |
| `duplicates` | yes | two entries share a normalised title |
| `field_completeness` | yes | an entry has no authors, no year or no title |
| `identifier_format` | yes | a DOI or arXiv id does not match the expected shape |
| `provenance` | yes | an entry (or one of its source fragments) is not verbatim in the parsed paper |
| `key_uniqueness` | yes | two entries share a citation key |

Merges, unresolved-but-existing citations and uncited references are reported in
`audit_report.json.review` — findings, not failures, each with its anchor.

## Handling failures

| Situation | Action |
|---|---|
| a reference has no year in the PDF | it is almost always a fragment: check whether the next block carries the year and merge it, recording why |
| two works share surname and year | the citation needs a/b; if the marker lacks it, report the ambiguity rather than picking one |
| a citation has no matching entry | check the reference-list text before declaring it dangling — it may be a parse gap |
| a DOI is truncated | report the entry; do not reconstruct a DOI from memory |
| the paper uses numbered citations | the same pipeline works: bracket markers resolve by number, keys stay `surname+year` |
| scanned PDF | the parser reports unreadable pages; do not invent entries for them |

## Limits to state in an answer

- Entry fields come from the PDF text; a title/venue split is heuristic and can put
  a venue fragment in the title. The anchor lets a reviewer check any entry.
- Citation matching is author+year; a paper that cites by title only needs a manual
  pass.
- Uncited references may be cited in a table or figure note that the parser did not
  read as prose — the finding says so explicitly.
- No network: identifiers are validated by shape, not by resolving them.

## When to use

Use it when a bibliography has to reconcile with the text: every in-text marker resolves to
an entry, split entries are merged, and the result exports to BibTeX / CSL-JSON / CSV.

- **Input**: one PDF.
- **Output**: `refs_parsed.json`, `citations_resolved.json`, `audit_report.json` and exports.
- **Do not use** it to invent an entry for a dangling citation; that is reported as a defect.

## Minimal example

Input: a 6-page paper at `input/paper.pdf`.

```bash
python scripts/prepare.py input/paper.pdf --out work
python scripts/audit.py --work work
python scripts/audit.py --work work --selftest
```

示意输出（示例，非正式答案）:

```json
{"status": "success", "references": 54, "citations": 72, "resolved": 74,
 "unresolved": 2, "uncited": 7, "merges": 13, "hard_failures": 0}
```

Illustrative only; the counts come from the demo paper used in this run.

See `references/` for the key rules and the QA rules.
