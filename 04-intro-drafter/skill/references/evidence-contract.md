# The evidence contract

Every sentence of the draft is a unit with exactly one of three kinds of support.

## 1. `source` — a sentence of the paper
```json
{"type": "source", "ref": "p1b8:s2"}
```
The id means *block* `p1b8`, *sentence* 2 of that block's joined paragraph. The
verifier resolves it against `facts.json` and requires the fact's text to occur
verbatim in the parsed paper. So a source ref is a pointer to a readable location,
not a label.

Use a source ref when the draft restates the paper's own claim, method or result.

## 2. `citation` — a reference entry
```json
{"type": "citation", "ref": "radford2018"}
```
The key comes from `works.json`, which is the reference list after fragment
merging and `a`/`b` disambiguation. Two conditions:

- the key must resolve to an entry;
- the sentence must actually cite it, i.e. contain a matching in-text marker.

The second condition is what stops the common failure of attaching a bibliography
to a paragraph without pointing at the clause it supports: the citation has to be
where the claim is.

## 3. `judgement` — the author's inference
```json
{"type": "judgement", "ref": null}
```
with a `note` on the unit or the evidence entry, e.g. "inferred from the
architecture described in p1b8:s1".

Judgement is legitimate — a related-work paragraph almost always needs one
sentence that no single paper states — but it is bounded:

- at most 40% of units may be judgement;
- every judgement unit needs a note explaining what it is inferred *from*;
- every judgement is listed in the QA report so a reviewer can argue with it
  individually.

## Why the map is positional

`assemble.py` zips `intro.md` sentences with `mapping.json` entries by position and
refuses to continue if the counts differ. The alternative — matching by text — would
let a reworded draft silently keep an old evidence mapping. Positional assembly
means any change to the prose forces a re-assembly, and the verifier then checks
that each mapped text is actually in the file.

## Numbers

Numbers in a sentence must come from the facts that sentence cites. Citation years
are excluded before the check, because they belong to the marker, not the claim.
This is why a contribution may say "GLUE at 80.5%" only with a fact that contains
80.5.
