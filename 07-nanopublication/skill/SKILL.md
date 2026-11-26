---
name: paper-nanopub
description: "Turn a paper's key claims into claim-level nanopublications: atomic subject-relation-object assertions, each bound to the sentence that supports it, with a provenance graph that reaches the paper and a content-addressed URI. Trigger on: nanopublication, nanopub, 纳米出版, RDF claim export, assertion extraction, 断言拆解, evidence binding, 'make these claims machine-readable', 'split this into assertions', 'link claims to the paper', TriG export."
---

# Paper Nanopub

A summary loses the link to its evidence. This skill produces the opposite: one
nanopublication per claim, each with a single checkable assertion, the exact
sentence that supports it, and provenance that leads back to the paper.

## What it guarantees

| Topic requirement | Mechanism |
|---|---|
| **拆得细** atomic | one subject, one relation from a controlled vocabulary, one object; the validator rejects compound objects and unknown relations |
| **对得上** minimal evidence | every assertion references a candidate sentence extracted from the PDF, and the validator requires that quote to occur verbatim in the parsed paper |
| **追得回** full chain | the provenance graph carries title, authors, year, arXiv/DOI, the file's SHA-256, page, block and anchor; the publication-info graph carries creator, date, licence, version |
| **读得懂** machine-readable | TriG with the four nanopublication graphs; validated by rdflib when installed, and by the built-in reader otherwise |

The nanopublication URI is **content-addressed**: a SHA-256 over the assertion,
the evidence and the source metadata (the creation timestamp is excluded). Re-run
on the same assertion and the URI is identical; change the claim and the URI
changes. The validator recomputes it, so a hand-edited TriG fails.

## Run it

Paths are relative to **this skill's own directory**. `cd` there first or use
absolute paths.

```bash
# 1. outline, quotable candidates, source metadata (arXiv/DOI, sha256)
python scripts/prepare.py PAPER.pdf --out WORK --max-sentences 8

# 2. author WORK/assertions.json against candidate ids (contract below)

# 3. emit TriG and validate
python scripts/emit_nanopub.py --work WORK
python scripts/validate_nanopub.py --work WORK
python scripts/validate_nanopub.py --work WORK --selftest   # proves the checks fire

# 4. apply the case contract
python scripts/run_case.py --case /input/case.json --task /input/task.md \
    --pdf PAPER.pdf --work WORK --out /app/output
```

Without `assertions.json` the case step stops with `blocked_on_assertions` and
reports how many candidates exist — it never invents a claim.

## Assertion contract

```json
{"id": "A03", "subject": "BERT", "relation": "reports-score",
 "object": "GLUE score 80.5%",
 "qualifiers": {"benchmark": "GLUE", "absolute_improvement": "7.7"},
 "claim": "BERT 在 GLUE 上报告 80.5% 的分数。",
 "quote_id": "p1b5:s1", "evidence_kind": "direct", "confidence": "high",
 "section": "Abstract"}
```

Rules:

1. **One relation, ten allowed** (`vocab/relations.json`): `reports-score`,
   `outperforms`, `uses-method`, `trained-on`, `requires-condition`,
   `has-limitation`, `improves-on`, `compared-with`, `part-of`, `causes`.
   Direction is subject → object; an inverse relation is not a relation.
2. **Atomic object.** No `and` / `、` / `；` inside subject or object. "lower on
   QNLI, MNLI and SQuAD" is three assertions, each with one benchmark.
3. **`quote_id` is a candidate id**, never a typed quote; the emitter copies the
   sentence from `candidates.json`.
4. **`evidence_kind`** is `direct` (the sentence states it) or `indirect` (the
   sentence supports it by inference); `confidence` is `high`/`medium`/`low`.
5. **Conditions belong in qualifiers**, not in the object: a claim that is true
   only under a budget or an assumption keeps that in `qualifiers`.
6. **One assertion per claim.** Splitting a compound claim is the main work of
   this skill, not an afterthought.

## What the validator checks

| Check | Hard? | Fails when |
|---|---|---|
| `trig_parse` | yes | the TriG does not parse |
| `structure` | yes | a nanopublication lacks its head link or one of the three graphs |
| `assertion_atomic` | yes | missing or repeated subject/relation/object, unknown relation, compound value, value over 200 chars |
| `evidence_verbatim` | yes | the quote is absent from the parsed paper, the anchor is malformed, or the anchor does not match the quoted sentence |
| `provenance_chain` | yes | missing creator/used/source title/sha256/evidence fields, or the source URI does not name the arXiv id |
| `pubinfo_complete` | yes | missing creator, created, licence or version |
| `uri_integrity` | yes | the URI hash does not recompute from assertion + evidence + source |
| `no_duplicates` | yes | two nanopublications with the same subject-relation-object |
| `coverage` | yes | fewer than 8 nanopublications or fewer than 5 sections represented |

`--selftest` injects seven defects (missing provenance graph, compound assertion,
evidence not in the source, duplicate assertion, hash mismatch, missing creator,
unknown relation) and requires each to be caught.

## Handling failures

| Situation | Action |
|---|---|
| a claim has no quotable sentence | drop it or mark `indirect` against the nearest supporting sentence; do not assert it |
| the paper only reports a number in a table | quote the caption that names the table, or record it as a qualifier with `evidence_kind: indirect` |
| two claims share one sentence | that is allowed; they must still differ in subject/relation/object |
| the relation you want is not in the vocabulary | pick the closest allowed relation and put the nuance in qualifiers; do not invent a relation |
| scanned PDF | the parser reports unreadable pages; emit nothing for them and return `partial` |
| a claim is contested in the paper itself | keep it with `confidence: medium` and say so in qualifiers |

## Limits to state in an answer

- Assertions are the model's reading; the skill guarantees the quote, the anchor
  and the hash, not the interpretation.
- The relation vocabulary is small and generic on purpose; domain ontologies can
  be added in `vocab/relations.json` without touching the code.
- The URI is content-addressed in the Trusty-URI **spirit**, not byte-compatible
  with the official nanopublication library.
- Numbers that appear only in table bodies are qualifiers with `indirect`
  evidence, not direct quotes.

See `references/` for the workflow, the assertion rules and the QA rules.
