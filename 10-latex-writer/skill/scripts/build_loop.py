#!/usr/bin/env python3
"""Compile a LaTeX project, classify what broke, repair it, and compile again.

The loop is the point of the skill: a compile failure is turned into a category, a
category into a repair, and a repair into evidence (before/after log excerpts). Every
round is recorded, including the repairs that were *not* applied automatically and
stay as warnings for a human.

Usage:
    python build_loop.py --project PROJECT [--max-rounds 3] [--engine pdflatex]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_tex  # noqa: E402

TINYTEX_CANDIDATES = [
    Path(r"E:\bher\tools\tex\tinytex\bin\windows"),
    Path(r"E:\bher\tools\tex\TinyTeX\bin\windows"),
    Path.home() / "AppData/Roaming/TinyTeX/bin/windows",
    Path(r"C:\ProgramData\TinyTeX\bin\windows"),
]

# undefined control sequence -> package that provides it
COMMAND_PACKAGES = {
    "toprule": "booktabs", "midrule": "booktabs", "bottomrule": "booktabs",
    "includegraphics": "graphicx", "textcolor": "xcolor", "checkmark": "amssymb",
    "href": "hyperref", "url": "hyperref", "bm": "bm", "mathbb": "amssymb",
}
# missing .sty file -> package to declare (the file name is usually the package)
PACKAGE_ALIASES = {"amsfonts": "amssymb", "amsmath2": "amsmath"}

ERROR_RE = re.compile(r"^! (.+)$", re.M)
UNRESOLVED_RE = re.compile(r"(Reference|Citation) `([^']+)' on page \d+ undefined")
OVERFULL_RE = re.compile(r"Overfull \\hbox \((\d+(?:\.\d+)?)pt too wide\)")


def find_engine(name: str = "pdflatex") -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for directory in TINYTEX_CANDIDATES:
        candidate = directory / f"{name}.exe"
        if candidate.exists():
            return str(candidate)
    return None


def classify(log: str) -> dict:
    errors = [match.group(1).strip() for match in ERROR_RE.finditer(log)]
    unresolved = [(kind, key) for kind, key in UNRESOLVED_RE.findall(log)]
    overfull = [float(value) for value in OVERFULL_RE.findall(log)]
    categories: set[str] = set()
    for message in errors:
        lowered = message.lower()
        if "not found" in lowered and ".sty" in lowered:
            categories.add("missing_package_file")
        elif "undefined control sequence" in lowered:
            categories.add("undefined_command")
        elif "missing $ inserted" in lowered:
            categories.add("math_mode")
        elif "extra alignment tab" in lowered:
            categories.add("table_columns")
        elif "runaway argument" in lowered:
            categories.add("runaway_argument")
        elif "file" in lowered and "not found" in lowered:
            categories.add("missing_file")
        else:
            categories.add("other_error")
    for kind, _key in unresolved:
        categories.add("undefined_ref" if kind == "Reference" else "undefined_citation")
    if overfull:
        categories.add("overfull_hbox")
    return {"errors": errors, "unresolved": unresolved, "overfull": overfull,
            "categories": sorted(categories)}


def add_package(project: Path, package: str) -> bool:
    main = project / "main.tex"
    if not main.exists():
        return False
    text = main.read_text(encoding="utf-8")
    if re.search(r"\\usepackage(?:\[[^\]]*\])?\{" + re.escape(package) + r"\}", text):
        return False
    anchor = re.search(r"\\usepackage(?:\[[^\]]*\])?\{[^}]+\}\n", text)
    line = "\\usepackage{" + package + "}\n"
    if anchor:
        text = text[:anchor.end()] + line + text[anchor.end():]
    else:
        text = re.sub(r"(\\documentclass(?:\[[^\]]*\])?\{[^}]+\}\n)", r"\1" + line, text, count=1)
    main.write_text(text, encoding="utf-8")
    return True


def escape_specials(project: Path) -> list[str]:
    """Escape % & # _ that appear in text outside math and outside commands."""
    changed: list[str] = []
    for path in sorted(project.rglob("*.tex")):
        text = path.read_text(encoding="utf-8")
        lines = []
        for line in text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("%") or stripped.startswith("\\\\newcommand") or stripped.startswith("\\\\def"):
                lines.append(line)
                continue
            repaired = line
            repaired = re.sub(r"(?<!\\)%", r"\\%", repaired)
            repaired = re.sub(r"(?<!\\)#", r"\\#", repaired)
            if repaired != line:
                changed.append(path.relative_to(project).as_posix())
            lines.append(repaired)
        if lines:
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sorted(set(changed))


def fix_table_columns(project: Path) -> list[str]:
    fixes = []
    for path in sorted(project.rglob("*.tex")):
        text = path.read_text(encoding="utf-8")
        new_text = text
        for match in check_tex.TABLE_RE.finditer(text):
            spec, body = match.group(1), match.group(2)
            declared = len(re.findall(r"[lcrp]", re.sub(r"\{[^}]*\}", "", spec)))
            rows = [line for line in body.splitlines() if "&" in line]
            widest = max((len(row.split("&")) for row in rows), default=0)
            if widest and declared and widest != declared:
                new_spec = "l" + "r" * (widest - 1)
                new_text = new_text.replace(f"\\begin{{tabular}}{{{spec}}}",
                                            f"\\begin{{tabular}}{{{new_spec}}}", 1)
                fixes.append(f"{path.name}: {declared} -> {widest} columns")
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
    return fixes


