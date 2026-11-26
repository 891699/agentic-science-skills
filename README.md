# Agentic Science Skills

Agent skills for scientific document reading and academic writing, built for the
Bohrium **科学空间 / Playground for Agentic Science** challenges.

Each folder is one skill: `SKILL.md` is what an agent loads, `skill/scripts` are the
programs it runs, `skill/references` are the rules it follows.

| Folder | Skill | What it does | Challenge |
|---|---|---|---|
| `01-document-parser` | `pdf-evidence-reader` | Parses a PDF into sections, paragraphs, tables, figures and references, each with a page/block anchor | 阅读01 文献文档解析 |
| `02-academic-polish` | `paper-polish` | Minimal academic edits with a sentence-level change log and a fidelity gate | 写作02 学术语言润色 |
| `03-citation-audit` | `cite-audit` | Reconciles the reference list with in-text citations, merges split entries, exports BibTeX / CSL-JSON / CSV | 写作04 参考文献与引用管理 |
| `04-intro-drafter` | `intro-drafter` | Drafts an introduction and related work where every sentence is bound to a fact, a citation or an explicit judgement | 写作08 引言与相关工作写作 |
| `05-paper-note` | `paper-note` | Structured notes whose quotes are verified verbatim against the paper | 阅读10 文献总结与结构化笔记 |
| `06-paper-translator` | `paper-translator` | Section-by-section translation with a locked glossary and terminology checks | 阅读03 文献翻译 |
| `07-nanopublication` | `paper-nanopub` | Emits and validates a nanopublication (assertion / provenance / publication info) | 阅读14 Nanopublication |
| `08-knowledge-graph` | `paper-kg` | Builds and validates a knowledge graph of entities, relations and evidence | 阅读15 文献知识图谱 |

## Design principle

The agent writes content against machine-extracted candidates; a verifier re-checks
every quote, anchor, number and citation mechanically; `--selftest` proves the
checks actually fire by injecting defects. Nothing is reported as verified unless a
program checked it.

## Using a skill

```bash
cd 04-intro-drafter/skill
python scripts/prepare.py PAPER.pdf --out work --max-facts 260
python scripts/assemble.py --work work
python scripts/verify_draft.py --work work --selftest
```

Each `SKILL.md` documents its own commands, inputs, outputs, failure handling and
honest limits.

## Dependencies

Python 3.10+ and `pymupdf` for the parsing skills; the rest is standard library.
No network access is required at run time.

## Scope and limits

Skills operate on one paper at a time, in English or Chinese, and report what they
cannot verify rather than guessing. Scanned PDFs without a text layer are reported
unreadable instead of being mined.

## Licence

Released for reuse in the context of these challenges. Demo papers are not
redistributed here; their arXiv identifiers are recorded in each bundle's manifest.
