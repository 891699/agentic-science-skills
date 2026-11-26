#!/usr/bin/env python3
"""Emit a compilable LaTeX project from a content spec.

The content spec is plain JSON: metadata, sections of paragraphs, an optional table,
an optional equation display and a bibliography. The emitter owns the LaTeX so that
escaping, table column counts, label naming and citation keys are produced in one
place and can be checked mechanically.

Usage:
    python emit_latex.py --content content.json --out PROJECT [--inject-defects]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

TEX_SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def escape(text: str) -> str:
    out = []
    for char in text:
        out.append(TEX_SPECIALS.get(char, char))
    return "".join(out)


def escape_url(text: str) -> str:
    return text.replace("_", r"\_").replace("#", r"\#").replace("%", r"\%")


def slug(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return cleaned or "section"


def render_table(table: dict) -> str:
    columns = table.get("columns") or []
    rows = table.get("rows") or []
    spec = "l" + "r" * (len(columns) - 1)
    lines = ["\\begin{table}[t]", "  \\centering",
             f"  \\caption{{{escape(table.get('caption', ''))}}}",
             f"  \\label{{tab:{slug(table.get('label', 'table'))}}}",
             f"  \\begin{{tabular}}{{{spec}}}", "    \\toprule",
             "    " + " & ".join(escape(c) for c in columns) + " \\\\", "    \\midrule"]
    for row in rows:
        lines.append("    " + " & ".join(escape(str(cell)) for cell in row) + " \\\\")
    lines += ["    \\bottomrule", "  \\end{tabular}", "\\end{table}", ""]
    return "\n".join(lines)


def render_equation(equation: dict) -> str:
    body = equation.get("latex", "")
    return "\n".join(["\\begin{equation}", f"  \\label{{eq:{slug(equation.get('label', 'eq'))}}}",
                      f"  {body}", "\\end{equation}", ""])


def render_project(content: dict) -> dict[str, str]:
    title = escape(content.get("title", "Untitled"))
    authors = escape(content.get("authors", ""))
    abstract = escape(content.get("abstract", ""))

    preamble = [
        r"\documentclass[11pt]{article}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{amsmath,amssymb}",
        r"\usepackage{graphicx}",
        r"\usepackage{booktabs}",
        r"\usepackage{hyperref}",
        r"\usepackage[margin=1in]{geometry}",
        r"\title{" + title + "}",
        r"\author{" + authors + "}",
        r"\date{}",
        r"\begin{document}",
        r"\maketitle",
        "",
        r"\begin{abstract}",
        abstract,
        r"\end{abstract}",
        "",
    ]

    body: list[str] = []
    for index, section in enumerate(content.get("sections") or [], start=1):
        heading = section.get("heading", f"Section {index}")
        body.append(f"\\section{{{escape(heading)}}}")
        body.append(f"\\label{{sec:{slug(heading)}}}")
        if section.get("table"):
            body.append(render_table(section["table"]))
        if section.get("equation"):
            body.append(render_equation(section["equation"]))
        for paragraph in section.get("paragraphs") or []:
            text = paragraph if isinstance(paragraph, str) else paragraph.get("text", "")
            cites = [] if isinstance(paragraph, str) else (paragraph.get("cites") or [])
            rendered = escape(text)
            if cites:
                rendered += " \\cite{" + ",".join(cites) + "}"
            body.append(rendered)
            body.append("")

    references = []
    for entry in content.get("references") or []:
        references.append("@misc{" + entry["key"] + ",")
        references.append("  title = {" + entry.get("title", "") + "},")
        references.append("  author = {" + entry.get("authors", "") + "},")
        references.append("  year = {" + str(entry.get("year", "n.d.")) + "},")
        if entry.get("howpublished"):
            references.append("  howpublished = {" + entry["howpublished"] + "},")
        references.append("}")
        references.append("")

    files = {
        "main.tex": "\n".join(preamble + ["\\input{sections/body}", ""]
                              + ["\\bibliographystyle{plain}", "\\bibliography{refs}",
                                 "", "\\end{document}", ""]),
        "refs.bib": "\n".join(references),
        "sections/body.tex": "\n".join(body),
    }
    return files


def inject_defects(files: dict[str, str]) -> dict[str, str]:
    """Three realistic defects for the repair loop to find and fix."""
    main = files["main.tex"]
    main = main.replace(r"\usepackage{booktabs}", "")
    main = main.replace("\\bibliographystyle{plain}",
                        "\\bibliographystyle{plain}\n% TODO: table numbers live in Table 5")
    main = main.replace(r"\maketitle", r"\maketitle" + "\n\n\\noindent 100% of the runs used 4 TPUs.")
    files["main.tex"] = main
    body = files["sections/body.tex"]
    body = re.sub(r"\\begin\{tabular\}\{lrrr\}", r"\\begin{tabular}{lr}", body, count=1)
    files["sections/body.tex"] = body
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--content", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--inject-defects", action="store_true")
    args = ap.parse_args(argv)

    content = json.loads(args.content.read_text(encoding="utf-8"))
    files = render_project(content)
    if args.inject_defects:
        files = inject_defects(files)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "sections").mkdir(exist_ok=True)
    for name, text in files.items():
        target = args.out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    summary = {"files": sorted(files), "bytes": sum(len(t) for t in files.values()),
               "sections": len(content.get("sections") or []),
               "references": len(content.get("references") or []),
               "defects_injected": bool(args.inject_defects)}
    (args.out / "emit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                                encoding="utf-8")
    print("EMIT_OK " + json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
