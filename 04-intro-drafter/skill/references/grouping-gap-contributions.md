# Grouping, gap and contributions

## Grouping related work by route

A route is a way of using pre-training, not a year or a venue. Three groups is the
minimum; each has three sentences:

| Sentence | Role | What it must do |
|---|---|---|
| 1 | `group-thesis` | state what the route does, naming ≥2 member works |
| 2 | `limitation` | state what the route costs or assumes; a judgement with a note if the paper only implies it |
| 3 | `differentiation` | say how this paper differs, backed by a fact from the paper |

Why three sentences: a one-sentence group becomes an annotated list; a four-sentence
group becomes a mini-review. The three-sentence shape forces a comparison, which is
what "分得清" asks for.

Ordering: strongest overlap first. A reader deciding whether to keep reading wants
the nearest prior work before the farthest.

## Deriving the gap

The gap paragraph is the only place where the draft is allowed to say what is
missing. The verifier requires all three of:

1. **≥2 cited works** in the gap group — a gap derived from one paper is a
   limitation of that paper, not of the field;
2. **a contrast** word (`however`, `while`, `neither`, `only`, `limited`,
   `restrict`, `lack`, `remain`, `gap`, `but`) — the gap must be stated as a
   contrast, not as a wish;
3. **a fact from the paper** — the paper itself must claim the limitation, so the
   gap is not the drafter's invention.

The typical failure is a gap that says "existing methods are not good enough"
without naming which methods, or one that cites two works that do not share the
shortcoming.

## Contributions

A contribution bullet must:

- cite a fact whose text contains a result token (`obtains`, `improve`, `achieve`,
  `show`, `state-of-the-art`, `hurt`) or a number;
- carry `maps_to`, naming the paper's section, table or experiment;
- avoid scope inflation: if the paper evaluates on eleven tasks, the bullet may not
  say "all tasks"; if the paper reports a benchmark score, the bullet must not
  round it.

Three contributions is the minimum. More than five usually means results are being
listed rather than summarised.

## Hype guard

`first`, `novel`, `state-of-the-art`, `best`, `unprecedented` are allowed only when
the cited fact contains the same word. A paper that says "new state-of-the-art
results" licenses `state-of-the-art`; it does not license `first`. This is a small
rule with a large effect on introductions, where novelty words tend to arrive
unattached to evidence.
