# Minimal invocation example

> **Example only.** The numbers below are illustrative output shapes, not the
> official case results. Official cases are supplied by the platform.

```bash
$ python submission/scripts/pdf_evidence_parser.py paper.pdf --out work --render
PARSE_OK {"ok": true, "pages": 12, "sections": 17, "tables": 14, "figures": 6,
          "formulas": 3, "references": 50, "char_coverage": 1.0,
          "unreadable_pages": [], "overlays": ["page-003-overlay.png"], "out": "work"}

$ python submission/scripts/run_case.py --case case.json --task task.md \
      --pdf paper.pdf --work work --out output
CASE_OK {"case_id": "example-case", "status": "success", "pages": 12, "sections": 17,
         "tables": 14, "references": 50, "char_coverage": 1.0, "filled": 8,
         "contract_fields": 9, "pending": ["key_result"]}
```

`output/result.json` (abridged):

```json
{
  "case_id": "example-case",
  "status": "success",
  "results": {
    "sections": [{"title": "Deep Residual Learning", "level": 1, "number": "3", "page": 3}],
    "tables": [{"id": "tbl-p5-1", "page": 5, "rows": 9, "cols": 7,
                "grid": [["layer name", "output size", "18-layer", "34-layer"]]}],
    "references_count": 50,
    "full_text": "# Deep Residual Learning for Image Recognition\n..."
  },
  "pending_fields": ["key_result"],
  "evidence": [{"anchor": "p3b2", "page": 3, "bbox": [50.1, 75.0, 286.4, 96.4],
                "section": "Deep Residual Learning"}],
  "uncertainty": [{"item": "field:key_result",
                   "detail": "requires reading and judgement"}]
}
```

Fill a judgement field with the evidence you read:

```bash
$ cat > answers.json <<'EOF'
{"key_result": "3.57% top-5 error on ImageNet (p. 1, block p1b4)"}
EOF
$ python submission/scripts/run_case.py ... --answers answers.json
CASE_OK {"case_id": "example-case", ..., "filled": 9, "pending": []}
```

Read a table:

```bash
$ python - <<'EOF'
import json
r = json.load(open("work/parse.json"))
t = r["tables"][0]
print(t["page"], t["rows"], t["cols"])
print("\n".join(" | ".join(c or "" for c in row) for row in t["grid"][:4]))
EOF
```
