# Keys and fragments

## Citation keys

A key is `surname+year`, lowercased and stripped of punctuation:
`surname2018`. When two or more works share the same surname and year, the key gets
a letter suffix in list order: `peters2018a`, `peters2018b`.

Rules:

- the surname is the **first** author's, taken from the author block before the
  year (`Rie Kubota Ando and Tong Zhang` → `Ando`);
- an in-text `A and B, year` disambiguates between candidates by checking that `B`
  appears in the entry's author block;
- a multi-word surname is matched by its tail as well (`Tjong Kim Sang` →
  `Sang`), because the reference list often keeps only the last word as the surname;
- a key must be unique; a collision without a suffix is a hard failure.

## Fragments

PDF reference lists are two-column and the extractor regularly splits one entry into
two blocks. The split is nearly always *head before continuation*, so a block with
no year and no author prefix is prepended to the **next** complete entry; only a
trailing fragment attaches backwards.

Every merge is recorded:

```json
{"merged": "ref-002", "into": "ref-001",
 "reason": "head fragment: the PDF placed the start of the entry in the previous text block"}
```

The merged entry keeps its original fragments in `sources`, and the provenance check
verifies each fragment verbatim, so a merge cannot quietly invent text.

## Existence vs matching

The audit distinguishes three states for a citation:

| State | Meaning | Severity |
|---|---|---|
| resolved | matched to an entry | — |
| exists but unmatched | the author+year occurs in the reference-list text, but no parsed entry matches | finding |
| dangling | the author+year occurs nowhere in the reference list | **hard failure** |

The middle state is the honest one: a citation can be correct while the tool's
entry parser fails. Reporting it as a manuscript defect would be wrong, and hiding
it would be worse.

## Duplicates

Two entries with the same normalised title (first 80 characters, alphanumerics
only) are duplicates. The report names both ids and the basis, so a reviewer can
decide whether it is a genuine double-listing or two similarly titled works.
