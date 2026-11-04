#!/usr/bin/env python3
"""Prepare WGDI-preprocess-compatible accession-prefixed aliases without moving raw files.

Upstream pgci_preprocess `_discover_accession` requires gff/cds/pep basenames to
share exactly one NCBI-style `GCA_/GCF_<digits>.<digits>_` prefix. Non-NCBI names
fail with `accession_mismatch`.

This adapter:
  - never deletes or renames original downloads
  - creates hard links (fallback: copy) beside the original as
    `{ACCESSION}_{original_basename}` when needed
  - updates `resources/download_inventory.tsv` gff/cds/pep to the alias names
  - backups prior inventory to `download_inventory.pre_wgdi.tsv` (once per run)
  - writes `resources/wgdi_run_inventory.tsv` (species that have the triangle)
  - writes `resources/wgdi_accession_alias_log.tsv`

Staging aliases under data/downloads may be deleted later; raw originals stay.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import sys
from pathlib import Path

ACCESSION_RE = re.compile(r"^(GC[AF]_\d+\.\d+)_")
PLACEHOLDER_ACCESSION = "GCA_000000000.0"
TRIANGLE = ("gff", "cds", "pep")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project-root", type=Path, default=Path("."))
    p.add_argument(
        "--species",
        default="",
        help="Comma-separated showid filter. Empty = all triangle-complete rows.",
    )
    p.add_argument(
        "--placeholder-accession",
        default=PLACEHOLDER_ACCESSION,
        help="Used when none of gff/cds/pep filenames carry GCA_/GCF_.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan only; do not create links or rewrite inventory.",
    )
    return p.parse_args()


def accession_of(name: str) -> str:
    m = ACCESSION_RE.match(name)
    return m.group(1) if m else ""


def link_or_copy(src: Path, dst: Path) -> str:
    if dst.exists():
        # If already points at same inode or same bytes, keep.
        try:
            if src.samefile(dst):
                return "alias_exists_samefile"
        except OSError:
            pass
        return "alias_exists"
    try:
        os.link(src, dst)
        return "hardlink"
    except OSError:
        shutil.copy2(src, dst)
        return "copy"


def choose_accession(names: list[str], placeholder: str) -> tuple[str, str]:
    found = {accession_of(n) for n in names}
    found.discard("")
    if len(found) == 1:
        return next(iter(found)), "unified_existing"
    if len(found) > 1:
        # Prefer accession already present on cds, then pep, then gff, else first sorted.
        for name in names[1:2] + names[2:3] + names[0:1]:
            acc = accession_of(name)
            if acc:
                return acc, "picked_from_mixed"
        return sorted(found)[0], "picked_from_mixed"
    return placeholder, "placeholder"


def main() -> int:
    args = parse_args()
    root = args.project_root.resolve()
    inventory_path = root / "resources" / "download_inventory.tsv"
    backup_path = root / "resources" / "download_inventory.pre_wgdi.tsv"
    run_inv_path = root / "resources" / "wgdi_run_inventory.tsv"
    alias_log_path = root / "resources" / "wgdi_accession_alias_log.tsv"
    downloads = root / "data" / "downloads"

    if not inventory_path.is_file():
        print(f"ERROR: missing {inventory_path}", file=sys.stderr)
        return 2
    if not downloads.is_dir():
        print(f"ERROR: missing {downloads}", file=sys.stderr)
        return 2

    want = {s.strip() for s in args.species.split(",") if s.strip()} or None

    directories = {
        path.name.split("_", 1)[0]: path
        for path in downloads.iterdir()
        if path.is_dir() and "_" in path.name
    }

    with inventory_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    alias_log: list[dict[str, str]] = []
    run_rows: list[dict[str, str]] = []
    changed = False

    for row in rows:
        showid = (row.get("showid") or "").strip()
        if not showid or showid not in directories:
            continue
        if want is not None and showid not in want:
            continue
        gff = (row.get("gff") or "").strip()
        cds = (row.get("cds") or "").strip()
        pep = (row.get("pep") or "").strip()
        if not (gff and cds and pep):
            continue

        species_dir = directories[showid]
        names = [gff, cds, pep]
        paths = [species_dir / n for n in names]
        missing = [str(p) for p in paths if not p.is_file()]
        if missing:
            alias_log.append(
                {
                    "showid": showid,
                    "file_type": "_triangle",
                    "original": ";".join(names),
                    "alias": "",
                    "accession": "",
                    "action": f"skip_missing:{'|'.join(missing)}",
                }
            )
            continue

        accession, how = choose_accession(names, args.placeholder_accession)
        prefix = f"{accession}_"
        new_names: list[str] = []
        for file_type, name, src in zip(TRIANGLE, names, paths):
            if name.startswith(prefix):
                new_names.append(name)
                alias_log.append(
                    {
                        "showid": showid,
                        "file_type": file_type,
                        "original": name,
                        "alias": name,
                        "accession": accession,
                        "action": "already_prefixed",
                    }
                )
                continue
            # Avoid double-prefix if another accession already present: strip none,
            # always prefix the full original basename for traceability.
            alias = f"{prefix}{name}"
            dst = species_dir / alias
            if args.dry_run:
                action = "dry_run_would_link"
            else:
                action = link_or_copy(src, dst)
                changed = True
            new_names.append(alias)
            alias_log.append(
                {
                    "showid": showid,
                    "file_type": file_type,
                    "original": name,
                    "alias": alias,
                    "accession": accession,
                    "action": f"{action};{how}",
                }
            )

        # Update inventory columns to aliases.
        for file_type, new_name in zip(TRIANGLE, new_names):
            if (row.get(file_type) or "").strip() != new_name:
                row[file_type] = new_name
                changed = True

        run_rows.append(
            {
                "showid": showid,
                "Order": row.get("Order", ""),
                "Family": row.get("Family", ""),
                "Species": row.get("Species", ""),
                "gff": new_names[0],
                "genome": row.get("genome", ""),
                "cds": new_names[1],
                "pep": new_names[2],
                "rna": row.get("rna", ""),
                "gbff": row.get("gbff", ""),
                "gtf": row.get("gtf", ""),
                "accession": accession,
                "directory": species_dir.name,
            }
        )

    if not args.dry_run:
        if changed and not backup_path.is_file():
            shutil.copy2(inventory_path, backup_path)
            print(f"Backup inventory → {backup_path}")
        elif changed:
            # Always refresh pre_wgdi? Keep existing backup once.
            print(f"Kept existing backup: {backup_path}")

        if changed:
            with inventory_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore"
                )
                writer.writeheader()
                writer.writerows(rows)
            print(f"Updated inventory: {inventory_path}")

        run_fields = [
            "showid",
            "Order",
            "Family",
            "Species",
            "gff",
            "genome",
            "cds",
            "pep",
            "rna",
            "gbff",
            "gtf",
            "accession",
            "directory",
        ]
        with run_inv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=run_fields, delimiter="\t")
            writer.writeheader()
            writer.writerows(run_rows)

        with alias_log_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["showid", "file_type", "original", "alias", "accession", "action"],
                delimiter="\t",
            )
            writer.writeheader()
            writer.writerows(alias_log)

    print(f"Triangle-ready species prepared: {len(run_rows)}")
    print(f"Alias log entries: {len(alias_log)}" + (" (dry-run)" if args.dry_run else ""))
    if not args.dry_run:
        print(f"wgdi_run_inventory: {run_inv_path}")
        print(f"alias log: {alias_log_path}")
        print("Note: alias files under data/downloads may be deleted; raw originals must stay.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
