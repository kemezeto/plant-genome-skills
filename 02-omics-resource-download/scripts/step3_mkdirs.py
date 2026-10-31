#!/usr/bin/env python3
"""Step 3a: create one download folder per show_id from predownload_list.tsv."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from step3_common import downloads_root, folder_name  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "-i",
        "--predownload",
        type=Path,
        default=Path("resources/predownload_list.tsv"),
        help="Species-deduped predownload list",
    )
    ap.add_argument(
        "-d",
        "--downloads-dir",
        type=Path,
        default=None,
        help="Root for per-show_id folders (default: data/downloads)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print folder names only; do not create",
    )
    args = ap.parse_args()

    project_root = Path.cwd()
    out_root = args.downloads_dir or downloads_root(project_root)
    needed = ["show_id", "Species", "Order", "Family"]

    with args.predownload.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    if not rows:
        raise SystemExit(f"empty predownload list: {args.predownload}")
    missing = [c for c in needed if c not in rows[0]]
    if missing:
        raise SystemExit(f"missing columns: {missing}")

    if not args.dry_run:
        out_root.mkdir(parents=True, exist_ok=True)

    created = 0
    existed = 0
    names: list[str] = []
    for r in rows:
        name = folder_name(r["show_id"], r["Order"], r["Family"], r["Species"])
        names.append(name)
        dest = out_root / name
        if args.dry_run:
            continue
        if dest.exists():
            existed += 1
        else:
            dest.mkdir(parents=True, exist_ok=True)
            created += 1

    if args.dry_run:
        print(f"dry-run: would create {len(names)} folders under {out_root}")
        for n in names[:5]:
            print(f"  example: {n}")
        if len(names) > 5:
            print(f"  ... ({len(names) - 5} more)")
    else:
        print(
            f"downloads root: {out_root}\n"
            f"rows: {len(names)}\n"
            f"created: {created}\n"
            f"already_existed: {existed}"
        )
        for n in names[:5]:
            print(f"  example: {n}")


if __name__ == "__main__":
    main()
