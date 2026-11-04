#!/usr/bin/env python3
"""Scan data/downloads/ and write a per-file raw catalog TSV.

Heterogeneous downloads from many portals → one row per file with
file_type / format / compression / size / source_hint.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlparse

# allow `python3 /path/to/scripts/step0_classify_raw.py` without PYTHONPATH
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from classify_local import (  # noqa: E402
    PRIMARY_TYPES,
    classify_local_filename,
    detect_compression,
    detect_format,
    source_hint_from_url,
    url_basename,
)

_FOLDER_RE = re.compile(
    r"^(?P<showid>.+?)_(?P<order>.+?)_(?P<family>.+?)\((?P<species>.+)\)$"
)

CATALOG_COLS = [
    "showid",
    "Order",
    "Family",
    "Species",
    "folder",
    "filename",
    "file_type",
    "format",
    "compression",
    "size_bytes",
    "size_mb",
    "source_hint",
    "notes",
]

MAX_MB_NOTE = 300
MAX_BYTES_NOTE = MAX_MB_NOTE * 1024 * 1024


def parse_folder_name(name: str) -> dict[str, str] | None:
    m = _FOLDER_RE.match(name)
    if not m:
        return None
    return {
        "showid": m.group("showid"),
        "Order": m.group("order"),
        "Family": m.group("family"),
        "Species": m.group("species"),
    }


def load_links_index(links_path: Path | None) -> dict[str, list[dict[str, str]]]:
    """showid → list of {basename, source_hint, download_url, file_type}."""
    idx: dict[str, list[dict[str, str]]] = defaultdict(list)
    if links_path is None or not links_path.is_file():
        return idx
    with links_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            sid = (row.get("show_id") or row.get("showid") or "").strip()
            url = (row.get("download_url") or "").strip()
            if not sid:
                continue
            bn = url_basename(url).lower()
            hint = source_hint_from_url(url) or source_hint_from_url(
                (row.get("portal_url") or "").strip()
            )
            idx[sid].append(
                {
                    "basename": bn,
                    "source_hint": hint,
                    "download_url": url,
                    "file_type": (row.get("file_type") or "").strip(),
                }
            )
    return idx


def match_source_hint(
    showid: str, filename: str, links_idx: dict[str, list[dict[str, str]]]
) -> str:
    candidates = links_idx.get(showid) or links_idx.get(str(showid)) or []
    if not candidates:
        return ""
    fn = filename.lower()
    # exact basename match
    for c in candidates:
        if c["basename"] and c["basename"] == fn:
            return c["source_hint"] or "manual"
    # basename without compression
    fn_stem = re.sub(r"\.(gz|bz2|xz|zip|tar\.gz|tgz)$", "", fn)
    for c in candidates:
        bn = c["basename"]
        if not bn:
            continue
        bn_stem = re.sub(r"\.(gz|bz2|xz|zip|tar\.gz|tgz)$", "", bn)
        if bn_stem == fn_stem or bn in fn or fn in bn:
            return c["source_hint"] or "manual"
    # showid has links but no basename match → mark manual (do not guess portal)
    if candidates:
        return "manual"
    return ""


def should_skip_name(name: str) -> bool:
    if name.startswith("."):
        return True
    if name.endswith(".partial") or name.endswith(".tmp") or name.endswith(".part"):
        return True
    return False


def build_notes(path: Path, file_type: str, size: int) -> str:
    notes: list[str] = []
    if size == 0:
        notes.append("empty_file")
    if size > MAX_BYTES_NOTE:
        notes.append("over_300mb")
        notes.append("skipped_size")
    if file_type.startswith("other_") and "tar" in file_type:
        notes.append("multi_type_archive")
    if file_type == "other_annotation_pack":
        notes.append("multi_type_archive")
    if file_type == "unknown":
        notes.append("unclassified")
    return ";".join(notes)


def scan_downloads(
    downloads_dir: Path,
    links_idx: dict[str, list[dict[str, str]]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not downloads_dir.is_dir():
        return rows
    for folder in sorted(downloads_dir.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        meta = parse_folder_name(folder.name)
        if meta is None:
            meta = {
                "showid": "",
                "Order": "",
                "Family": "",
                "Species": "",
            }
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            # skip nested junk / hidden
            rel_parts = path.relative_to(folder).parts
            if any(p.startswith(".") for p in rel_parts):
                continue
            if should_skip_name(path.name):
                continue
            # only top-level files by default? include nested but record relative name
            rel_name = str(path.relative_to(folder)).replace("\\", "/")
            size = path.stat().st_size
            ft = classify_local_filename(path.name)
            fmt = detect_format(path.name)
            comp = detect_compression(path.name)
            hint = match_source_hint(meta["showid"], path.name, links_idx)
            if not hint:
                hint = ""
            notes = build_notes(path, ft, size)
            rows.append(
                {
                    "showid": meta["showid"],
                    "Order": meta["Order"],
                    "Family": meta["Family"],
                    "Species": meta["Species"],
                    "folder": folder.name,
                    "filename": rel_name if "/" in rel_name else path.name,
                    "file_type": ft,
                    "format": fmt,
                    "compression": comp,
                    "size_bytes": str(size),
                    "size_mb": f"{size / (1024 * 1024):.4f}",
                    "source_hint": hint,
                    "notes": notes,
                }
            )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--downloads-dir",
        type=Path,
        default=Path("data/downloads"),
        help="Per-species download folders (default: data/downloads)",
    )
    ap.add_argument(
        "--links",
        type=Path,
        default=None,
        help="Optional assembly_download_links.tsv for source_hint",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("resources/raw_file_catalog.tsv"),
        help="Output catalog TSV",
    )
    args = ap.parse_args()

    links_path = args.links
    if links_path is None:
        # convention: sibling resources/ under project root
        candidate = Path("resources/assembly_download_links.tsv")
        if candidate.is_file():
            links_path = candidate

    links_idx = load_links_index(links_path)
    rows = scan_downloads(args.downloads_dir, links_idx)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CATALOG_COLS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    n_sp = len({r["showid"] for r in rows if r["showid"]})
    primary = sum(1 for r in rows if r["file_type"] in PRIMARY_TYPES)
    print(
        f"Wrote {args.output}: {len(rows)} files / {n_sp} species "
        f"(primary_types={primary}; links={'yes' if links_path else 'no'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
