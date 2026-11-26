# Workflow

## 1. Prepare
```bash
python scripts/prepare.py paper.pdf --out work --max-sentences 8
```
| File | Meaning |
|---|---|
| `work/candidates.json` | quotable sentences: `id` (`p1b5:s1`), `anchor`, `page`, `block`, `section`, `text`, `numbers`, `citations` |
| `work/segments.json` | the paper outline, so assertions can be grouped by section |
| `work/paper.json` | source metadata: title, authors, year, arXiv/DOI, SHA-256, pages |
| `work/parse.json` | the full parse the validator re-reads for verbatim evidence |

## 2. Author assertions
Write `work/assertions.json` against the candidate ids. Work from the argument
sections outward: abstract claims, the method's mechanism, the main results, the
ablations, the conclusion. Each claim usually needs one sentence; a sentence that
carries three results becomes three assertions.

The two failure modes to watch:

- **compound object** — "lower on QNLI, MNLI and SQuAD" is three assertions;
- **condition hidden in the object** — "works with one extra layer" is
  `requires-condition` with the layer count as the object, not a property of the
  method in general.

## 3. Emit
```bash
python scripts/emit_nanopub.py --work work
```
Writes `work/nanopubs.trig` and `work/nanopubs.jsonl`. Each nanopublication gets a
content-addressed URI: `https://w3id.org/np/RA<base64url-sha256>`. The hash covers
assertion + evidence + source metadata, not the timestamp, so re-running is
idempotent.

## 4. Validate
```bash
python scripts/validate_nanopub.py --work work            # exit 1 while anything hard fails
python scripts/validate_nanopub.py --work work --selftest # proves the checks fire
```
The report names the nanopublication and the check. Fix the assertion (or the
rights of the claim), re-emit, re-validate.

## 5. Produce the case result
```bash
python scripts/run_case.py --case case.json --task task.md --pdf paper.pdf \
    --work work --out output
```
Outputs: `output/result.json` (assertions, nanopublications, source, evidence, QA,
TriG) and `output/nanopubs.trig` (the serialisation on its own).

## 6. Reuse
The TriG is the interchange format; `result.json` is the human- and code-readable
record. To load it into a triple store:
`rdflib.Dataset().parse("output/nanopubs.trig", format="trig")`. Assertions can be
compared across papers by (subject, relation) pairs, and deduplicated by content
hash.
