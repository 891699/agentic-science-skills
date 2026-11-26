# QA rules

## What counts as a successful build

Three conditions, all required:

1. the engine exits 0 and `main.pdf` exists and is non-empty;
2. the log contains no line starting with `!` and no `Reference ... undefined` or
   `Citation ... undefined`;
3. the static checker reports zero errors after the repairs.

The third condition exists because a project can compile while still being wrong: a
silent comment compiles, a duplicated label compiles, a reference to a label that was
deleted compiles into `??`.

## Error categories and their evidence

| Category | Which log line proves it | Repairable |
|---|---|---|
| `missing_package_file` | `File \`x.sty' not found` | yes |
| `undefined_command` | `Undefined control sequence` | yes, when mapped |
| `undefined_citation` | `Citation ... undefined` | yes, via BibTeX |
| `undefined_ref` | `Reference ... undefined` | no |
| `table_columns` | `Extra alignment tab` | yes |
| `math_mode` | `Missing $ inserted` | partially |
| `runaway_argument` | `Runaway argument` | no |
| `overfull_hbox` | `Overfull \hbox` | no |
| `silent_comment` | static check only | yes |

## Repair policy

A repair is applied only when the intended result is unambiguous:

- **escape a special** — `%`, `#` in text always mean the literal character;
- **declare a package** — the command's package is known and the package exists;
- **widen a column spec** — the data decides the number of columns;
- **run BibTeX** — the key exists in the `.bib`;
- **install a package** — only when `tlmgr` is available.

Everything else is reported with its log excerpt. A wrong automatic repair is worse
than a reported error, because it hides the problem behind a green build.

## Round accounting

`build_report.json` records, per round: exit code, compile time, error count, the
unresolved references and citations, the overfull count, the categories, the repairs
applied and the first five error lines. The final block repeats the same fields for
the last compile. A reader can therefore reconstruct the sequence without the log.

## Static checks that catch what the log cannot

- `silent_comment` — the `%` failure produces no log line at all;
- `duplicate_label` — compiles, but `\ref` picks one of the two;
- `undefined_ref` before the second pass;
- `missing_package` — a command used but its package never declared;
- `table_columns` — a mismatch that some TeX versions silently pad.

## Baseline

The run compiles the same defective project once with no repairs. That arm fails with
the raw error set; the difference between it and the repaired arm is the measured value
of the loop, not a claim about it.
