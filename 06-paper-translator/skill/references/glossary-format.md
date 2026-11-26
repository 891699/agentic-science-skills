# Glossary format

## CSV seed (shipped)
`glossary/seed-ml-zh.csv`

```csv
en,zh,note
self-attention,自注意力,locked form; never 自我注意力
transformer,Transformer,keep Latin form
```

- `en` is matched case-insensitively as a whole word/phrase (`self-attention` will
  not match inside `self-attentional`).
- `zh` is the locked rendering. Leave it empty to ship a term as a suggestion
  only; `prepare.py` then marks it `locked: false`.
- `note` is for the human editor and is copied into the glossary entry.

## JSON built by `prepare.py`
`work/glossary.json` is an array:

```json
{"en": "fine-tuning", "zh": "微调", "count": 6, "pages": [1],
 "source": "seed", "locked": true, "note": ""}
```

- `count` and `pages` come from the selected segments, so the glossary reflects
  this translation's scope, not the whole library.
- `source: extracted` entries are acronyms and capitalised phrases the script
  found in the text. They have `locked: false` until someone fills `zh`.
- Locking a term is a deliberate act: `verify.py` fails a segment when a locked
  source term is missing its locked Chinese form.

## Terms to prefer
| Term | Preferred | Avoid |
|---|---|---|
| self-attention | 自注意力 | 自我注意力 |
| fine-tuning | 微调 | 精调 |
| token | 词元 | 标记、令牌 |
| masked language model | 掩码语言模型 | 遮盖语言模型 |
| state-of-the-art | 当前最优 | 最新最好的 |
| transformer | Transformer | 变换器 |
| encoder / decoder | 编码器 / 解码器 | 编码机 |

Keep Latin script for model names (`BERT`, `GLUE`, `SQuAD v1.1`) and for terms the
field writes in Latin (`Transformer`, `dropout`, `softmax`) — the glossary does
this explicitly so a translator cannot drift between 变换器 and Transformer.

## Adding a term during a run
1. Add the row to the CSV, or set `zh` and `locked: true` in `glossary.json`.
2. Re-run `prepare.py` (CSV) or `verify.py` (JSON) — no retranslation of earlier
   batches is needed unless the new lock contradicts them; the verifier will name
   the segments that need a second look.
