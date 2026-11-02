#!/usr/bin/env python3
"""Re-label file_type on an existing assembly_download_links.tsv without re-fetching.

Also promotes none rows whose portal_url is itself a direct file URL into a
classified download row (still no HTTP).
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

from classify_file_type import classify_row

FIELDS = [
    "show_id",
    "Species",
    "Ploidy",
    "portal_url",
    "file_type",
    "label",
    "download_url",
    "notes",
]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "-i",
        "--input",
        type=Path,
        default=Path("resources/assembly_download_links.tsv"),
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("resources/assembly_download_links_reclassified.tsv"),
    )
    p.add_argument(
        "--in-place",
        action="store_true",
        help="replace input with reclassified output after writing",
    )
    args = p.parse_args()

    with args.input.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    before = Counter((r.get("file_type") or "none") for r in rows)
    moved_from_other = Counter()
    changed = 0
    direct_promoted = 0
    out_rows: list[dict[str, str]] = []

    for r in rows:
        old_ft = (r.get("file_type") or "none").strip() or "none"
        old_url = (r.get("download_url") or "").strip()
        label = r.get("label") or ""
        portal = r.get("portal_url") or ""
        new_ft, new_url, notes_addon = classify_row(old_url, label, portal)

        notes = (r.get("notes") or "").strip()
        if notes_addon:
            notes = f"{notes};{notes_addon}" if notes else notes_addon
            direct_promoted += 1

        if new_ft != old_ft or new_url != old_url:
            changed += 1
            if old_ft == "other" and new_ft != old_ft:
                moved_from_other[new_ft] += 1
            # also track former none that gained a type
            if old_ft == "none" and new_ft != "none":
                moved_from_other[f"none->{new_ft}"] += 1

        out = {k: r.get(k, "") for k in FIELDS}
        out["file_type"] = new_ft
        out["download_url"] = new_url
        out["notes"] = notes
        out_rows.append(out)

    after = Counter((r.get("file_type") or "none") for r in out_rows)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(out_rows)

    if args.in_place:
        args.output.replace(args.input)
        final_path = args.input
    else:
        final_path = args.output

    print(f"rows={len(out_rows)} changed={changed} direct_portal_promoted={direct_promoted}", file=sys.stderr)
    print(f"wrote {final_path}", file=sys.stderr)
    print("BEFORE:", file=sys.stderr)
    for k, c in before.most_common():
        print(f"  {k}\t{c}", file=sys.stderr)
    print("AFTER:", file=sys.stderr)
    for k, c in after.most_common():
        print(f"  {k}\t{c}", file=sys.stderr)
    print("MOVED_FROM_OTHER (and none promotions):", file=sys.stderr)
    for k, c in moved_from_other.most_common():
        print(f"  {k}\t{c}", file=sys.stderr)


if __name__ == "__main__":
    main()
