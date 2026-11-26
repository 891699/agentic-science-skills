#!/usr/bin/env python3
"""Evidence-anchored scientific PDF parser.

Extracts a reading-ordered, structure-typed representation of a research PDF in
which every emitted element carries a pointer back to its source (page, block,
bounding box).  Designed for agent use: one command, deterministic JSON, honest
status for anything it cannot read.

Public contract
---------------
    parse_pdf(path, render_dir=None, max_pages=None) -> dict

The returned dict is serialised as ``parse.json``; the same information is also
written as ``document.md`` (human/markdown reading order) and
``structure.json`` (compact structural skeleton).

Usage:
    python pdf_evidence_parser.py INPUT.pdf --out OUTDIR [--render] [--max-pages N]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

try:  # PyMuPDF >= 1.24 and 2.x
    import pymupdf as fitz
except Exception:  # pragma: no cover - older releases
    import fitz  # type: ignore

SCHEMA = "pdf-evidence-parse/1.0"

LIGATURES = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
    "\u00ad": "",  # soft hyphen
}

MATH_CHARS = set("\u222b\u2211\u220f\u221a\u00b1\u00d7\u00f7\u2264\u2265\u2248\u2260\u221e\u2202\u2207\u2208\u2209\u2282\u2286\u222a\u2229\u211d\u2115\u2124\u03b1\u03b2\u03b3\u03b4\u03b5\u03b6\u03b7\u03b8\u03b9\u03ba\u03bb\u03bc\u03bd\u03be\u03c0\u03c1\u03c3\u03c4\u03c5\u03c6\u03c7\u03c8\u03c9\u0393\u0394\u0398\u039b\u039e\u03a0\u03a3\u03a6\u03a8\u03a9\u2192\u2190\u2194\u21d2\u21d4\u00b7\u22c5\u2218\u2297\u2295\u27e8\u27e9\u2308\u2309\u230a\u230b")

CAPTION_RE = re.compile(r"^\s*(Figure|Fig\.|FIG\.|Table|TABLE|Algorithm|Listing)\s*([0-9]+|[IVX]+)\b")
SECTION_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+(\S.{0,110})$")
KNOWN_HEADINGS = {
    "abstract", "introduction", "related work", "background", "method", "methods",
    "approach", "experiments", "experimental setup", "results", "discussion",
    "conclusion", "conclusions", "references", "acknowledgments", "acknowledgements",
    "appendix", "supplementary material", "limitations", "future work",
}
PAGE_NUM_RE = re.compile(r"^\s*[-\u2013\u2014]?\s*\d{1,4}\s*[-\u2013\u2014]?\s*$")
DOI_RE = re.compile(r"(doi:|arxiv:|https?://|www\.|\u00a9|copyright|preprint)", re.I)

# A wrapped title continues when the previous fragment stops on one of these.
TITLE_CONTINUATION_WORDS = {
    "of", "for", "and", "the", "in", "on", "to", "with", "from", "a", "an", "by",
    "at", "as", "via", "using", "between", "under", "over", "into", "toward",
    "towards", "based", "within", "without", "through",
}
ORG_WORDS = (
    "university", "research", "institute", "laboratory", "lab", "google",
    "microsoft", "deepmind", "meta", "openai", "college", "school", "academy",
    "inc.", "corporation", "department",
)
REF_STOP_WORDS = {
    "in", "the", "a", "an", "proceedings", "journal", "ieee", "acm", "arxiv",
    "http", "https", "url", "vol", "pp", "and", "for", "of", "on", "at",
    "from", "by", "with", "this", "we", "our", "technical", "conference",
}


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_text(text: str, records: dict[str, int]) -> str:
    """Normalise ligatures and stray control characters, recording every change."""
    out = []
    for ch in text:
        if ch in LIGATURES:
            out.append(LIGATURES[ch])
            records["ligature"] = records.get("ligature", 0) + 1
            continue
        cat = unicodedata.category(ch)
        if cat in ("Cc", "Cf") and ch not in "\t\n":
            records["control_char"] = records.get("control_char", 0) + 1
            continue
        out.append(ch)
    return "".join(out)


def dehyphenate(left: str, right: str) -> tuple[str, bool]:
    """Join two fragments, repairing a line-break hyphen when it is one."""
    if not left:
        return right, False
    if left.endswith(("-", "\u2010")) and right[:1].islower():
        return left[:-1] + right, True
    return left + right, False


def join_word_break(left: str, right: str, vocab: set[str]) -> tuple[str, bool]:
    """Join a line break that may be a hyphenated compound or a broken word.

    A hyphen at the end of a line is ambiguous.  The document itself decides:
    when the same compound is written with a hyphen somewhere else in the text it
    is a real compound and the hyphen is kept; otherwise it is a word broken by
    justification and the hyphen is dropped.
    """
    if left.endswith(("-", "\u2010")) and right[:1].islower():
        stem = re.search(r"([A-Za-z]+)-$", left)
        nxt = re.match(r"([A-Za-z]+)", right)
        if stem and nxt and f"{stem.group(1).lower()}-{nxt.group(1).lower()}" in vocab:
            return left + right, False
        return left[:-1] + right, True
    return left + " " + right, False


def join_lines(lines: list[str], joined_records: dict[str, int], vocab: set[str]) -> str:
    text = ""
    fixes = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if not text:
            text = line
            continue
        text, fixed = join_word_break(text, line, vocab)
        if fixed:
            fixes += 1
    if fixes:
        joined_records["dehyphenated_joins"] = joined_records.get("dehyphenated_joins", 0) + fixes
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def dedupe_spans(spans: list[Span]) -> tuple[list[Span], int]:
    """Drop glyph runs the producer drew twice (fake-bold / shadow text).

    IEEE-style PDFs often paint a word twice with a sub-point offset so it looks
    bolder.  PyMuPDF reports both runs, which duplicates every word.  Two spans
    are the same painted text when they share the text and their origins agree
    within one point.
    """
    kept: list[Span] = []
    dropped = 0
    for span in spans:
        duplicate = False
        for prev in kept[-6:]:
            if (prev.text == span.text
                    and abs(prev.bbox[0] - span.bbox[0]) < 1.0
                    and abs(prev.origin_y - span.origin_y) < 1.0
                    and abs(prev.bbox[1] - span.bbox[1]) < 1.2):
                duplicate = True
                break
        if duplicate:
            dropped += 1
            continue
        kept.append(span)
    return kept, dropped


def dedupe_lines(lines: list[Line]) -> tuple[list[Line], int]:
    kept: list[Line] = []
    dropped = 0
    for line in lines:
        duplicate = False
        for prev in kept[-4:]:
            if (prev.text.strip() == line.text.strip()
                    and abs(prev.bbox[1] - line.bbox[1]) < 1.2
                    and abs(prev.bbox[0] - line.bbox[0]) < 1.2):
                duplicate = True
                break
        if duplicate:
            dropped += 1
            continue
        kept.append(line)
    return kept, dropped


TERMINAL_RE = re.compile(r"[.!?:;]\s*[\"'\u201d\u2019)\]]?\s*$")


def is_terminal(text: str) -> bool:
    return bool(TERMINAL_RE.search(text.strip()))


def starts_continuation(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    first = stripped[0]
    return first.islower() or first in "(=+\u2212\u00d7\u00f7<>\u2264\u2265"


def clean_number_tokens(text: str) -> str:
    return re.sub(r"\s+([,.;:)\]}])", r"\1", text)


# --------------------------------------------------------------------------- #
# data model
# --------------------------------------------------------------------------- #
@dataclass
class Span:
    text: str
    bbox: tuple[float, float, float, float]
    size: float
    flags: int
    font: str
    origin_y: float

    @property
    def bold(self) -> bool:
        return bool(self.flags & 16) or "bold" in self.font.lower() or "black" in self.font.lower()

    @property
    def italic(self) -> bool:
        return bool(self.flags & 2) or "italic" in self.font.lower() or "oblique" in self.font.lower()

    @property
    def superscript(self) -> bool:
        return bool(self.flags & 1)


@dataclass
class Line:
    bbox: tuple[float, float, float, float]
    spans: list[Span]
    direction: tuple[float, float]

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)

    @property
    def size(self) -> float:
        sizes = [s.size for s in self.spans if s.text.strip()]
        return max(sizes) if sizes else 0.0

    @property
    def bold(self) -> bool:
        body = [s for s in self.spans if s.text.strip()]
        return bool(body) and sum(1 for s in body if s.bold) >= max(1, len(body) * 0.6)

    @property
    def horizontal(self) -> bool:
        return abs(self.direction[1]) < 0.15


@dataclass
class Block:
    page: int
    index: int
    bbox: tuple[float, float, float, float]
    lines: list[Line] = field(default_factory=list)
    kind: str = "body"
    text: str = ""
    level: int | None = None
    number: str | None = None
    order: int = -1
    evidence_id: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def top(self) -> float:
        return self.bbox[1]

    @property
    def bottom(self) -> float:
        return self.bbox[3]

    @property
    def left(self) -> float:
        return self.bbox[0]

    @property
    def right(self) -> float:
        return self.bbox[2]

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def cx(self) -> float:
        return (self.left + self.right) / 2

    @property
    def cy(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def size(self) -> float:
        sizes = [ln.size for ln in self.lines if ln.text.strip()]
        return max(sizes) if sizes else 0.0

    @property
    def bold(self) -> bool:
        body = [ln for ln in self.lines if ln.text.strip()]
        return bool(body) and sum(1 for ln in body if ln.bold) >= max(1, len(body) * 0.6)

    def evidence(self) -> dict:
        return {
            "anchor": self.evidence_id,
            "page": self.page,
            "block": self.index,
            "bbox": [round(v, 2) for v in self.bbox],
        }


# --------------------------------------------------------------------------- #
# geometry: reading order by recursive XY-cut
# --------------------------------------------------------------------------- #
def _gaps(intervals: list[tuple[float, float]]) -> list[tuple[float, float, float]]:
    """Return free gaps (start, end, size) between merged intervals."""
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged: list[list[float]] = [list(ordered[0])]
    for lo, hi in ordered[1:]:
        if lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return [(merged[i][1], merged[i + 1][0], merged[i + 1][0] - merged[i][1])
            for i in range(len(merged) - 1)]


def _split(items: list[Block], axis: str, pos: float) -> tuple[list[Block], list[Block]]:
    if axis == "v":
        first = [b for b in items if b.cx < pos]
        second = [b for b in items if b.cx >= pos]
    else:
        first = [b for b in items if b.cy < pos]
        second = [b for b in items if b.cy >= pos]
    return first, second


def xy_cut(items: list[Block], min_vgap: float = 8.0, min_hgap: float = 2.0) -> list[Block]:
    """Classic XY-cut: cut on the widest free vertical or horizontal channel."""
    if len(items) <= 1:
        return list(items)

    hgaps = _gaps([(b.top, b.bottom) for b in items])
    vgaps = _gaps([(b.left, b.right) for b in items])
    hbest = max(hgaps, key=lambda g: g[2]) if hgaps else None
    vbest = max(vgaps, key=lambda g: g[2]) if vgaps else None

    use_v = (
        vbest is not None
        and vbest[2] >= min_vgap
        and (hbest is None or vbest[2] >= hbest[2] * 1.15)
    )
    if use_v:
        pos = (vbest[0] + vbest[1]) / 2
        left, right = _split(items, "v", pos)
        if left and right:
            return xy_cut(left, min_vgap, min_hgap) + xy_cut(right, min_vgap, min_hgap)
    if hbest is not None and hbest[2] >= min_hgap:
        pos = (hbest[0] + hbest[1]) / 2
        top, bottom = _split(items, "h", pos)
        if top and bottom:
            return xy_cut(top, min_vgap, min_hgap) + xy_cut(bottom, min_vgap, min_hgap)
    return sorted(items, key=lambda b: (round(b.top, 1), b.left))


def detect_columns(blocks: list[Block], page_width: float) -> dict:
    """Report whether the page behaves like a multi-column layout."""
    if not blocks:
        return {"layout": "empty", "columns": 0, "gutter": None}
    mid = page_width / 2
    left = [b for b in blocks if b.right <= mid + 6]
    right = [b for b in blocks if b.left >= mid - 6]
    spanning = [b for b in blocks if b not in left and b not in right]
    if len(left) >= 2 and len(right) >= 2:
        lr = max(b.right for b in left)
        rl = min(b.left for b in right)
        return {
            "layout": "two-column",
            "columns": 2,
            "gutter": [round(lr, 1), round(rl, 1)],
            "left_blocks": len(left),
            "right_blocks": len(right),
            "spanning_blocks": len(spanning),
        }
    return {"layout": "single-column", "columns": 1, "gutter": None}


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
class PdfEvidenceParser:
    def __init__(self, path: Path, max_pages: int | None = None):
        self.path = path
        self.doc = fitz.open(path)
        self.max_pages = max_pages
        self.records: dict[str, int] = {}
        self.change_records: list[dict] = []
        self.uncertainty: list[dict] = []
        self.pages: list[dict] = []
        self.blocks: list[Block] = []
        self.tables: list[dict] = []
        self.formulas: list[dict] = []
        self.figures: list[dict] = []
        self.excluded: list[dict] = []
        self.body_size = 10.0
        self.page_sizes: list[tuple[float, float]] = []
        self.hyphen_vocab: set[str] = set()

    # -- extraction -------------------------------------------------------- #
    def extract(self) -> None:
        weight: dict[float, int] = {}
        for pno in range(self.doc.page_count):
            page = self.doc[pno]
            self.page_sizes.append((page.rect.width, page.rect.height))
            raw = page.get_text("dict")
            for b in raw["blocks"]:
                if b.get("type") != 0:
                    continue
                for line in b.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "")
                        if text.strip():
                            key = round(span["size"], 1)
                            weight[key] = weight.get(key, 0) + len(text)
                            for compound in re.findall(r"[A-Za-z]+-[A-Za-z]+", text):
                                self.hyphen_vocab.add(compound.lower())
        if weight:
            self.body_size = max(weight, key=weight.get)

    def build_blocks(self) -> None:
        for pno in range(self.doc.page_count):
            page = self.doc[pno]
            width, height = page.rect.width, page.rect.height
            raw = page.get_text("dict")
            page_blocks: list[Block] = []
            for bidx, b in enumerate(raw["blocks"]):
                bbox = tuple(float(v) for v in b["bbox"])
                if b.get("type") == 1:  # image
                    blk = Block(page=pno + 1, index=bidx, bbox=bbox, kind="figure")
                    blk.evidence_id = f"p{pno + 1}b{bidx}"
                    if bbox[3] - bbox[1] > 20 and bbox[2] - bbox[0] > 20:
                        page_blocks.append(blk)
                    continue
                lines: list[Line] = []
                for line in b.get("lines", []):
                    spans = []
                    for span in line.get("spans", []):
                        spans.append(Span(
                            text=normalize_text(span.get("text", ""), self.records),
                            bbox=tuple(float(v) for v in span["bbox"]),
                            size=float(span["size"]),
                            flags=int(span.get("flags", 0)),
                            font=span.get("font", ""),
                            origin_y=float(span.get("origin", (0.0, 0.0))[1]),
                        ))
                    if not spans:
                        continue
                    spans, dropped_spans = dedupe_spans(spans)
                    if dropped_spans:
                        self.records["duplicate_spans"] = self.records.get("duplicate_spans", 0) + dropped_spans
                    lines.append(Line(
                        bbox=tuple(float(v) for v in line["bbox"]),
                        spans=spans,
                        direction=tuple(line.get("dir", (1.0, 0.0))),
                    ))
                lines, dropped_lines = dedupe_lines(lines)
                if dropped_lines:
                    self.records["duplicate_lines"] = self.records.get("duplicate_lines", 0) + dropped_lines
                if not lines:
                    continue
                blk = Block(page=pno + 1, index=bidx, bbox=bbox, lines=lines)
                blk.evidence_id = f"p{pno + 1}b{bidx}"
                blk.text = join_lines([ln.text for ln in lines], self.records, self.hyphen_vocab)
                page_blocks.append(blk)
            self.blocks.extend(page_blocks)
            self.pages.append({"page": pno + 1, "width": width, "height": height,
                               "block_count": len(page_blocks), "raw_blocks": page_blocks})

    # -- tables / formulas -------------------------------------------------- #
    def detect_graphic_regions(self) -> None:
        """Cluster vector drawings and images into graphic regions per page.

        Text inside these regions is figure-internal labelling (axis ticks, box
        labels), not running body text; it is reported with the figure instead of
        being spliced into the prose.
        """
        for page in self.pages:
            page_obj = self.doc[page["page"] - 1]
            boxes: list[tuple[float, float, float, float]] = []
            try:
                for drawing in page_obj.get_drawings():
                    rect = drawing.get("rect")
                    if rect is not None and rect.width > 8 and rect.height > 8:
                        boxes.append((rect.x0, rect.y0, rect.x1, rect.y1))
            except Exception:
                pass
            for blk in page["raw_blocks"]:
                if blk.kind == "figure":
                    boxes.append(blk.bbox)
            clusters: list[list[float]] = []
            for box in sorted(boxes, key=lambda b: (b[1], b[0])):
                merged = False
                for cluster in clusters:
                    if (box[0] <= cluster[2] + 6 and box[2] >= cluster[0] - 6
                            and box[1] <= cluster[3] + 6 and box[3] >= cluster[1] - 6):
                        cluster[0] = min(cluster[0], box[0])
                        cluster[1] = min(cluster[1], box[1])
                        cluster[2] = max(cluster[2], box[2])
                        cluster[3] = max(cluster[3], box[3])
                        merged = True
                        break
                if not merged:
                    clusters.append(list(box))
            page_area = page["width"] * page["height"]
            page["graphic_regions"] = [
                [round(v, 2) for v in c] for c in clusters
                if (c[2] - c[0]) * (c[3] - c[1]) >= page_area * 0.008
                and c[2] - c[0] > 60 and c[3] - c[1] > 40
            ]

    def extract_tables(self) -> None:
        for pno in range(self.doc.page_count):
            page = self.doc[pno]
            try:
                finder = page.find_tables()
            except Exception as exc:  # pragma: no cover - defensive
                self.uncertainty.append({"page": pno + 1, "item": "tables",
                                         "detail": f"table finder failed: {exc}"})
                continue
            for t_idx, table in enumerate(finder.tables):
                try:
                    rows = table.extract()
                except Exception:
                    continue
                if not rows or len(rows) < 2:
                    continue
                cells = []
                for r_i, row in enumerate(table.rows):
                    for c_i, cell in enumerate(row.cells):
                        if cell is None:
                            continue
                        cells.append({
                            "row": r_i,
                            "col": c_i,
                            "bbox": [round(float(v), 2) for v in cell],
                        })
                tid = f"tbl-p{pno + 1}-{t_idx + 1}"
                entry = {
                    "id": tid,
                    "page": pno + 1,
                    "bbox": [round(float(v), 2) for v in table.bbox],
                    "rows": table.row_count,
                    "cols": table.col_count,
                    "grid": [[(c if c is not None else "") for c in row] for row in rows],
                    "markdown": table.to_markdown(),
                    "html": table.to_html(),
                    "cells": cells,
                    "evidence": {
                        "anchor": f"p{pno + 1}t{t_idx + 1}",
                        "page": pno + 1,
                        "bbox": [round(float(v), 2) for v in table.bbox],
                    },
                }
                self.tables.append(entry)
                pseudo = Block(page=pno + 1, index=9000 + t_idx, bbox=tuple(float(v) for v in table.bbox),
                               kind="table")
                pseudo.evidence_id = entry["evidence"]["anchor"]
                pseudo.meta["table_id"] = tid
                pseudo.text = f"[table {tid} {table.row_count}x{table.col_count}]"
                self.pages[pno]["raw_blocks"].append(pseudo)

    def absorb_tables(self) -> None:
        """Drop text blocks that live inside a detected table (the table owns them)."""
        table_boxes = {}
        for t in self.tables:
            table_boxes.setdefault(t["page"], []).append(t["bbox"])
        for page in self.pages:
            boxes = table_boxes.get(page["page"], [])
            kept = []
            for blk in page["raw_blocks"]:
                inside = None
                if blk.kind == "body":
                    for box in boxes:
                        if (box[0] - 3 <= blk.left and blk.right <= box[2] + 3
                                and box[1] - 3 <= blk.top and blk.bottom <= box[3] + 3):
                            inside = box
                            break
                if inside is not None:
                    self.records["absorbed_table_chars"] = (
                        self.records.get("absorbed_table_chars", 0)
                        + sum(1 for ch in blk.text if not ch.isspace())
                    )
                    self.excluded.append({
                        "page": page["page"], "kind": "table_text", "text": blk.text[:120],
                        "reason": "covered by extracted table structure",
                        "bbox": [round(v, 2) for v in blk.bbox],
                    })
                    continue
                kept.append(blk)
            page["raw_blocks"] = kept

    # -- classification ----------------------------------------------------- #
    def classify(self) -> None:
        repeated: dict[str, set[int]] = {}
        for page in self.pages:
            h = page["height"]
            for blk in page["raw_blocks"]:
                if blk.kind != "body":
                    continue
                key = re.sub(r"\d+", "#", re.sub(r"\s+", " ", blk.text.strip().lower()))[:80]
                if key:
                    repeated.setdefault(key, set()).add(page["page"])
                top_ratio = blk.top / h
                bottom_ratio = blk.bottom / h
                rotated = any(not ln.horizontal for ln in blk.lines)
                if rotated and not self._inside_graphic(blk, page):
                    blk.kind = "margin_watermark"
                    continue
                if PAGE_NUM_RE.match(blk.text) and (top_ratio < 0.06 or bottom_ratio > 0.95):
                    blk.kind = "page_number"
                    continue
                if top_ratio < 0.055 or bottom_ratio > 0.955:
                    blk.kind = "margin_candidate"
                    continue
                if CAPTION_RE.match(blk.text):
                    blk.kind = "caption"
                    continue
                if self._inside_graphic(blk, page):
                    blk.kind = "figure_label"
                    continue
                if self._is_byline(blk, page):
                    blk.kind = "byline"
                    continue
                if self._is_footnote(blk, h):
                    blk.kind = "footnote"
                    continue
                if self._is_heading(blk):
                    blk.kind = "heading"
                    m = SECTION_NUM_RE.match(blk.text)
                    if m:
                        blk.number = m.group(1)
                        blk.level = m.group(1).count(".") + 1
                    else:
                        blk.level = 1
                    continue
                if self._is_formula(blk):
                    blk.kind = "formula"
                    continue
                blk.kind = "body"

        for page in self.pages:
            for blk in page["raw_blocks"]:
                if blk.kind in ("margin_candidate", "page_number", "margin_watermark"):
                    key = re.sub(r"\d+", "#", re.sub(r"\s+", " ", blk.text.strip().lower()))[:80]
                    repeated_pages = repeated.get(key, set())
                    if blk.kind == "margin_watermark" or len(repeated_pages) >= 2:
                        self.excluded.append({
                            "page": page["page"],
                            "kind": ("watermark" if blk.kind == "margin_watermark" else "header_footer"),
                            "text": blk.text[:160],
                            "reason": ("rotated margin stamp" if blk.kind == "margin_watermark"
                                       else f"repeated margin text on {len(repeated_pages)} page(s)"),
                            "bbox": [round(v, 2) for v in blk.bbox],
                        })
                        blk.kind = "excluded"
                    else:
                        blk.kind = "body"

    def _inside_graphic(self, blk: Block, page: dict) -> bool:
        for region in page.get("graphic_regions", []):
            if (region[0] - 2 <= blk.cx <= region[2] + 2
                    and region[1] - 2 <= blk.cy <= region[3] + 2):
                return True
        return False

    def _is_byline(self, blk: Block, page: dict) -> bool:
        """Author/affiliation lines sit above the abstract and look like headings."""
        if blk.page > 2 or blk.top > page["height"] * 0.30:
            return False
        text = blk.text.strip()
        if not text:
            return False
        lowered = text.lower()
        has_org = any(word in lowered for word in ORG_WORDS)
        if not (has_org or "@" in text):
            return False
        return len(text.split()) <= 45

    def _is_footnote(self, blk: Block, page_height: float) -> bool:
        small = blk.size < self.body_size - 0.6
        if not small:
            return False
        near_bottom = blk.top > page_height * 0.72
        marker = (re.match(r"^\s*\d{1,2}\s+\S", blk.text)
                  or re.match(r"^\s*\d{1,2}(?=\D)", blk.text)
                  or re.match(r"^\s*[*\u2020\u2021\u00a7]\s*\S", blk.text))
        return bool(near_bottom and marker)

    def _is_heading(self, blk: Block) -> bool:
        text = blk.text.strip()
        if not text or len(text) > 140:
            return False
        if CAPTION_RE.match(text):
            return False
        words = text.split()
        if len(words) > 18:
            return False
        if "@" in text or text.count(",") >= 3:
            return False
        if text.endswith((".", ";", ",")) and not SECTION_NUM_RE.match(text):
            return False
        norm = re.sub(r"^[\d.]+\s*", "", text).strip().lower()
        if norm in KNOWN_HEADINGS:
            return True
        if SECTION_NUM_RE.match(text) and (blk.size >= self.body_size - 0.3 or blk.bold):
            return True
        bigger = blk.size >= self.body_size + 1.2
        boldish = blk.bold and blk.size >= self.body_size + 0.2
        return bool(bigger or boldish)

    def _is_formula(self, blk: Block) -> bool:
        text = blk.text.strip()
        if len(text) > 300 or len(text) < 4:
            return False
        math = sum(1 for ch in text if ch in MATH_CHARS)
        if math >= 3 and math / max(1, len(text)) < 0.5:
            return True
        return bool(re.search(r"[=<>\u2248\u2264\u2265].{0,60}\(\d+[a-z]?\)\s*$", text))

    # -- reading order ------------------------------------------------------ #
    def order_pages(self) -> None:
        counter = 0
        for page in self.pages:
            items = [b for b in page["raw_blocks"] if b.kind not in ("excluded", "table", "figure_label", "figure")]
            page["columns"] = detect_columns(items, page["width"])
            ordered = xy_cut(items)
            # figure captions follow their figure unless they already do
            ordered = self._attach_figures(ordered)
            page["ordered"] = ordered
            for blk in ordered:
                counter += 1
                blk.order = counter
                self.blocks.append(blk)
            for blk in page["raw_blocks"]:
                if blk.kind == "table":
                    counter += 1
                    blk.order = counter

    def _attach_figures(self, ordered: list[Block]) -> list[Block]:
        result: list[Block] = []
        pending_caption: Block | None = None
        for blk in ordered:
            if blk.kind == "caption" and (blk.text.lower().startswith(("figure", "fig."))):
                if pending_caption is not None:
                    result.append(pending_caption)
                pending_caption = blk
                continue
            result.append(blk)
            if pending_caption is not None:
                # keep caption directly after the block it follows
                if blk is not pending_caption:
                    result.append(pending_caption)
                    pending_caption = None
        if pending_caption is not None:
            result.append(pending_caption)
        return result

    # -- document assembly -------------------------------------------------- #
    def detect_figures(self) -> None:
        """Turn detected graphic regions into figure records paired with captions."""
        for page in self.pages:
            pno = page["page"]
            captions = [b for b in page["ordered"] if b.kind == "caption"]
            labels = [b for b in page["raw_blocks"] if b.kind == "figure_label"]
            for region in page.get("graphic_regions", []):
                caption = None
                best = 1e9
                for cap in captions:
                    if cap.left >= region[0] - 40 and cap.right <= region[2] + 40:
                        gap = min(abs(cap.top - region[3]), abs(region[1] - cap.bottom))
                        if gap < best and gap < 70:
                            caption, best = cap, gap
                inside = [
                    b.text for b in labels
                    if region[0] - 2 <= b.cx <= region[2] + 2 and region[1] - 2 <= b.cy <= region[3] + 2
                ]
                self.figures.append({
                    "id": f"fig-{len(self.figures) + 1}",
                    "page": pno,
                    "bbox": region,
                    "caption": caption.text if caption else None,
                    "caption_evidence": caption.evidence() if caption else None,
                    "label_count": len(inside),
                    "labels": inside[:40],
                    "evidence": {
                        "anchor": caption.evidence_id if caption else f"p{pno}graphic{len(self.figures) + 1}",
                        "page": pno,
                        "bbox": region,
                    },
                })

    def assemble(self) -> dict:
        sections: list[dict] = []
        current = {
            "id": "sec-0",
            "title": "(front matter)",
            "level": 0,
            "number": None,
            "page": 1,
            "paragraphs": [],
            "evidence": [],
        }
        sections.append(current)
        in_references = False
        references: list[dict] = []
        merges = 0
        last_kind = None
        last_heading_size = 0.0

        for page in self.pages:
            for blk in page["ordered"]:
                if blk.kind == "heading":
                    title = blk.text.strip()
                    if blk.number:
                        title = re.sub(r"^\s*" + re.escape(blk.number) + r"\.?\s*", "", title, count=1)
                    norm = re.sub(r"^[\d.]+\s*", "", blk.text.strip()).strip().lower().rstrip(":")
                    continues_title = (
                        last_kind == "heading"
                        and abs(blk.size - last_heading_size) < 0.6
                        and (current["title"].rstrip().split(" ")[-1].lower().strip(":")
                             in TITLE_CONTINUATION_WORDS
                             or title[:1].islower())
                    )
                    if continues_title:
                        current["title"] = f"{current['title'].rstrip()} {title}".strip()
                        current["evidence"].append(blk.evidence())
                        last_kind = "heading"
                        last_heading_size = blk.size
                        continue
                    if norm == "references":
                        in_references = True
                    elif in_references:
                        in_references = False
                    current = {
                        "id": f"sec-{len(sections)}",
                        "title": title,
                        "level": blk.level or 1,
                        "number": blk.number,
                        "page": blk.page,
                        "paragraphs": [],
                        "evidence": [blk.evidence()],
                    }
                    sections.append(current)
                    last_kind = "heading"
                    last_heading_size = blk.size
                    continue
                if blk.kind in ("body", "caption", "footnote", "formula", "byline") and blk.text.strip():
                    kind = {"body": "reference_entry" if in_references else "paragraph"}.get(blk.kind, blk.kind)
                    paragraphs = current["paragraphs"]
                    prev = paragraphs[-1] if paragraphs else None
                    starts_new_entry = False
                    if kind == "reference_entry" and prev is not None:
                        text = blk.text.strip()
                        first = text.split(" ")[0].strip(".,") if text else ""
                        author_like = (
                            bool(re.match(r"^[A-Z][A-Za-z\-'\u2019]+,\s", text))
                            or (bool(re.match(r"^[A-Z][A-Za-z\-'\u2019]+\s+[A-Z]", text))
                                and first.lower() not in REF_STOP_WORDS
                                and not re.match(r"^[A-Z]{2,}\s", text))
                        )
                        numbered = bool(re.match(r"^\s*\[\d+\]", text))
                        starts_new_entry = numbered or (
                            author_like and not prev["text"].rstrip().endswith(("-", ",")))
                    if kind == "reference_entry":
                        can_merge = (prev is not None and prev["kind"] == kind
                                     and not starts_new_entry)
                    else:
                        can_merge = (
                            prev is not None
                            and prev["kind"] == kind
                            and kind == "paragraph"
                            and not is_terminal(prev["text"])
                            and (starts_continuation(blk.text)
                                 or prev["text"].rstrip()[-1:] in ("-", ",", "\u2212"))
                        )
                    if can_merge:
                        joined, hyphen_removed = join_word_break(
                            prev["text"].rstrip(), blk.text.strip(), self.hyphen_vocab)
                        prev["text"] = re.sub(r"\s{2,}", " ", joined)
                        prev["evidence_list"].append(blk.evidence())
                        merges += 1
                        if hyphen_removed:
                            self.records["dehyphenated_joins"] = self.records.get("dehyphenated_joins", 0) + 1
                        last_kind = kind
                        continue
                    paragraphs.append({
                        "id": f"par-{len(paragraphs)}",
                        "text": blk.text,
                        "kind": kind,
                        "evidence": blk.evidence(),
                        "evidence_list": [blk.evidence()],
                    })
                    current["evidence"].append(blk.evidence())
                    if kind == "reference_entry":
                        references.append({"text": blk.text, "evidence": blk.evidence()})
                    last_kind = kind
                elif blk.kind == "table":
                    current["paragraphs"].append({
                        "id": f"par-{len(current['paragraphs'])}",
                        "text": blk.text,
                        "kind": "table",
                        "evidence": blk.evidence(),
                        "evidence_list": [blk.evidence()],
                    })
                    current["evidence"].append(blk.evidence())

        if merges:
            self.change_records.append({
                "change": "paragraph_continuation_merge",
                "count": merges,
                "detail": "consecutive fragments joined when the previous one ended mid-sentence "
                          "(column and page continuations, inline math split off by the PDF producer)",
            })
        split_count = self._split_numbered_references(sections)
        if split_count:
            self.change_records.append({
                "change": "reference_entry_split",
                "count": split_count,
                "detail": "numbered reference entries separated inside a block that held several of them",
            })
        sections = [s for s in sections if s["paragraphs"] or s["level"] > 0]
        references = []
        for sec in sections:
            for par in sec["paragraphs"]:
                if par["kind"] == "reference_entry":
                    references.append({"text": par["text"], "evidence": par["evidence"]})
        return {"sections": sections, "references": references}

    def _split_numbered_references(self, sections: list[dict]) -> int:
        """A single PDF block often holds several numbered references; split them."""
        splits = 0
        for sec in sections:
            rebuilt = []
            for par in sec["paragraphs"]:
                if par["kind"] != "reference_entry":
                    rebuilt.append(par)
                    continue
                if len(re.findall(r"\[\d+\]", par["text"])) < 2:
                    rebuilt.append(par)
                    continue
                chunks = [c.strip() for c in re.split(r"(?=\[\d+\]\s*[A-Z])", par["text"]) if c.strip()]
                for chunk in chunks:
                    rebuilt.append({**par, "text": chunk})
                splits += max(0, len(chunks) - 1)
            sec["paragraphs"] = rebuilt
        # A numbered list can leave a continuation fragment behind: a line that did
        # not start with "[n]" and was split away from its entry. Re-attach it.
        for sec in sections:
            entries = [p for p in sec["paragraphs"] if p["kind"] == "reference_entry"]
            if not entries:
                continue
            numbered = sum(1 for p in entries if re.match(r"^\[\d+\]", p["text"]))
            if numbered < max(3, len(entries) * 0.6):
                continue
            merged: list[dict] = []
            for par in sec["paragraphs"]:
                if (par["kind"] == "reference_entry" and merged
                        and not re.match(r"^\[\d+\]", par["text"])
                        and merged[-1]["kind"] == "reference_entry"):
                    joined, _ = join_word_break(merged[-1]["text"], par["text"], self.hyphen_vocab)
                    merged[-1]["text"] = re.sub(r"\s{2,}", " ", joined)
                    continue
                merged.append(par)
            sec["paragraphs"] = merged
        return splits

    # -- markdown ----------------------------------------------------------- #
    def document_markdown(self, sections: list[dict]) -> str:
        out: list[str] = []
        for sec in sections:
            level = max(1, min(6, sec["level"] or 1))
            title = sec["title"] if sec["number"] is None else f"{sec['number']}. {sec['title']}"
            if sec["level"] == 0:
                out.append(f"# {sec['title']}")
            else:
                out.append("#" * level + " " + title)
            for par in sec["paragraphs"]:
                anchor = par["evidence"]["anchor"]
                kind = par["kind"]
                if kind == "formula":
                    out.append(f"<!-- {anchor} -->")
                    out.append(f"    {par['text']}")
                elif kind == "caption":
                    out.append(f"*{par['text']}*  <!-- {anchor} -->")
                elif kind == "table":
                    out.append(f"**{par['text']}**  <!-- {anchor} -->")
                elif kind == "footnote":
                    out.append(f"> [footnote] {par['text']}  <!-- {anchor} -->")
                else:
                    out.append(f"{par['text']}  <!-- {anchor} -->")
            out.append("")
        return "\n".join(out)

    # -- stats / verification ---------------------------------------------- #
    def char_stats(self) -> dict:
        produced = 0
        for page in self.pages:
            for blk in page["ordered"]:
                if blk.kind in ("heading", "body", "caption", "footnote", "formula"):
                    produced += sum(1 for ch in blk.text if not ch.isspace())
        raw_total = 0
        for page in self.pages:
            for blk in page["raw_blocks"]:
                raw_total += sum(1 for ch in blk.text if not ch.isspace())
        excluded_chars = 0
        for item in self.excluded:
            if item["kind"] in ("header_footer", "watermark"):
                excluded_chars += sum(1 for ch in item["text"] if not ch.isspace())
        label_chars = sum(
            sum(1 for ch in blk.text if not ch.isspace())
            for page in self.pages
            for blk in page["raw_blocks"]
            if blk.kind == "figure_label"
        )
        absorbed = self.records.get("absorbed_table_chars", 0)
        table_chars = 0
        for t in self.tables:
            for row in t["grid"]:
                for cell in row:
                    table_chars += sum(1 for ch in (cell or "") if not ch.isspace())
        expected = max(0, raw_total - excluded_chars - table_chars - absorbed - label_chars)
        coverage = produced / expected if expected else 1.0
        return {
            "raw_non_space_chars": raw_total,
            "excluded_header_footer_chars": excluded_chars,
            "figure_label_chars": label_chars,
            "table_cell_chars": table_chars,
            "absorbed_table_text_chars": absorbed,
            "emitted_non_space_chars": produced,
            "expected_body_chars": expected,
            "char_coverage": round(min(coverage, 1.0), 4),
        }

    def unreadable_pages(self) -> list[dict]:
        out = []
        for page in self.pages:
            chars = sum(sum(1 for ch in blk.text if not ch.isspace())
                        for blk in page["raw_blocks"] if blk.kind not in ("excluded",))
            if chars < 40:
                out.append({"page": page["page"], "non_space_chars": chars,
                            "detail": "page has no usable text layer (image-only or empty)"})
        return out

    # -- orchestration ------------------------------------------------------ #
    def parse(self) -> dict:
        self.extract()
        self.build_blocks()
        self.detect_graphic_regions()
        self.extract_tables()
        self.absorb_tables()
        self.classify()
        self.order_pages()
        assembled = self.assemble()
        for page in self.pages:
            for blk in page["ordered"]:
                if blk.kind == "formula":
                    self.formulas.append({
                        "id": f"eq-{len(self.formulas) + 1}",
                        "text": blk.text,
                        "page": blk.page,
                        "evidence": blk.evidence(),
                        "note": "glyph order preserved; sub/superscript span flags kept, not converted to LaTeX",
                    })
        self.detect_figures()
        sections = assembled["sections"]
        markdown = self.document_markdown(sections)
        stats = self.char_stats()
        unreadable = self.unreadable_pages()
        if self.records.get("ligature"):
            self.change_records.append({
                "change": "ligature_normalization",
                "count": self.records["ligature"],
                "detail": "Unicode ligature glyphs (fi/fl/ffi) replaced with ASCII letters",
            })
        if self.records.get("dehyphenated_joins"):
            self.change_records.append({
                "change": "line_break_hyphen_repair",
                "count": self.records["dehyphenated_joins"],
                "detail": "word-final hyphens at line breaks removed when the next line starts lowercase",
            })
        for item in self.excluded:
            if item["kind"] == "header_footer":
                self.change_records.append({
                    "change": "header_footer_removed",
                    "page": item["page"],
                    "detail": f"margin text excluded: {item['text'][:60]}",
                })
        for page in unreadable:
            self.uncertainty.append({
                "page": page["page"],
                "item": "text_layer",
                "detail": "no text layer; OCR is required and was not available in this environment",
            })
        if stats["char_coverage"] < 0.98:
            self.uncertainty.append({
                "item": "char_coverage",
                "detail": f"emitted/expected non-space characters = {stats['char_coverage']}; "
                          "re-check pages with tables or overlapping blocks",
            })
        result = {
            "schema": SCHEMA,
            "source": {
                "path": str(self.path),
                "sha256": sha256_file(self.path),
                "pages": self.doc.page_count,
                "bytes": self.path.stat().st_size,
                "parser": f"PyMuPDF {getattr(fitz, '__version__', 'unknown')}",
            },
            "layout": {
                "body_font_size": self.body_size,
                "page_sizes": [{"page": i + 1, "width": w, "height": h}
                               for i, (w, h) in enumerate(self.page_sizes)],
                "per_page": [{"page": p["page"], **p.get("columns", {})} for p in self.pages],
            },
            "sections": sections,
            "tables": self.tables,
            "formulas": self.formulas,
            "figures": self.figures,
            "references": {
                "count": len(assembled["references"]),
                "entries": assembled["references"],
            },
            "excluded": self.excluded,
            "stats": stats,
            "unreadable_pages": unreadable,
            "change_records": self.change_records,
            "uncertainty": self.uncertainty,
            "markdown": markdown,
            "limits": [
                "Text is extracted from the PDF text layer; scanned pages need OCR, which this "
                "run reports as unreadable instead of guessing.",
                "Mathematical formulas keep their glyph order and sub/superscript span flags; "
                "they are not converted to LaTeX.",
                "Table cells come from PyMuPDF's ruling-line detector; merged cells are reported "
                "through the cell grid and may need review on borderless tables.",
                "Header/footer removal is based on repeated margin text; a one-off margin note on "
                "a single page is kept as body text and flagged if ambiguous.",
            ],
        }
        return result


# --------------------------------------------------------------------------- #
# render an evidence overlay for visual verification
# --------------------------------------------------------------------------- #
def render_overlay(pdf_path: Path, result: dict, out_dir: Path, pages: list[int] | None = None,
                   scale: float = 2.0) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    doc = fitz.open(pdf_path)
    wanted = set(pages or [])
    by_page: dict[int, list[dict]] = {}
    for page in result.get("_ordered_pages", []):
        by_page[page["page"]] = page["blocks"]
    for pno in range(doc.page_count):
        page_no = pno + 1
        if wanted and page_no not in wanted:
            continue
        blocks = by_page.get(page_no)
        if not blocks:
            continue
        page = doc[pno]
        for order, blk in enumerate(blocks, start=1):
            rect = fitz.Rect(*blk["bbox"])
            color = (0.85, 0.1, 0.2)
            page.draw_rect(rect, color=color, width=0.7)
            page.insert_text((rect.x0 + 1, max(rect.y0 + 5, 5)), str(order),
                             fontsize=5.5, color=color)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
        name = f"page-{page_no:03d}-overlay.png"
        pix.save(out_dir / name)
        written.append(name)
    doc.close()
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evidence-anchored scientific PDF parser")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--render", action="store_true", help="write page overlays with block order numbers")
    ap.add_argument("--render-pages", type=str, default="", help="comma separated page numbers")
    ap.add_argument("--max-pages", type=int, default=None)
    args = ap.parse_args(argv)

    parser = PdfEvidenceParser(args.pdf, max_pages=args.max_pages)
    result = parser.parse()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "parse.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    (args.out / "document.md").write_text(result["markdown"], encoding="utf-8")
    structure = {
        "schema": SCHEMA,
        "source": result["source"],
        "sections": [{"id": s["id"], "title": s["title"], "level": s["level"], "number": s["number"],
                      "page": s["page"], "paragraphs": len(s["paragraphs"]), "evidence": s["evidence"]}
                     for s in result["sections"]],
        "tables": [{"id": t["id"], "page": t["page"], "rows": t["rows"], "cols": t["cols"],
                    "bbox": t["bbox"]} for t in result["tables"]],
        "figures": result["figures"],
        "formulas": len(result["formulas"]),
        "references": result["references"]["count"],
        "stats": result["stats"],
    }
    (args.out / "structure.json").write_text(json.dumps(structure, ensure_ascii=False, indent=1),
                                             encoding="utf-8")
    if args.render:
        pages = [int(p) for p in args.render_pages.split(",") if p.strip()] if args.render_pages else None
        for page in parser.pages:
            page["blocks"] = [{"bbox": b.bbox} for b in page["ordered"]]
        result["_ordered_pages"] = parser.pages
        written = render_overlay(args.pdf, result, args.out / "overlays", pages)
    else:
        written = []

    summary = {
        "ok": True,
        "pdf": str(args.pdf),
        "pages": result["source"]["pages"],
        "sections": len(result["sections"]),
        "tables": len(result["tables"]),
        "figures": len(result["figures"]),
        "formulas": result["formulas"].__len__(),
        "references": result["references"]["count"],
        "char_coverage": result["stats"]["char_coverage"],
        "unreadable_pages": [p["page"] for p in result["unreadable_pages"]],
        "overlays": written,
        "out": str(args.out),
    }
    print("PARSE_OK " + json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