def static_repairs(project: Path) -> dict:
    report = check_tex.check(project)
    actions: list[str] = []
    packages = set()
    for finding in report["findings"]:
        if finding["category"] == "missing_package":
            match = re.search(r"\{(\w+)\}", finding["repair"])
            if match:
                packages.add(match.group(1))
    for package in sorted(packages):
        if add_package(project, PACKAGE_ALIASES.get(package, package)):
            actions.append(f"preamble: add \\usepackage{{{package}}}")
    escaped = escape_specials(project)
    if escaped:
        actions.append(f"escape specials in {', '.join(escaped)}")
    columns = fix_table_columns(project)
    actions.extend(f"table: {item}" for item in columns)
    return {"actions": actions}


def run(engine: str, project: Path, timeout: int = 180) -> dict:
    started = time.time()
    proc = subprocess.run([engine, "-interaction=nonstopmode", "-file-line-error", "main.tex"],
                          cwd=str(project), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    log_path = project / "main.log"
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    return {"exit": proc.returncode, "seconds": round(time.time() - started, 2),
            "log": log, "stdout_tail": (proc.stdout or "")[-400:]}


def run_bibtex(project: Path) -> dict:
    engine = shutil.which("bibtex")
    if not engine:
        for directory in TINYTEX_CANDIDATES:
            candidate = directory / "bibtex.exe"
            if candidate.exists():
                engine = str(candidate)
                break
    if not engine:
        return {"available": False}
    proc = subprocess.run([engine, "main"], cwd=str(project), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    return {"available": True, "exit": proc.returncode,
            "tail": ((proc.stdout or "") + (proc.stderr or ""))[-300:]}


def install_package(package: str) -> bool:
    """Last resort for a .sty that is not in the distribution: ask tlmgr for it."""
    engine_dir = find_engine("pdflatex")
    if not engine_dir:
        return False
    tlmgr = Path(engine_dir).with_name("tlmgr.bat")
    if not tlmgr.exists():
        tlmgr = Path(engine_dir).with_name("tlmgr.exe")
    if not tlmgr.exists():
        return False
    proc = subprocess.run([str(tlmgr), "install", package], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=600)
    return proc.returncode == 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--max-rounds", type=int, default=3)
    ap.add_argument("--engine", default="pdflatex")
    args = ap.parse_args(argv)

    engine = find_engine(args.engine)
    report_path = args.project / "build_report.json"
    if not engine:
        report = {"schema": "latex-build/1.0", "engine": None,
                  "status": "no_engine",
                  "detail": "no TeX engine found on PATH or in the TinyTeX directories",
                  "static": check_tex.check(args.project)}
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print("BUILD " + json.dumps({"status": "no_engine", "errors": None}, ensure_ascii=False))
        return 3

    rounds = []
    for index in range(1, args.max_rounds + 1):
        static = static_repairs(args.project)
        first = run(engine, args.project)
        parsed = classify(first["log"])
        bib = None
        if parsed["categories"] and ("undefined_citation" in parsed["categories"]
                                     or "missing_file" in parsed["categories"]):
            bib = run_bibtex(args.project)
            first = run(engine, args.project)
            parsed = classify(first["log"])

        repairs = list(static["actions"])
        packages = set()
        for message in parsed["errors"]:
            lowered = message.lower()
            match = re.search(r"file `([\w-]+)\.sty' not found", lowered)
            if match:
                packages.add(match.group(1))
            for command, package in COMMAND_PACKAGES.items():
                if command in lowered:
                    packages.add(package)
        for package in sorted(packages):
            if add_package(args.project, PACKAGE_ALIASES.get(package, package)):
                repairs.append(f"preamble: add \\usepackage{{{package}}} (from the log)")
            installed = install_package(package)
            if installed:
                repairs.append(f"tlmgr: install {package}")

        round_record = {"round": index, "exit": first["exit"], "seconds": first["seconds"],
                        "errors": len(parsed["errors"]),
                        "unresolved": [f"{k} {v}" for k, v in parsed["unresolved"]],
                        "overfull": len(parsed["overfull"]),
                        "categories": parsed["categories"], "repairs": repairs,
                        "error_excerpt": parsed["errors"][:5],
                        "bibtex": bib}
        rounds.append(round_record)

        pdf = args.project / "main.pdf"
        if first["exit"] == 0 and not parsed["errors"] and not parsed["unresolved"]:
            break
        if not repairs and not parsed["errors"]:
            break

    final = run(engine, args.project)
    parsed = classify(final["log"])
    pdf = args.project / "main.pdf"
    report = {
        "schema": "latex-build/1.0",
        "engine": engine,
        "rounds": rounds,
        "final": {"exit": final["exit"], "errors": len(parsed["errors"]),
                  "unresolved": [f"{k} {v}" for k, v in parsed["unresolved"]],
                  "overfull": len(parsed["overfull"]), "categories": parsed["categories"],
                  "pdf": pdf.exists(),
                  "pdf_bytes": pdf.stat().st_size if pdf.exists() else 0},
        "static_after": {"errors": check_tex.check(args.project)["errors"]},
        "status": "success" if (pdf.exists() and not parsed["errors"]
                                and not parsed["unresolved"]
                                and not check_tex.check(args.project)["errors"]) else "failed",
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("BUILD " + json.dumps({k: report[k] for k in ("status", "rounds")}
                                | {"final": report["final"]}, ensure_ascii=False))
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
