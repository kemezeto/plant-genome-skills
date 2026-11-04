#!/usr/bin/env python3
"""Bridge: preprocess_input_manifest.tsv → download_inventory.tsv basenames for HXC.

HXC discover_species reads resources/download_inventory.tsv columns
showid/Species/Order/Family/gff/cds/pep and expects a *single* basename per
column (no '|' joins). This script writes basenames from the stage-2
canonical manifest into those columns without deleting other inventory rows.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

INVENTORY_TYPES = ("gff", "gtf", "cds", "pep", "gbff", "genome", "rna")
FOLDER_RE = re.compile(
    r"^(?P<showid>[^_]+)_(?P<Order>[^_]+)_(?P<Family>[^(]+)\((?P<Species>.+)\)$"
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--project-root",
        type=Path,
        default=Path("."),
        help="Project root with resources/ and data/downloads/",
    )
    p.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Default: resources/preprocess_input_manifest.tsv",
    )
    p.add_argument(
        "--inventory",
        type=Path,
        default=None,
        help="Default: resources/download_inventory.tsv",
    )
    p.add_argument(
        "--bridge-log",
        type=Path,
        default=None,
        help="Default: resources/preprocess_bridge_log.tsv",
    )
    return p.parse_args()


def folder_meta(downloads: Path) -> dict[str, dict[str, str]]:
    meta: dict[str, dict[str, str]] = {}
    if not downloads.is_dir():
        return meta
    for path in downloads.iterdir():
        if not path.is_dir() or "_" not in path.name:
            continue
        m = FOLDER_RE.match(path.name)
        if not m:
            showid = path.name.split("_", 1)[0]
            meta[showid] = {
                "showid": showid,
                "Order": "",
                "Family": "",
                "Species": "",
                "folder": path.name,
            }
            continue
        d = m.groupdict()
        d["folder"] = path.name
        meta[d["showid"]] = d
    return meta


def load_manifest(path: Path) -> dict[str, dict[str, dict[str, str]]]:
    """showid -> file_type -> row."""
    by: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            showid = (row.get("showid") or "").strip()
            file_type = (row.get("file_type") or "").strip()
            if not showid or file_type not in INVENTORY_TYPES:
                continue
            by[showid][file_type] = row
    return by


def ensure_inventory_fields(fieldnames: list[str]) -> list[str]:
    required = [
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
    ]
    out = list(fieldnames) if fieldnames else []
    for col in required:
        if col not in out:
            out.append(col)
    return out


def main() -> int:
    args = parse_args()
    root = args.project_root.resolve()
    manifest_path = args.manifest or (root / "resources" / "preprocess_input_manifest.tsv")
    inventory_path = args.inventory or (root / "resources" / "download_inventory.tsv")
    bridge_log_path = args.bridge_log or (root / "resources" / "preprocess_bridge_log.tsv")
    downloads = root / "data" / "downloads"

    if not manifest_path.is_file():
        print(f"ERROR: manifest not found: {manifest_path}", file=sys.stderr)
        return 2
    if not inventory_path.is_file():
        print(f"ERROR: inventory not found: {inventory_path}", file=sys.stderr)
        return 2

    by_show = load_manifest(manifest_path)
    folders = folder_meta(downloads)

    with inventory_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = ensure_inventory_fields(list(reader.fieldnames or []))
        rows = list(reader)
    index = {(row.get("showid") or "").strip(): row for row in rows}

    bridge_rows: list[dict[str, str]] = []
    gtf_as_gff_warnings: list[str] = []

    def touch_row(showid: str) -> dict[str, str]:
        row = index.get(showid)
        if row is None:
            meta = folders.get(showid, {})
            sample = by_show.get(showid, {})
            species = ""
            for ft_row in sample.values():
                species = (ft_row.get("Species") or "").strip()
                if species:
                    break
            row = {col: "" for col in fieldnames}
            row["showid"] = showid
            row["Order"] = meta.get("Order", "")
            row["Family"] = meta.get("Family", "")
            row["Species"] = meta.get("Species") or species
            rows.append(row)
            index[showid] = row
            bridge_rows.append(
                {
                    "showid": showid,
                    "file_type": "_row",
                    "basename": "",
                    "action": "added_inventory_row",
                }
            )
        else:
            for col in fieldnames:
                row.setdefault(col, "")
        return row

    for showid, typed in sorted(by_show.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else kv[0]):
        row = touch_row(showid)
        # Fill Species/Order/Family gaps from folder when empty.
        meta = folders.get(showid, {})
        for key in ("Order", "Family", "Species"):
            if not (row.get(key) or "").strip() and meta.get(key):
                row[key] = meta[key]

        chosen: dict[str, str] = {}
        for file_type, mrow in typed.items():
            chosen_path = (mrow.get("chosen_path") or "").strip()
            if not chosen_path:
                continue
            basename = Path(chosen_path).name
            chosen[file_type] = basename

        # gff column: prefer gff, else gtf (HXC only reads gff).
        if "gff" in chosen:
            gff_name = chosen["gff"]
            action = "set_gff"
        elif "gtf" in chosen:
            gff_name = chosen["gtf"]
            action = "set_gff_from_gtf"
            gtf_as_gff_warnings.append(f"{showid}:{gff_name}")
            print(
                f"WARNING: showid={showid} has no gff; writing gtf basename into gff column: {gff_name}",
                file=sys.stderr,
            )
        else:
            gff_name = ""
            action = "clear_or_skip_gff"

        if gff_name:
            old = (row.get("gff") or "").strip()
            if old != gff_name:
                row["gff"] = gff_name
                bridge_rows.append(
                    {
                        "showid": showid,
                        "file_type": "gff",
                        "basename": gff_name,
                        "action": action if old == "" else f"replace_gff_was:{old}",
                    }
                )
            else:
                bridge_rows.append(
                    {
                        "showid": showid,
                        "file_type": "gff",
                        "basename": gff_name,
                        "action": "unchanged",
                    }
                )

        for file_type in ("gtf", "cds", "pep", "gbff", "genome", "rna"):
            if file_type not in chosen:
                continue
            basename = chosen[file_type]
            old = (row.get(file_type) or "").strip()
            if old != basename:
                row[file_type] = basename
                bridge_rows.append(
                    {
                        "showid": showid,
                        "file_type": file_type,
                        "basename": basename,
                        "action": "set" if old == "" else f"replace_was:{old}",
                    }
                )
            else:
                bridge_rows.append(
                    {
                        "showid": showid,
                        "file_type": file_type,
                        "basename": basename,
                        "action": "unchanged",
                    }
                )

    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    with inventory_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    with bridge_log_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["showid", "file_type", "basename", "action"],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(bridge_rows)

    complete = 0
    for row in rows:
        if (row.get("gff") or "").strip() and (row.get("cds") or "").strip() and (row.get("pep") or "").strip():
            complete += 1

    print(f"Updated inventory: {inventory_path}")
    print(f"Bridge log: {bridge_log_path} ({len(bridge_rows)} actions)")
    print(f"Species with complete gff+cds+pep triangle (HXC-runnable candidates): {complete}")
    if gtf_as_gff_warnings:
        print(f"gtf-as-gff warnings: {len(gtf_as_gff_warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
