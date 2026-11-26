# Edit taxonomy

Every change carries one of these types. The taxonomy exists so a reviewer can
filter the log: "show me every concision edit" or "show me every change to
punctuation" is a real review question.

| Type | What it covers | Example |
|---|---|---|
| `grammar` | agreement, tense, articles, prepositions, closed compounds | `can be finetuned` → `can be fine-tuned` |
| `syntax` | clause structure, dangling modifiers, misplaced modifiers | moving `only` next to what it restricts |
| `collocation` | verb–noun or adjective–noun pairings a native writer expects | `obtains results` → `achieves results` |
| `concision` | removing words that add nothing | `has been shown to be effective for improving` → `has been shown to improve` |
| `sentence-structure` | apposition, participle, colon, relative clause, split | `model called BERT, which stands for` → `model, BERT, whose name stands for` |
| `sentence-split` | splitting an overlong sentence at a real clause boundary | 80-word sentence into two |
| `parallelism` | two lists given the same shape | `sentence-level tasks ..., as well as token-level tasks, where ...` → two parallel sentences |
| `punctuation` | serial comma, semicolon between independent clauses, comma with restrictive participles | `objective, inspired by` → `objective inspired by` |
| `hyphenation` | closed and hyphenated compounds | `taskspecific` → `task-specific`; `sub-optimal` → `suboptimal` |
| `spelling` | spelling variants, not domain terms | `sub-optimal` → `suboptimal` |
| `redundancy` | duplicated information inside one sentence | `7.7% point absolute improvement` → `7.7% absolute improvement` |
| `voice` | passive to active when the agent matters | `the authors use` → `OpenAI GPT uses` |
| `word-choice` | a better verb or noun with the same meaning | `pushing the score` → `raising the score` |
| `article` | definite/indefinite article on generic plurals | `the fine-tuning approaches` → `fine-tuning approaches` |
| `register` | informal or promotional wording | `a big win` → `a substantial improvement` |

## What an edit must not do

- change a number, unit, percentage, or the point/percent distinction;
- move a citation, add one, or drop one;
- replace a protected term with a synonym (BERT is not "the model" in a
  results sentence — the first `BERT` in a paragraph may be varied, but the
  verifier treats a disappeared acronym as a defect, so vary only where the term
  appears more than once and keep at least one occurrence);
- remove or add a hedge (`may`, `can`, `only`, `likely`, `suggest`);
- flip a negation;
- turn a correlation into a cause;
- delete a qualification clause to make the sentence shorter.

## Minimal-edit band

- length ratio 0.85–1.15 per paragraph;
- sentence count delta −1 to +2;
- if a paragraph needs more than that, the honest output is "this paragraph needs a
  rewrite, here is why" rather than a silent reconstruction.
