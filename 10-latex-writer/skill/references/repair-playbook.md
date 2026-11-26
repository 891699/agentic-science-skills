# Repair playbook

Each entry is a failure the loop has seen, the evidence in the log, and the repair —
or the reason there is no automatic repair.

## Missing package file
```
! LaTeX Error: File `booktabs.sty' not found.
```
The distribution is minimal: TinyTeX-1 ships a few hundred packages, not all of TeX
Live. Two repairs, in order:

1. `tlmgr install booktabs` — installs the real package, keeps the source correct;
2. declare it in the preamble — the loop does this when the package turns out to be
   already present (an undeclared `\usepackage`).

Declaring a package the distribution does not have only moves the error, so the loop
tries the installer first when `tlmgr` exists.

## Undefined control sequence
```
! Undefined control sequence.
l.42     \toprule
```
Almost always an undeclared package (`\toprule` → `booktabs`, `\includegraphics` →
`graphicx`, `\checkmark` → `amssymb`). The loop maps the command to its package and
declares it. A genuinely misspelled macro is not repaired: the mapping does not fire
and the error stays.

## Undefined citation
```
LaTeX Warning: Citation `vaswani2017' on page 1 undefined
```
The `.bib` entry exists and BibTeX has not run: run `bibtex main`, then pdflatex twice.
If the key is absent from the `.bib`, the loop reports it — inventing a bibliography
entry would be worse than the warning.

## Table column mismatch
```
! Extra alignment tab has been changed to \cr.
```
The column spec declares fewer columns than a row uses. The loop reads the widest row
and rewrites the spec (`{lr}` → `{lrrr}`). Note the direction: it widens the spec to
match the data, because the data is what the table means.

## Silent comment
```latex
\noindent 100% of the runs used 4 TPUs.
```
No error, no warning: everything after `%` is a comment, so the rest of the sentence
is missing from the PDF. This is the most dangerous failure in the set and the static
checker reports it as an error, because the compile log cannot.

## Undefined reference
```
LaTeX Warning: Reference `tab:missing' on page 2 undefined
```
Left in the report. A missing label is either a removed table or a wrong reference, and
both need a human decision. The loop will not point the reference at a nearby label.

## Overfull box
```
Overfull \hbox (12.3pt too wide) in paragraph at lines 88--92
```
Counted and reported, not repaired. The fix is a phrasing or layout decision.

## Math mode
```
! Missing $ inserted.
```
Usually a stray `_` or `^` in text. The loop escapes `_` in text and reports the line
so the author can decide whether it was meant to be math.
