# Minimal invocation example

> **Example only.** The paper is a public preprint and the translation below is a
> two-paragraph illustration, not an official case result.

## Prepare

```bash
$ python scripts/prepare.py bert-2019.pdf --out work --pages 1 --max-paragraphs 6
PREPARE_OK {"segments": 6, "source_chars": 2688, "pages": [1],
            "sections": ["Abstract", "Introduction"], "glossary_terms": 26,
            "locked_terms": 21, "batches": 2}
```

`work/batches/batch-001.json` (abridged):

```json
{"batch": 1,
 "instructions": "Translate every segment below from English into Simplified Chinese. ...",
 "locked_terms": [{"en": "fine-tuning", "zh": "微调", "locked": true},
                  {"en": "token", "zh": "词元", "locked": true}],
 "segments": [{"id": "p1b4", "page": 1, "section": "Abstract",
               "text": "We introduce a new language representation model called BERT, ..."}]}
```

## Translate

`work/translations.jsonl`:

```json
{"id": "p1b4", "target": "我们提出一种新的语言表示模型 BERT，其全称为 Bidirectional Encoder Representations from Transformers（来自 Transformer 的双向编码器表示）。", "terms": ["pre-training", "encoder"], "notes": ""}
{"id": "p1b5", "target": "BERT 在概念上简单、在实证上强大。它在 11 项自然语言处理任务上取得了新的当前最优结果，……", "terms": ["state-of-the-art"], "notes": ""}
```

## Verify

```bash
$ python scripts/verify.py --work work
VERIFY {"status": "success", "coverage": 1.0, "hard_failures": 0,
        "checks": {}, "out": "work/qa_report.json"}
```

A failing run names the ids and the reason:

```bash
$ python scripts/verify.py --work work
VERIFY {"status": "partial", "coverage": 1.0, "hard_failures": 2,
        "checks": {"glossary_lock": 1, "citations": 1}, ...}
# qa_report.json → failures:
#   p1b4 | glossary_lock | inference must be translated as 推理
#   p1b7 | citations     | citation markers not preserved: ['(Dolan and Brockett, 2005)']
```

## Case result

```bash
$ python scripts/run_case.py --case case.json --task task.md --pdf bert-2019.pdf \
      --work work --out output
CASE_OK {"case_id": "demo-bert-abstract", "status": "success", "segments": 6,
         "translated": 6, "coverage": 1.0, "hard_failures": 0,
         "fields_filled": 5, "pending": []}
```

`output/result.json` (abridged):

```json
{"case_id": "demo-bert-abstract",
 "status": "success",
 "results": {
   "bilingual": [{"id": "p1b4", "page": 1, "source": "We introduce ...",
                  "target": "我们提出 ...", "terms": ["pre-training"]}],
   "glossary": [{"en": "fine-tuning", "zh": "微调", "locked": true, "count": 6}],
   "qa": {"status": "success", "coverage_rate": 1.0, "hard_failures": 0}
 },
 "evidence": [{"id": "p1b4", "page": 1, "block": 4, "bbox": [89.0, 247.1, 273.2, 423.1]}],
 "uncertainty": [],
 "pending_fields": []}
```
