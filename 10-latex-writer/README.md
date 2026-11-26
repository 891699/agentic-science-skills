# LaTeX writer

Submission for **写作13｜LaTeX 写作与编译** (`product-arena-07-865de7e4`).

The deliverable is a skill, not a paper. `submission/SKILL.md` is what the platform
installs; the scripts are the only programs it needs; `src/reproduce.py` is the run
that produced the evidence in `execution/`.

## What the skill does

A content spec is emitted into a LaTeX project, compiled with real `pdflatex`, and the
log is classified into categories. Mechanical failures are repaired, the project is
compiled again, and the whole sequence is recorded round by round. The demo project
starts with three defects on purpose, so the loop has something to find.

| Requirement | Mechanism |
|---|---|
| **能编译** | success requires a PDF, no `!` error, no unresolved reference or citation, and a clean static check |
| **改对** | five mechanical repair classes: package declaration, special escaping, column widening, BibTeX, `tlmgr install` |
| **不猜** | undefined references and overfull boxes are reported with the log excerpt, never rewritten |
| **可复核** | `build_report.json` keeps every round: errors, categories, repairs, excerpt |
| **静默丢失** | an unescaped `%` is an error even though the log stays silent |

## Measured result

| Metric | Value |
|---|---|
| Engine | pdfTeX 3.141592653-2.6-1.40.29 (TeX Live 2026, TinyTeX) |
| Project | `main.tex` + `sections/body.tex` + `refs.bib`, 3 sections, 1 table, 1 equation, 8 references |
| Defects injected | 3 — missing `booktabs`, table column spec `{lr}` against a 4-cell row, unescaped `%` swallowing a sentence |
| Static findings before | **5 errors** across 3 categories |
| Build rounds | **2** |
| Repairs applied | **3** (`\usepackage{booktabs}`, escape specials in `main.tex`, column spec `{lr}` → `{lrrr}`), plus BibTeX on the undefined citations |
| Static findings after | **0** |
| Compiled PDF | **110,633 bytes** |
| Baseline (same project, no repair loop) | **failed**: 7 log errors, 2 unresolved citations, 4 static errors |
| Wall time | **2.7 s** |

The baseline is the honest comparison: the same sources, compiled once, fail. The loop
is what turns them into a document.

## What the evidence looks like

`build_report.json`, one round:

```json
{"round": 1, "exit": 0, "errors": 0,
 "unresolved": ["Citation taylor1953", "Citation devlin2019"],
 "categories": ["undefined_citation"],
 "repairs": ["preamble: add \\usepackage{booktabs}",
             "escape specials in main.tex",
             "table: body.tex: 2 -> 4 columns"],
 "bibtex": {"available": true, "exit": 0}}
```

## Bundle map

| Path | What it is |
|---|---|
| `submission/SKILL.md` | skill definition installed under `/skills` |
| `submission/scripts/emit_latex.py` | content spec → `.tex` project, with defect injection for the demo |
| `submission/scripts/check_tex.py` | static linter (11 finding categories) |
| `submission/scripts/build_loop.py` | compile → classify → repair → recompile, recorded per round |
| `submission/scripts/run_case.py` | case adapter → `result.json`, `main.tex`, `main.pdf` |
| `submission/references/repair-playbook.md` | each failure with its log line and its repair |
| `submission/references/qa-rules.md` | success conditions, repair policy, round accounting |
| `src/reproduce.py` | the run that produced everything below |
| `execution/run.log` | append-only log (mirrored at `run.log`) |
| `execution/results/` | project, build report, checks before/after, baseline, metrics, case output (mirrored at `results/`) |
| `trace/trace.jsonl` | typed steps with paired tool calls and artifact paths |
| `characterization.json` | what was measured |
| `bundle_validation.json` | local validation report |

## Honest limits

- The emitter writes an `article` skeleton. A publisher template with a custom class
  needs its class file; the loop then operates on the author's `main.tex`.
- Repairs are mechanical by design; anything that changes meaning stays in the report.
- Overfull boxes are counted, not fixed.
- The linter catches wrong syntax, not wrong numbers.
- The demo's defects are injected so the loop can be measured end to end; on real input
  the same categories appear from the author's own edits.

## GitHub link

`GITHUB_URL.txt` points at `https://github.com/891699/agentic-science-skills`, folder
`10-latex-writer`.

## Licence and reuse

The emitter, linter, repair playbook and build report format are released for reuse
within this submission. The demo content is written for this run; no third-party paper
is redistributed.
