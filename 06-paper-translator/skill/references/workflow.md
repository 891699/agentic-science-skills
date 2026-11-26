# Workflow

## 1. Choose the scope
A whole paper, one section, or a paragraph range. Scope is a `--pages` /
`--sections` / `--max-paragraphs` triple; keep it explicit so the result can be
compared with another run.

```bash
python scripts/prepare.py paper.pdf --out work --pages 1,2 --max-paragraphs 20
```

## 2. Read the prepared files
| File | Meaning |
|---|---|
| `work/segments.json` | the source paragraphs, each with `id`, `page`, `block`, `bbox`, `section`, `kind` |
| `work/glossary.json` | terms: `en`, `zh`, `count`, `pages`, `locked` |
| `work/batches/batch-NNN.json` | 3–4 segments plus the locked terms that appear in them, and the instruction block |
| `work/prompt.md` | the same instruction block for reference |

`locked: true` means the Chinese form is fixed and checked. `locked: false` means
the term was extracted from the paper but has no committed translation yet: fill
`zh` in `glossary.json` (and set `locked`) **before** translating, otherwise the
checker cannot enforce it.

## 3. Translate a batch
Send one batch per model turn: it carries the instruction block, the locked terms
and the exact source text. Append results to `translations.jsonl` as you go — a
partial file is useful, and the verifier reports which ids are still missing.

Context carry-over: the previous batch's last two segments are enough. The
glossary, not the chat history, is what keeps terminology stable.

## 4. Verify and iterate
```bash
python scripts/verify.py --work work          # exit 1 while anything hard fails
python scripts/verify.py --work work --selftest   # proves the checks fire
```
Fix the target, never the source, and never the numbers. Re-run until exit 0 or
until the remaining items are genuinely untranslatable; those go to `notes`.

## 5. Produce the case result
```bash
python scripts/run_case.py --case case.json --task task.md --pdf paper.pdf \
    --work work --out output
```
Outputs: `output/result.json` (contract fields + evidence + QA), `output/bilingual.md`
(side-by-side), `output/translation.md` (Chinese only, original paragraph order).

## Budget
A 10-paragraph page costs one `prepare` run (~2 s), 3 batches of translation, and
one verify per pass. The mechanical parts are local and free; only translation
consumes model turns.
