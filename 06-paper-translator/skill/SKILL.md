---
name: paper-translator
description: "Translate a scientific paper into Chinese with a locked glossary, paragraph-level alignment and a mechanical quality gate. Trigger on: translating a paper or abstract, 文献翻译, 翻译这篇论文, bilingual 对照, glossary consistency, 'translate section 2', 'keep the terminology consistent', 'make a bilingual version', 'check this translation against the source'. Use it whenever a translation must stay verifiable against the original: numbers, citations, formulas, negation and paragraph ids preserved."
---

# Paper Translator

Translate a paper so the result can still be checked against the original: one
record per source paragraph, a glossary that is enforced rather than suggested,
and a verifier that fails loudly when the translation stops matching the paper.

The topic names four failures. This skill addresses each with a mechanism, not a
promise:

| Requirement | Mechanism |
|---|---|
| **术语稳** terminology locked | `glossary.json` carries `locked` entries with a fixed Chinese form; `verify.py` fails any segment where a locked source term is not rendered with its locked target |
| **段落全** no missing paragraphs | segments come from the PDF's own blocks with ids `p<page>b<block>`; the verifier compares id sets both ways, so a dropped, duplicated or invented paragraph is a hard failure |
| **关系准** relations intact | the verifier compares numeric values, citation markers, formula tokens, negation markers and hedging words between source and target |
| **可核验** traceable | every target paragraph keeps its page, block and bbox; the QA report names the failing id, the check and the detail |

## When to use it

Use it for any paper or section that has to be translated and then trusted:
abstracts, methods, results, figures and table captions, related work. Do not
translate straight from a text dump and call it done — that loses the paragraph
mapping that makes the result checkable.

## Run it

Paths are relative to **this skill's own directory** (the loader reports it as the
resource base, e.g. `/skills/weekly-skill`). `cd` there first, or use absolute
paths.

```bash
# 1. Segment the paper and build the glossary skeleton
python scripts/prepare.py PAPER.pdf --out WORK \
    --max-paragraphs 40 --glossary glossary/seed-ml-zh.csv

# 2. Translate batches/ into WORK/translations.jsonl (one JSON object per line)
#    The batch file carries the instruction block and the locked terms for it.

# 3. Verify, then apply the case contract
python scripts/verify.py --work WORK
python scripts/run_case.py --case /input/case.json --task /input/task.md \
    --pdf PAPER.pdf --work WORK --out /app/output
```

`run_case.py` writes `result.json` with the bilingual pairs, the glossary, the QA
report, the evidence anchors and an honest status. Without `translations.jsonl`
it stops with `blocked_on_translation` and lists the batches to do — it never
invents a target text.

## Translation contract

For each segment id in `batches/batch-NNN.json`, append one line to
`translations.jsonl`:

```json
{"id": "p1b4", "target": "……中文译文……", "terms": ["pre-training"], "notes": ""}
```

Rules, in priority order:

1. **One object per id, same order.** Never merge, split, reorder, drop or add ids.
2. **Locked terms use their locked `zh` form exactly.** If a locked term is wrong
   for the context, still use it and explain in `notes` — the glossary is the
   contract, and a drift must be visible rather than silent.
3. **Keep verbatim:** citation markers such as `[12]` and `(Devlin et al., 2019)`,
   numeric values and units, section numbers, formula tokens, figure/table labels.
   Full-width parentheses around a citation are accepted; the inner text is not.
4. **Keep negation and hedging:** `not/no/never/without` → 不/无/未/非/没, and
   `may/can/only/should` → 可能/可以/仅/只/应该. A dropped 可能 or 仅 changes the claim.
5. **Academic Chinese, no additions.** Translate every clause; add no explanation
   and omit nothing. A translator note goes in `notes`, never into the target.
6. **Uncertain? Say so.** If the source is ambiguous or corrupt, translate what is
   there and put the doubt in `notes`; the verifier carries `notes` into the
   review queue.

## What the verifier checks

| Check | Hard? | What fails it |
|---|---|---|
| `coverage` | yes | missing, duplicate or unknown segment id; unparsable line |
| `glossary_lock` | yes | a locked source term whose locked Chinese form is absent |
| `numbers` | yes | a numeric value from the source missing in the target |
| `citations` | yes | a citation marker not preserved (inner text, not brackets) |
| `formula_tokens` | yes | an `a = b` style token dropped |
| `negation` | yes | source negates and target has no negation marker |
| `hedge` | yes | source hedges/restricts and target has no modal or restriction word |
| `untranslated` | yes | no Chinese characters, or target identical to source (bylines exempt) |
| `placeholder` | yes | `TODO`/`TBD`/`<…>`/`???` in the target |
| `length_ratio` | no | target shorter than 12% or longer than 100% of the source |

Exit code 0 means every hard check passed; 1 means at least one did not, and the
report names the ids. `verify.py --selftest` proves the checks fire: it injects
term drift, a lost number, a lost citation, lost negation, lost hedging, an
untranslated segment and a placeholder, and requires each to be caught.

## Handling failures

| Situation | Action |
|---|---|
| no text layer (scanned PDF) | the parser reports `unreadable_pages`; translate what exists and return `partial`, naming the pages |
| a locked term is clearly wrong for the context | keep the locked form, explain in `notes`, and propose the change in the review queue — do not silently drift |
| a paragraph fails `numbers` | re-read the source block; never "fix" the number in the target |
| `coverage` fails with missing ids | the batch was truncated; retranslate that batch rather than the whole paper |
| source mixes languages or has broken hyphenation | translate as printed, note it, and let the review queue carry it |
| table cells | translate `tables[].grid` cell by cell and keep the grid shape; never flatten a table into prose |

## Limits to state in an answer

- Translation quality is the model's; this skill guarantees **structure and
  fidelity checks**, not literary quality.
- The glossary covers the terms it lists; a term absent from the glossary is
  translated freely and is not checked.
- The verifier is heuristic on hedging and negation: it proves a marker survived,
  not that the scope is identical. Scope doubts belong in the review queue.
- Formulas are compared as glyph strings; mathematical equivalence is not checked.

See `references/` for the workflow, the glossary format, the QA rules and a
worked example.
