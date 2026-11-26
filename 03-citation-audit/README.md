# Cite audit

Submission for **写作04｜参考文献与引用管理** (`product-arena-03-429cc14d`).

The deliverable is a skill, not a fixed bibliography. `submission/SKILL.md` is what
the platform installs; the scripts are the only programs it needs;
`src/reproduce.py` is the run that produced the evidence in `execution/`.

## What the skill does

The paper is parsed into reference blocks and in-text citation markers with page and
block anchors. The audit reassembles split entries, builds citation keys, resolves
every marker, reports what it cannot resolve, and exports the bibliography three
ways.

| Requirement | Mechanism |
|---|---|
| **对得上** | every marker resolves to a key; a citation whose work is absent from the list is a hard failure |
| **编得顺** | `surname+year` keys with `a`/`b` suffixing; a collision without a suffix fails |
| **收得净** | fragments reassembled with a recorded reason, duplicates reported by normalised title |
| **格式可用** | `refs.bib`, `refs.csl.json`, `citations.csv` with anchors |

The distinction that makes the audit honest: a citation is a **hard failure** only
if its author+year appears nowhere in the reference-list text. If it appears there
but the parser could not build an entry from it, that is a finding about the tool,
with the marker and its anchor — not an accusation against the manuscript.

## Measured result (BERT, 16 pages)

| Metric | Value |
|---|---|
| Reference blocks extracted | 67 |
| Fragments reassembled | **13**, each with a recorded reason |
| Entries after merging | **54** |
| In-text citation groups | 72 |
| Citation tokens resolved | **74** |
| Unresolved, work exists in list | 2 (reported as findings with anchors) |
| Unresolved, dangling | **0** |
| Never-cited references | 7 (reported individually) |
| Duplicates | 0 |
| Hard failures | **0** (resolution, duplicates, completeness, identifiers, provenance, key uniqueness) |
| Exports | `refs.bib` (54 entries), `refs.csl.json`, `citations.csv` (74 rows) |
| Gate sensitivity | **6/6** injected defects detected |
| Runtime | 15 s local, no network |

The 13 fragments are the substantive result: a naive split leaves references like
`Rami Al-Rfou, …, Mandy` as an entry with no year and no journal, while the real
continuation sits in the next block. Reassembling them and recording why is what
makes the exports usable.

## Bundle map

| Path | What it is |
|---|---|
| `submission/SKILL.md` | skill definition installed under `/skills` |
| `submission/scripts/prepare.py` | reference blocks, citation markers, anchors |
| `submission/scripts/audit.py` | fragment merge, key assignment, resolution, checks, exports |
| `submission/scripts/run_case.py` | case-contract adapter → `result.json` |
| `submission/references/keys-and-fragments.md` | key rules and the merge policy |
| `submission/references/qa-rules.md` | the checks and the existence/matching distinction |
| `src/reproduce.py` | the run that produced everything below |
| `execution/run.log` | append-only log (mirrored at `run.log`) |
| `execution/results/` | refs, citations, audit report, exports, metrics, case result (mirrored at `results/`) |
| `trace/trace.jsonl` | typed steps with paired tool calls and artifact paths |
| `characterization.json` | what was measured |
| `bundle_validation.json` | local validation report |

## Honest limits

- Title and venue are split heuristically; a venue fragment can end up in the title.
  Every entry keeps its anchor so a reviewer can check the split.
- Citation matching is author+year; a paper citing by title only needs a manual pass.
- Uncited references may be cited only inside tables or figure notes, which the
  body-text scan does not treat as prose. The finding says exactly that.
- Identifiers are validated by shape only; the audit never resolves them over the
  network, so a well-formed wrong DOI passes.
- No OCR: scanned pages are reported unreadable rather than mined for entries.

## GitHub link

No public repository exists for this run, so `GITHUB_URL.txt` is not included and
the 5-point ecosystem bonus is forfeited rather than filled with a placeholder.

## Licence and reuse

The skill and scripts are released for reuse within this submission. The demo PDF
is an arXiv preprint (arXiv non-exclusive licence) and is not redistributed;
`manifest.data_sources` records its URI, size and SHA-256.
