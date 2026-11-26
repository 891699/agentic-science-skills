# QA rules

Each rule exists because its failure changes meaning, not because it is easy to
count.

## `coverage` — every paragraph once
The verifier builds the id set from `segments.json` and from
`translations.jsonl` and compares both directions:

- **missing** — the translator stopped early or skipped a long paragraph;
- **duplicate** — a batch was retried and appended instead of replaced;
- **unknown** — an id was invented or a segment was split into two.

Fix by retranslating the named ids. Never "fix" coverage by deleting a segment.

## `glossary_lock` — the term survives as agreed
For every locked term that occurs in the source segment, its Chinese form must
occur in the target. This is what makes 术语稳 a property of the output rather
than of the prompt:

- drift (`自注意力` → `自我注意力`) is caught even when the translation reads well;
- a term inside a proper name is still checked — if the expansion is kept in
  English, append the Chinese form in parentheses, which is also what a reader
  wants;
- a locked term that is genuinely wrong for the context is kept and explained in
  `notes`; the review queue carries it to a human instead of hiding it.

## `numbers` — values, not glyphs
Numeric values are compared after stripping thousands separators and `%`. So
`7.7%` → `7.7 个百分点` passes (the value survived, the unit was adapted), while
`7.7` → `7` fails. Percent and permille signs are a soft signal: Chinese often
writes 个百分点 instead.

## `citations` — inner text preserved
`[12]`, `[3, 4]`, `(Vaswani et al., 2017)` must appear in the target with the same
inner text. Full-width brackets are accepted (`（Vaswani et al., 2017）`) because
Chinese typography uses them; the citation itself may not be renumbered,
shortened or paraphrased.

## `formula_tokens` — `a = b` survives
Tokens like `F(x) = H(x) - x` are compared as strings. Mathematical equivalence is
out of scope: a reformatted formula is a human-review item, not a silent pass.

## `negation` and `hedge` — the claim's strength
- Source negation (`not/no/never/without/none`) requires a negation marker in the
  target (不/无/未/非/没/勿).
- Source hedging or restriction (`may/can/could/should/only/likely`) requires a
  modal or restriction marker (可能/可以/能/仅/只/应该/或许).

These are marker checks, not scope checks. They catch the common failure —
`may improve` becoming `improves` — and leave genuine scope questions to the
review queue.

## `untranslated` / `placeholder`
A target with no Chinese characters, identical to the source, or containing
`TODO`/`TBD`/`<…>`/`???` is not a translation. Bylines are exempt from the
Chinese-character rule: author names stay in Latin script by convention.

## `length_ratio` — a soft signal
Chinese is usually 0.2–0.6 of the English character count. Below 0.12 suggests
omission; above 1.0 suggests added explanation. Soft: it lands in the review queue
without failing the run.

## Review queue
Every non-hard finding, plus every translator `notes` entry, is emitted in
`qa_report.json.review_queue` with the segment id. That list is the handover to a
human: it says what is doubtful rather than pretending everything is certain.
