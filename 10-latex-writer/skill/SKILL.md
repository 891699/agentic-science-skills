---
name: latex-writer
description: "Build a LaTeX project that compiles: emit sources from a content spec, compile with pdflatex, classify every failure (missing package, undefined command, undefined citation, table column mismatch, silent comment), repair the mechanical ones, recompile, and report what stayed broken. Trigger on: LaTeX, compile, tex, 编译报错, undefined control sequence, missing package, bibtex, overfull hbox, 'make this compile', 'fix the LaTeX errors', 'why does my tex fail'."
---

# LaTeX Writer

## Requirements

- Python 3.10 or newer; the standard library only, no pip installs needed.
- A TeX distribution on `PATH` with `pdflatex` and `bibtex`; `texlive-latex-base`,
  `texlive-latex-recommended` and `texlive-latex-extra` are enough, and the Docker image
  installs exactly those. TinyTeX also works.


A `.tex` that looks right and does not compile is worth nothing. This skill closes the
loop: emit, compile, read the log, classify, repair, compile again — and keep the
evidence for every round.

## What it guarantees

| Requirement | Mechanism |
|---|---|
| **能编译** | the build loop stops only when the PDF exists, the log has no `!` error and no unresolved reference or citation |
| **改对** | every repair is one of a small set of mechanical transforms, recorded with the finding it fixed |
| **不猜** | undefined references and overfull boxes are reported, never silently rewritten |
| **可复核** | `build_report.json` keeps each round: errors, categories, repairs, and the log excerpt |
| **静默丢失** | an unescaped `%` that deletes a sentence is an error, because it produces no log line at all |

## Run it

Paths are relative to **this skill's own directory**. `cd` there first or use
absolute paths.

```bash
python scripts/emit_latex.py --content CONTENT.json --out PROJECT [--inject-defects]
python scripts/check_tex.py  --project PROJECT --json CHECK.json
python scripts/build_loop.py --project PROJECT --max-rounds 3
python scripts/run_case.py   --project PROJECT --out OUTPUT [--case CASE.json]
```

The engine is found on `PATH` or in a TinyTeX install; `build_loop.py` exits with
status 3 and a report when no engine exists, instead of pretending it compiled.

## What the loop classifies

| Log evidence | Category | Repair |
|---|---|---|
| `File \`x.sty' not found` | `missing_package_file` | declare the package; `tlmgr install` as a fallback |
| `Undefined control sequence` | `undefined_command` | map the command to its package (`\toprule` → `booktabs`) |
| `Reference ... undefined` | `undefined_ref` | report only |
| `Citation ... undefined` | `undefined_citation` | run BibTeX, then recompile |
| `Extra alignment tab` | `table_columns` | rewrite the column spec |
| `Missing $ inserted` | `math_mode` | report only |
| unescaped `%` in text | `silent_comment` | escape it; the text was being deleted without an error |
| `Overfull \hbox` | `overfull_hbox` | report only |

The distinction that matters: repairs are only applied where the intent is
unambiguous. An undefined reference could mean a missing label or a wrong number, so
the loop says so and stops.

## Static checks (`check_tex.py`)

Structure (`\documentclass`), package availability for the commands used, environment
nesting, brace balance, duplicate labels, undefined references, citation keys against
the `.bib`, `\includegraphics` targets, table column counts, math delimiter balance
and unescaped specials. These run before compiling and again afterwards: a project can
compile and still be wrong.

## Handling failures

| Situation | Action |
|---|---|
| no TeX engine | the run reports `no_engine` and the static checks still run; install TinyTeX and re-run |
| `x.sty` missing from a minimal distribution | the loop tries `tlmgr install x`, then the preamble declaration |
| citation undefined on the first pass | always run BibTeX and recompile twice; a first-pass warning is not a defect |
| undefined reference | add the label or fix the reference by hand; the loop will not invent a number |
| overfull box | report it; the fix is a design decision, not a mechanical one |
| text disappears with no error | suspect an unescaped `%`; the static check names the file and line |
| scanned or corrupt content | the emitter never invents text; missing sections are a content problem |

## Limits to state in an answer

- The emitter writes an `article` skeleton, not a publisher template. A template with a
  custom class needs its own class file and preamble; the loop then works on that file.
- Repairs are mechanical by design. Anything that changes meaning stays in the report.
- Overfull boxes are counted, not fixed.
- The static checker is a linter: it will not catch a wrong number, only wrong syntax.
- Fonts and CJK typesetting are out of scope unless the template already loads them.

See `references/repair-playbook.md` and `references/qa-rules.md`.

## When to use

Use it when a LaTeX project must actually compile: the loop classifies every failure, repairs
the mechanical ones, recompiles, and keeps what it could not fix in the report.

- **Input**: a content spec (or an existing project) and a TeX engine on `PATH`.
- **Output**: `.tex` sources, a compiled PDF, `build_report.json` and static checks.
- **Do not use** it to "fix" an undefined reference by pointing it elsewhere; that stays a
  report item because it is a decision, not a typo.

## Minimal example

Input: `data/content.json` with one section and one table.

```bash
python scripts/emit_latex.py --content content.json --out project --inject-defects
python scripts/check_tex.py  --project project --json check.json
python scripts/build_loop.py --project project --max-rounds 3
```

示意输出（示例，非正式答案）:

```json
{"status": "success", "rounds": 2,
 "repairs": ["preamble: add \usepackage{booktabs}",
             "escape specials in main.tex",
             "table: body.tex: 2 -> 4 columns"],
 "final": {"errors": 0, "unresolved": [], "pdf": true, "pdf_bytes": 110633}}
```

Illustrative only; the byte count belongs to the demo project.

