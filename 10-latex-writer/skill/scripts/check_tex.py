#!/usr/bin/env python3
"""Static checks for a LaTeX project, before and after compiling.

Each finding is a dict with a category, a location and a suggested repair. The
classifier is deliberately conservative: a check only fires on something that is
wrong in every TeX distribution, never on style.

Usage:
    python check_tex.py --project PROJECT [--json PATH]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ENV_RE = re.compile(r"\\(begin|end)\{([^}]+)\}")
LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
REF_RE = re.compile(r"\\(?:ref|eqref|autoref|cref)\{([^}]+)\}")
CITE_RE = re.compile(r"\\cite[pt]?\{([^}]+)\}")
GRAPHIC_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
USEPACKAGE_RE = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}")
DOCUMENTCLASS_RE = re.compile(r"\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}")
TABLE_RE = re.compile(r"\\begin\{tabular\}\{([^}]*)\}(.*?)\\end\{tabular\}", re.S)

REQUIRED_PACKAGES = {
    "toprule": "booktabs", "bottomrule": "booktabs", "midrule": "booktabs",
    "includegraphics": "graphicx", "url": "hyperref", "href": "hyperref",
    "textcolor": "xcolor", "checkmark": "amssymb",
}


def strip_comments(text: str) -> str:
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith("%"):
            continue
        cleaned = re.sub(r"(?<!\\)%.*$", "", line)
        out.append(cleaned)
    return "\n".join(out)


def read_sources(project: Path) -> dict[str, str]:
    files = {}
    for path in sorted(project.rglob("*.tex")):
        files[path.relative_to(project).as_posix()] = path.read_text(encoding="utf-8",
                                                                    errors="replace")
    return files


def find_first(pattern: str, text: str, label: str) -> list[dict]:
    return []


def check(project: Path) -> dict:
    sources = read_sources(project)
    raw = "\n".join(sources.values())
    text = strip_comments(raw)
    findings: list[dict] = []

    def add(category: str, where: str, detail: str, repair: str = "",
            severity: str = "error") -> None:
        findings.append({"category": category, "where": where, "detail": detail,
                         "repair": repair, "severity": severity})

    # preamble sanity
    if not DOCUMENTCLASS_RE.search(text):
        add("structure", "main.tex", "no \\documentclass", "add \\documentclass{article}")
    packages = set()
    for match in USEPACKAGE_RE.finditer(text):
        packages.update(p.strip() for p in match.group(1).split(","))
    for command, package in REQUIRED_PACKAGES.items():
        if re.search(r"\\" + command + r"\b", text) and package not in packages:
            add("missing_package", "preamble",
                f"\\{command} used but {{{package}}} not loaded",
                f"add \\usepackage{{{package}}}")

    # a % that silently deletes text is worse than one that raises an error
    for file, content in sources.items():
        for number, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("%"):
                continue
            match = re.search(r"(?<!\\)%", line)
            if match and line[:match.start()].strip():
                add("silent_comment", f"{file}:{number}",
                    "unescaped % comments out the rest of the line",
                    r"escape it as \%", severity="error")

    # environments and braces
    stack: list[str] = []
    for match in ENV_RE.finditer(text):
        kind, name = match.group(1), match.group(2).strip()
        if name == "document":
            continue
        if kind == "begin":
            stack.append(name)
        else:
            if not stack:
                add("environment", "?", f"\\end{{{name}}} without \\begin", "remove or pair the \\end")
            elif stack[-1] != name:
                add("environment", "?", f"\\end{{{name}}} closes \\begin{{{stack[-1]}}}",
                    f"fix the nesting: close {stack[-1]} first")
                stack.pop()
            else:
                stack.pop()
    for leftover in stack:
        add("environment", "?", f"\\begin{{{leftover}}} never closed", f"add \\end{{{leftover}}}")

    depth = 0
    for index, char in enumerate(text):
        if char == "{" and (index == 0 or text[index - 1] != "\\"):
            depth += 1
        elif char == "}" and (index == 0 or text[index - 1] != "\\"):
            depth -= 1
            if depth < 0:
                add("braces", "?", "unbalanced closing brace", "remove the extra }")
                depth = 0
    if depth != 0:
        add("braces", "?", f"{depth} unclosed brace(s)", "close the group")

    # labels and references
    labels: dict[str, int] = {}
    for match in LABEL_RE.finditer(text):
        labels[match.group(1)] = labels.get(match.group(1), 0) + 1
    for name, count in labels.items():
        if count > 1:
            add("duplicate_label", name, f"label defined {count} times",
                "keep one definition and reference it")
    for match in REF_RE.finditer(text):
        for name in match.group(1).split(","):
            name = name.strip()
            if name and name not in labels:
                add("undefined_ref", name, "reference to a label that does not exist",
                    "define the label or change the reference")

    # citations against the bib file
    bib_keys = set()
    for bib in project.rglob("*.bib"):
        content = bib.read_text(encoding="utf-8", errors="replace")
        bib_keys.update(key.strip() for key in
                        re.findall(r"@\w+\{([^,]+),", content))
    for match in CITE_RE.finditer(text):
        for key in match.group(1).split(","):
            key = key.strip()
            if key and key not in bib_keys:
                add("undefined_citation", key, "citation key not in the .bib file",
                    "add the entry or fix the key")

    # graphics
    for match in GRAPHIC_RE.finditer(text):
        name = match.group(1).strip()
        candidates = [project / name, project / "figures" / name,
                      project / (name + ".pdf"), project / (name + ".png"),
                      project / "figures" / (name + ".pdf"), project / "figures" / (name + ".png")]
        if not any(c.exists() for c in candidates):
            add("missing_graphic", name, "includegraphics target not found",
                "add the file or fix the path")

    # tables: column spec against the widest row
    for match in TABLE_RE.finditer(text):
        spec = match.group(1)
        body = match.group(2)
        columns = len(re.findall(r"[lcrp]", re.sub(r"\{[^}]*\}", "", spec)))
        rows = [line for line in body.splitlines()
                if "&" in line and not line.strip().startswith("%")]
        widest = max((len([c for c in row.split("&")]) for row in rows), default=0)
        if widest and columns and widest != columns:
            add("table_columns", "tabular",
                f"{columns} columns declared but a row has {widest} cells",
                "make the column spec match the widest row")

    # math delimiters and unescaped specials
    for index, paragraph in enumerate(re.split(r"\n\s*\n", text)):
        dollars = len(re.findall(r"(?<!\\)\$", paragraph))
        if dollars % 2:
            add("math_mode", f"paragraph{index + 1}",
                "odd number of $ delimiters", "close the math mode")
    body = re.sub(r"\$[^$]*\$", "", text)
    body = re.sub(r"\\begin\{tabular\}.*?\\end\{tabular\}", "", body, flags=re.S)
    body = re.sub(r"\\begin\{equation\}.*?\\end\{equation\}", "", body, flags=re.S)
    for match in re.finditer(r"(?<!\\)([%&_#])", body):
        char = match.group(1)
        if char in "%&" and char in "%&":
            context = body[max(0, match.start() - 25):match.start() + 25].replace("\n", " ")
            add("unescaped_special", "text", f"{char!r} unescaped near: {context!r}",
                f"escape it as \\{char}", severity="warning")

    errors = [f for f in findings if f["severity"] == "error"]
    return {
        "schema": "latex-check/1.0",
        "files": sorted(sources),
        "packages": sorted(packages),
        "labels": len(labels),
        "bib_entries": len(bib_keys),
        "categories": sorted({f["category"] for f in findings}),
        "findings": findings,
        "errors": len(errors),
        "warnings": len(findings) - len(errors),
        "status": "success" if not errors else "failed",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args(argv)
    report = check(args.project)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("CHECK " + json.dumps({k: report[k] for k in
                                 ("status", "errors", "warnings", "categories", "labels",
                                  "bib_entries")}, ensure_ascii=False))
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
