#!/usr/bin/env python3
"""Summarize raw_file_catalog.tsv → type matrix + markdown/tsv stats."""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

PRIMARY = ("gff", "gtf", "gbff", "genome", "cds", "pep", "rna")
# matrix columns focus on what stage-1 inventory tracked + format diversity
MATRIX_TYPES = ("gff", "gtf", "gbff", "genome", "cds", "pep", "rna")


def load_catalog(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def build_matrix(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    # showid → meta + type → list of "filename(format)" or "filename"
    by_sp: dict[str, dict] = {}
    for r in rows:
        sid = r.get("showid") or ""
        key = sid or r.get("folder") or "?"
        if key not in by_sp:
            by_sp[key] = {
                "showid": sid,
                "Order": r.get("Order", ""),
                "Family": r.get("Family", ""),
                "Species": r.get("Species", ""),
                "folder": r.get("folder", ""),
                "types": defaultdict(list),
            }
        ft = r.get("file_type") or "unknown"
        fn = r.get("filename") or ""
        fmt = r.get("format") or "unknown"
        label = f"{fn}:{fmt}" if fmt and fmt != "unknown" else fn
        notes = r.get("notes") or ""
        if "over_300mb" in notes or "skipped_size" in notes:
            label += "[skipped_size]"
        if "empty_file" in notes:
            label += "[empty]"
        by_sp[key]["types"][ft].append(label)

    out: list[dict[str, str]] = []
    for key in sorted(by_sp.keys(), key=lambda x: (len(x), x)):
        sp = by_sp[key]
        row = {
            "showid": sp["showid"],
            "Order": sp["Order"],
            "Family": sp["Family"],
            "Species": sp["Species"],
            "folder": sp["folder"],
        }
        for t in MATRIX_TYPES:
            files = sp["types"].get(t) or []
            row[t] = "|".join(files)
        # extras: other_* collapsed
        extras = []
        for t, files in sorted(sp["types"].items()):
            if t in MATRIX_TYPES:
                continue
            extras.append(f"{t}=" + "|".join(files))
        row["other"] = ";".join(extras)
        out.append(row)
    return out


def write_matrix(path: Path, matrix: list[dict[str, str]]) -> None:
    cols = [
        "showid",
        "Order",
        "Family",
        "Species",
        "folder",
        *MATRIX_TYPES,
        "other",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for r in matrix:
            w.writerow(r)


def summarize(rows: list[dict[str, str]], matrix: list[dict[str, str]]) -> str:
    ft_c = Counter(r.get("file_type") or "unknown" for r in rows)
    fmt_c = Counter(r.get("format") or "unknown" for r in rows)
    comp_c = Counter(r.get("compression") or "none" for r in rows)
    n_sp = len({r.get("showid") for r in rows if r.get("showid")})
    empty = sum(1 for r in rows if "empty_file" in (r.get("notes") or ""))
    over = sum(1 for r in rows if "over_300mb" in (r.get("notes") or ""))

    # missing primary types per species (species that have at least one file)
    missing: dict[str, list[str]] = {t: [] for t in PRIMARY}
    for m in matrix:
        sp = m.get("Species") or m.get("showid") or "?"
        for t in PRIMARY:
            if not (m.get(t) or "").strip():
                missing[t].append(f"{m.get('showid')}:{sp}")

    lines = [
        "# Raw download classify summary",
        "",
        f"- files: **{len(rows)}**",
        f"- species (showid): **{n_sp}**",
        f"- empty_file notes: {empty}",
        f"- over_300mb / skipped_size notes: {over}",
        "",
        "## file_type counts",
        "",
        "| file_type | count |",
        "|---|---:|",
    ]
    for k, v in ft_c.most_common():
        lines.append(f"| {k} | {v} |")

    lines += [
        "",
        "## format counts",
        "",
        "| format | count |",
        "|---|---:|",
    ]
    for k, v in fmt_c.most_common():
        lines.append(f"| {k} | {v} |")

    lines += [
        "",
        "## compression counts",
        "",
        "| compression | count |",
        "|---|---:|",
    ]
    for k, v in comp_c.most_common():
        lines.append(f"| {k} | {v} |")

    lines += ["", "## species missing primary types", ""]
    for t in PRIMARY:
        lst = missing[t]
        if not lst:
            lines.append(f"- **{t}**: (none missing among catalogued species)")
        else:
            preview = ", ".join(lst[:20])
            more = f" …(+{len(lst)-20})" if len(lst) > 20 else ""
            lines.append(f"- **{t}** ({len(lst)}): {preview}{more}")

    lines.append("")
    return "\n".join(lines)


def write_stats_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    ft_c = Counter(r.get("file_type") or "unknown" for r in rows)
    fmt_c = Counter(r.get("format") or "unknown" for r in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["metric", "key", "count"])
        for k, v in ft_c.most_common():
            w.writerow(["file_type", k, v])
        for k, v in fmt_c.most_common():
            w.writerow(["format", k, v])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "-i",
        "--catalog",
        type=Path,
        default=Path("resources/raw_file_catalog.tsv"),
    )
    ap.add_argument(
        "--matrix",
        type=Path,
        default=Path("resources/raw_type_matrix.tsv"),
    )
    ap.add_argument(
        "--summary",
        type=Path,
        default=Path("resources/raw_classify_summary.md"),
    )
    ap.add_argument(
        "--stats-tsv",
        type=Path,
        default=Path("resources/raw_classify_stats.tsv"),
    )
    args = ap.parse_args()

    if not args.catalog.is_file():
        raise SystemExit(f"catalog not found: {args.catalog}")

    rows = load_catalog(args.catalog)
    matrix = build_matrix(rows)
    write_matrix(args.matrix, matrix)
    text = summarize(rows, matrix)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(text, encoding="utf-8")
    write_stats_tsv(args.stats_tsv, rows)
    print(
        f"Wrote {args.matrix}, {args.summary}, {args.stats_tsv} "
        f"({len(rows)} files, {len(matrix)} species rows)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
