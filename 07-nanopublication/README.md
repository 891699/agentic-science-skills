# Paper nanopub

Submission for **阅读14｜Nanopublication** (`product-arena-09-0e8befd4`).

The deliverable is a skill, not a finished set of nanopublications.
`submission/SKILL.md` is what the platform installs; the scripts are the only
programs it needs; `src/reproduce.py` is the run that produced the evidence in
`execution/`. The platform's three fixed cases are supplied at evaluation time.

## What the skill does

The paper is parsed into sections and quotable sentences. The agent writes atomic
assertions against those sentences; the emitter turns each assertion into a
nanopublication; the validator re-checks structure, atomicity, evidence, provenance
and hash before anything is exported.

| Topic requirement | Mechanism |
|---|---|
| **拆得细** atomic | one subject / one relation from a ten-entry controlled vocabulary / one object; compound objects are rejected |
| **对得上** minimal evidence | every assertion references a candidate sentence; the validator requires it verbatim in the parsed paper and checks the anchor |
| **追得回** full chain | provenance carries title, authors, year, arXiv id, file SHA-256, page, block, anchor; publication info carries creator, date, licence, version |
| **读得懂** machine-readable | TriG with the four nanopublication graphs, parsed with rdflib, plus `result.json` |

The URI is content-addressed: SHA-256 over assertion + evidence + source metadata,
timestamp excluded. Re-running is idempotent; editing a triple breaks the URI and
the validator says so.

## Measured result (BERT → TriG nanopublications)

| Metric | Value |
|---|---|
| Source | arXiv 1810.04805v2, 16 pages, SHA-256 recorded |
| Quotable candidates | 131 |
| Nanopublications | **18** |
| Sections represented | **7** (Abstract, Introduction, BERT, Pre-training, Fine-tuning, Pre-training Tasks, Model Size, Conclusion) |
| Relations used | 8 of the 10 in the vocabulary |
| TriG parse | **rdflib**, 0 syntax errors |
| Hard validation failures | **0** (structure, atomicity, verbatim evidence, provenance, pubinfo, hash, duplicates, coverage) |
| Gate sensitivity | **7/7** injected defects detected |
| First draft | 1 compound claim caught and split into three nanopublications (QNLI / MNLI / SQuAD 1.1); 1 object rewritten to remove "between … and" |
| Runtime | 16 s local, no network, no GPU |

The first-draft line is the point: a human would have accepted "removing NSP hurts
QNLI, MNLI and SQuAD 1.1" as one claim. The atomicity check refused it, and the
final set has three nanopublications that can each be true or false on their own.

## Bundle map

| Path | What it is |
|---|---|
| `submission/SKILL.md` | skill definition installed under `/skills` |
| `submission/scripts/prepare.py` | outline, candidates, source metadata |
| `submission/scripts/emit_nanopub.py` | assertion → TriG + content-addressed URI |
| `submission/scripts/validate_nanopub.py` | the nine checks (+ `--selftest`) |
| `submission/scripts/run_case.py` | case-contract adapter → `result.json` |
| `submission/vocab/relations.json` | the controlled relation vocabulary |
| `submission/references/` | workflow, assertion rules, QA rules |
| `src/reproduce.py` | the run that produced everything below |
| `execution/run.log` | append-only log (mirrored at `run.log`) |
| `execution/results/` | candidates, paper metadata, assertions, `nanopubs.trig`, QA, metrics, case result (mirrored at `results/`) |
| `trace/trace.jsonl` | typed steps with paired tool calls and artifact paths |
| `characterization.json` | what was measured against the source |
| `bundle_validation.json` | local validation report |

## Honest limits

- Assertions are the model's reading; the skill guarantees the quote, anchor and
  hash, not the interpretation.
- The relation vocabulary is small and generic; domain ontologies can be added
  without code changes.
- The content-addressed URI follows the Trusty-URI idea, not the official
  byte-compatible algorithm.
- Numbers that live only in table bodies are recorded as qualifiers with
  `indirect` evidence, not as direct quotes.
- No OCR: scanned pages are reported unreadable rather than asserted from.

## GitHub link

No public repository exists for this run, so `GITHUB_URL.txt` is not included and
the 5-point ecosystem bonus is forfeited rather than filled with a placeholder.

## Licence and reuse

The skill, vocabulary and scripts are released for reuse within this submission.
The demo PDF is an arXiv preprint (arXiv non-exclusive licence) and is not
redistributed; `manifest.data_sources` records its URI, size and SHA-256.
