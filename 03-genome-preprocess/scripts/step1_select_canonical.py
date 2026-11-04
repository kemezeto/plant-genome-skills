#!/usr/bin/env python3
"""Pick one canonical file per (species, file_type) for preprocess input.

Priority rules (see references/raw-classify.md):
  gff:  gff3 > gff > (gtf is separate type)
  genome: fna > fasta > fa
  pep: faa > fasta/fa with pep token
  Prefer non-empty, not over_300mb / skipped_size.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

TARGET_TYPES = ("genome", "gff", "gtf", "gbff", "cds", "pep", "rna")

# Higher score = preferred
FORMAT_SCORE = {
    "gff": {"gff3": 30, "gff": 20, "unknown": 5},
    "gtf": {"gtf": 30, "unknown": 5},
    "gbff": {"gbff": 30, "unknown": 5},
    "genome": {"fna": 30, "fasta": 20, "fa": 15, "unknown": 5},
    "cds": {"fna": 25, "fasta": 20, "fa": 15, "unknown": 5},
    "pep": {"faa": 30, "fasta": 20, "fa": 15, "unknown": 5},
    "rna": {"fna": 25, "fasta": 20, "fa": 15, "unknown": 5},
}

COMP_PENALTY = {
    "none": 0,
    "gz": -1,
    "bz2": -2,
    "xz": -2,
    "zip": -5,
    "tgz": -8,
    "tbz2": -8,
    "txz": -8,
}

OUT_COLS = [
    "showid",
    "Species",
    "file_type",
    "chosen_path",
    "format",
    "compression",
    "size_bytes",
    "source_hint",
    "rejected_alts",
    "notes",
]


def score_row(r: dict[str, str]) -> tuple:
    ft = r.get("file_type") or ""
    fmt = r.get("format") or "unknown"
    notes = r.get("notes") or ""
    size = int(r.get("size_bytes") or 0)
    comp = r.get("compression") or "none"

    # hard demote empty / oversized (still selectable if only option)
    hard = 0
    if "empty_file" in notes:
        hard -= 1000
    if "skipped_size" in notes or "over_300mb" in notes:
        hard -= 500
    if ft.startswith("other_"):
        hard -= 200

    fmt_s = FORMAT_SCORE.get(ft, {}).get(fmt, 5)
    comp_s = COMP_PENALTY.get(comp, -3)
    # prefer larger non-empty within reason (proxy for complete file)
    size_s = min(size, 50 * 1024 * 1024)  # cap influence
    return (hard + fmt_s + comp_s, size_s, r.get("filename") or "")


def load_catalog(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def select(rows: list[dict[str, str]], downloads_dir: Path) -> list[dict[str, str]]:
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        ft = r.get("file_type") or ""
        if ft not in TARGET_TYPES:
            continue
        sid = r.get("showid") or ""
        groups[(sid, ft)].append(r)

    out: list[dict[str, str]] = []
    for (sid, ft), items in sorted(groups.items()):
        ranked = sorted(items, key=score_row, reverse=True)
        best = ranked[0]
        alts = ranked[1:]
        folder = best.get("folder") or ""
        fn = best.get("filename") or ""
        chosen = str((downloads_dir / folder / fn).as_posix()) if folder else fn
        rej = "|".join(
            f"{a.get('filename')}({a.get('format')})" for a in alts
        )
        notes = []
        bn = best.get("notes") or ""
        if "empty_file" in bn:
            notes.append("chosen_empty")
        if "skipped_size" in bn or "over_300mb" in bn:
            notes.append("chosen_over_300mb")
        if alts:
            notes.append(f"n_alts={len(alts)}")
        out.append(
            {
                "showid": sid,
                "Species": best.get("Species") or "",
                "file_type": ft,
                "chosen_path": chosen,
                "format": best.get("format") or "",
                "compression": best.get("compression") or "",
                "size_bytes": best.get("size_bytes") or "0",
                "source_hint": best.get("source_hint") or "",
                "rejected_alts": rej,
                "notes": ";".join(notes),
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "-i",
        "--catalog",
        type=Path,
        default=Path("resources/raw_file_catalog.tsv"),
    )
    ap.add_argument(
        "--downloads-dir",
        type=Path,
        default=Path("data/downloads"),
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("resources/preprocess_input_manifest.tsv"),
    )
    args = ap.parse_args()

    if not args.catalog.is_file():
        raise SystemExit(f"catalog not found: {args.catalog}")

    rows = load_catalog(args.catalog)
    chosen = select(rows, args.downloads_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_COLS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for r in chosen:
            w.writerow(r)
    print(f"Wrote {args.output}: {len(chosen)} canonical selections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
