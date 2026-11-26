# QA rules

## `citation_resolution`
A citation is parsed into author-year tokens (`(Peters et al., 2018a; Radford et
al., 2018)` is two tokens). Each token is matched by key, then by surname+year, then
by surname tail, then disambiguated by a `A and B` second author.

The check fails only when the token's author+year does **not occur in the
reference-list text**. A token that exists there but has no parsed entry is a
review item with the marker and anchor.

Bare-year parentheticals like `(2018)` are ignored: they are not author-year
citations, and treating them as dangling would produce noise.

## `reference_cited`
Uncited references are listed individually with their ids. Above 20% of the list,
the audit fails: a bibliography where a fifth of the entries are never cited is not
a formatting problem.

The finding text says the reference may be cited only in a table or figure note,
because table text is extracted separately and in-body citation scanning skips it.

## `duplicates`
Normalised-title collisions are reported with both ids and the basis. The check is
deliberately title-based: DOI collisions are a subset, and a missing DOI must not
hide a duplicate.

## `field_completeness`
An entry needs authors, a year and a title. A venue is optional — preprints have
none — but a missing year is almost always a fragment that the merge step should
have reassembled, so it is worth failing on.

## `identifier_format`
A DOI must match `10.<4-9 digits>/<suffix>`; an arXiv id must match
`NNNN.NNNNN`. Shape only: the audit does not resolve identifiers over the network,
so a well-formed but wrong DOI passes — that is a documented limit.

## `provenance`
Each entry's original fragments must occur verbatim in the parsed paper. Merged
entries keep `sources`, so a merge cannot be used to introduce text that never
existed in the PDF.

## `key_uniqueness`
Citation keys are the join between the exports and the manuscript. Two entries with
the same key mean any downstream reference manager will silently drop one.

## Self test
`--selftest` injects: a dangling citation, a duplicate entry, an entry without a
year, a malformed DOI, a key collision and a fabricated entry. All six must be
detected while the clean audit passes.
