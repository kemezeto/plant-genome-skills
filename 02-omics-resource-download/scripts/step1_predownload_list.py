#!/usr/bin/env python3
"""Step 1: build predownload list with species-level dedup and ranking."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
import unicodedata
from pathlib import Path

KEEP_COLS = [
    "show_id",
    "Species",
    "Ploidy",
    "Order",
    "Family",
    "Genome assembly",
]

EMPTY_SPECIES = {"", "na", "n/a", "nan", "none", "null"}


def normalize_species(name: str | None) -> str:
    """Strip controls, collapse whitespace, casefold for dedup key."""
    if name is None:
        return ""
    s = unicodedata.normalize("NFKC", str(name))
    s = "".join(ch for ch in s if unicodedata.category(ch)[0] != "C")
    s = re.sub(r"\s+", " ", s).strip()
    return s.casefold()


def is_empty_species(name: str | None) -> bool:
    key = normalize_species(name)
    return (not key) or key in EMPTY_SPECIES


def parse_year(raw: str | None, current_year: int) -> int:
    """Extract 4-digit publish year; missing/invalid -> far from current."""
    if raw is None:
        return -10_000
    s = str(raw).strip()
    if not s or s.upper() in {"NA", "N/A", "NAN", "NONE", "NULL"}:
        return -10_000
    m = re.search(r"(19|20)\d{2}", s)
    if not m:
        return -10_000
    return int(m.group(0))


def species_rank(row: dict[str, str], current_year: int) -> tuple:
    """Smaller tuple is better (kept)."""
    year = parse_year(row.get("Publish year"), current_year)
    try:
        sid = int(str(row.get("show_id", "")).strip())
    except ValueError:
        sid = 10**18
    return (abs(year - current_year), -year, sid)


def build_predownload_list(
    input_csv: Path,
    output_tsv: Path,
    current_year: int | None = None,
) -> tuple[int, int, int]:
    current_year = current_year or dt.date.today().year
    with input_csv.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    needed = ["show_id", "Species", "Ploidy", "Order", "Family", "Genome assembly", "Publish year"]
    if rows:
        missing = [c for c in needed if c not in rows[0]]
        if missing:
            raise SystemExit(f"missing columns in input: {missing}")

    filtered: list[dict[str, str]] = []
    dropped_empty = 0
    for r in rows:
        if is_empty_species(r.get("Species")):
            dropped_empty += 1
            continue
        filtered.append(r)

    best: dict[str, dict[str, str]] = {}
    for r in filtered:
        key = normalize_species(r.get("Species"))
        if key not in best or species_rank(r, current_year) < species_rank(best[key], current_year):
            best[key] = r

    out_rows: list[dict[str, str]] = []
    for r in sorted(best.values(), key=lambda x: species_rank(x, current_year)):
        out_rows.append(
            {
                "show_id": (r.get("show_id") or "").strip(),
                "Species": (r.get("Species") or "").strip(),
                "Ploidy": (r.get("Ploidy") or "NA").strip() or "NA",
                "Order": (r.get("Order") or "NA").strip() or "NA",
                "Family": (r.get("Family") or "NA").strip() or "NA",
                "Genome assembly": (r.get("Genome assembly") or "NA").strip() or "NA",
            }
        )

    # stable by show_id for readability
    out_rows.sort(key=lambda x: int(x["show_id"]) if x["show_id"].isdigit() else 10**18)

    output_tsv.parent.mkdir(parents=True, exist_ok=True)
    with output_tsv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=KEEP_COLS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(out_rows)

    return len(rows), dropped_empty, len(out_rows)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-i", "--input", type=Path, required=True, help="raw resource CSV")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("resources/predownload_list.tsv"),
        help="output TSV",
    )
    p.add_argument(
        "--year",
        type=int,
        default=None,
        help="current year for ranking (default: local today)",
    )
    args = p.parse_args()
    n_in, n_empty, n_out = build_predownload_list(args.input, args.output, args.year)
    print(
        f"input_rows={n_in} dropped_empty_species={n_empty} "
        f"unique_species={n_out} wrote={args.output}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
