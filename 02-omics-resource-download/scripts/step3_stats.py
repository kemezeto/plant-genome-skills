#!/usr/bin/env python3
"""Step 3c: inventory files under data/downloads/ into download_inventory.tsv.

Does NOT read predownload_list or assembly_download_links — only folder names
and files present on disk. Folder naming: showid_Order_Family(Species).
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from step3_common import (  # noqa: E402
    ALLOWED_FILE_TYPES,
    classify_local_filename,
    downloads_root,
    parse_folder_name,
)

OUT_COLS = [
    "showid",
    "Order",
    "Family",
    "Species",
    *ALLOWED_FILE_TYPES,
]


def inventory_folder(folder: Path) -> dict[str, str]:
    meta = parse_folder_name(folder.name)
    if meta is None:
        return {}
    found: dict[str, str] = {t: "" for t in ALLOWED_FILE_TYPES}
    if not folder.is_dir():
        return {**meta, **found}
    # Prefer non-partial, non-hidden files
    files = sorted(
        p for p in folder.iterdir() if p.is_file() and not p.name.startswith(".")
        and not p.name.endswith(".partial")
    )
    for p in files:
        typ = classify_local_filename(p.name)
        if typ is None:
            continue
        # Keep first filename per type; if multiple, join with |
        if found[typ]:
            if p.name not in found[typ].split("|"):
                found[typ] = found[typ] + "|" + p.name
        else:
            found[typ] = p.name
    return {
        "showid": meta["showid"],
        "Order": meta["Order"],
        "Family": meta["Family"],
        "Species": meta["Species"],
        **found,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "-d",
        "--downloads-dir",
        type=Path,
        default=None,
        help="Root of per-show_id folders (default: data/downloads)",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("resources/download_inventory.tsv"),
    )
    args = ap.parse_args()

    root = args.downloads_dir or downloads_root(Path.cwd())
    if not root.is_dir():
        raise SystemExit(f"downloads dir not found: {root}")

    rows: list[dict[str, str]] = []
    skipped = 0
    for child in root.iterdir():
        if not child.is_dir():
            continue
        rec = inventory_folder(child)
        if not rec:
            skipped += 1
            continue
        rows.append(rec)

    def _sid_key(r: dict[str, str]) -> tuple:
        s = r.get("showid", "")
        try:
            return (0, int(s))
        except ValueError:
            return (1, s)

    rows.sort(key=_sid_key)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUT_COLS, delimiter="\t")
        w.writeheader()
        w.writerows(rows)

    # Presence counts
    counts = {t: 0 for t in ALLOWED_FILE_TYPES}
    for r in rows:
        for t in ALLOWED_FILE_TYPES:
            if r.get(t):
                counts[t] += 1

    print(
        f"scanned: {root}\n"
        f"folders: {len(rows)} (skipped_unparsed: {skipped})\n"
        f"wrote: {args.output}"
    )
    print("presence_counts:", " ".join(f"{k}={v}" for k, v in counts.items()))
    # Sample first 3 rows for stdout
    for r in rows[:3]:
        nonempty = {k: r[k] for k in ALLOWED_FILE_TYPES if r[k]}
        print(f"  sample showid={r['showid']} files={nonempty or '{}'}")


if __name__ == "__main__":
    main()
