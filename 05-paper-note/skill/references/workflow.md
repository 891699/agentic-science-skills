# Workflow

## 1. Prepare
```bash
python scripts/prepare.py paper.pdf --out work --max-sentences 8
```
| File | Meaning |
|---|---|
| `work/parse.json` | full parse: sections, paragraphs, tables, figures, anchors |
| `work/segments.json` | the paper's outline as the note must follow it: section, level, number, page, heading anchor |
| `work/candidates.json` | quotable sentences: `id` (`p3b12:s2`), `anchor`, `page`, `block`, `section`, `text`, and what it contains (numbers, citations, keywords) |
| `work/prepare_summary.json` | counts, so you can see the scope before writing |

Candidates are filtered to sentences that carry a number, a citation or a
method/claim keyword, and capped per section. If a section has no candidates, it
gets a role line only — that is expected in references and appendix sections.

## 2. Write the note
Open `candidates.json` and write `notes.json` against it. Work section by section
in the paper's order:

1. card first — it forces you to decide the research question, the data, the
   method and the conditions before summarising results;
2. then the argument sections (abstract, introduction, method, main results,
   ablation, conclusion), 1–3 claims each;
3. then one role line for everything else.

Two habits make the note much better:
- put the **condition** in the claim when the quote has one ("在单块 TPU、1 小时内"), rather than in a separate sentence;
- prefer the sentence that states the finding over the sentence that announces it.

## 3. Verify
```bash
python scripts/verify_notes.py --work work            # exit 1 while anything hard fails
python scripts/verify_notes.py --work work --selftest # proves the checks fire
```
Read the `failures` array: each entry says which check, which claim (`where`) and
why. Fix the note, not the source. Iterate until exit 0.

## 4. Produce the case result
```bash
python scripts/run_case.py --case case.json --task task.md --pdf paper.pdf \
    --work work --out output
```
Outputs:
- `output/result.json` — card, section notes, evidence anchors, coverage, QA;
- `output/note.md` — the same note rendered as a readable document, quotes inline.

## 5. Reuse
`result.json` is diffable across papers: the card keys are fixed, every claim is a
`{claim, quote_id, quote, page, anchor}` record. Comparing two papers is comparing
two cards and matching anchors; nothing needs re-reading.
