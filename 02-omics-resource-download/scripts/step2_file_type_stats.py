#!/usr/bin/env python3
"""Summarize file_type frequencies from assembly_download_links.tsv."""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

TARGET_TYPES = ("cds", "gff", "pep", "gbff", "genome")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "-i",
        "--input",
        type=Path,
        default=Path("resources/assembly_download_links.tsv"),
    )
    p.add_argument(
        "--predownload",
        type=Path,
        default=Path("resources/predownload_list.tsv"),
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("resources/file_type_stats.tsv"),
    )
    p.add_argument(
        "--summary",
        type=Path,
        default=Path("resources/file_type_stats_summary.txt"),
    )
    args = p.parse_args()

    portal_total = 0
    if args.predownload.exists():
        with args.predownload.open(newline="", encoding="utf-8") as f:
            portal_total = sum(1 for _ in csv.DictReader(f, delimiter="\t"))

    rows: list[dict[str, str]] = []
    with args.input.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    counts = Counter((r.get("file_type") or "none") for r in rows)
    total_links = len(rows)
    distinct = sorted(counts.keys())

    by_show: dict[str, set[str]] = {}
    none_shows: set[str] = set()
    for r in rows:
        sid = (r.get("show_id") or "").strip()
        ft = r.get("file_type") or "none"
        by_show.setdefault(sid, set()).add(ft)
        if ft == "none":
            none_shows.add(sid)
    # portals with only none (or that have a none row and no real files)
    no_link_shows = {
        sid for sid, fts in by_show.items() if fts == {"none"} or (not fts - {"none"})
    }

    coverage = {
        t: sum(1 for sid, fts in by_show.items() if t in fts) for t in TARGET_TYPES
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["file_type", "count", "percent"],
            delimiter="\t",
            lineterminator="\n",
        )
        w.writeheader()
        for ft, c in counts.most_common():
            pct = (100.0 * c / total_links) if total_links else 0.0
            w.writerow(
                {"file_type": ft, "count": c, "percent": f"{pct:.4f}"}
            )

    lines = [
        f"total_portal_rows_predownload={portal_total}",
        f"total_download_link_rows={total_links}",
        f"distinct_show_ids_in_links={len(by_show)}",
        f"distinct_file_type_count={len(distinct)}",
        f"distinct_file_types={','.join(sorted(distinct))}",
        "",
        "file_type_frequency (count desc):",
    ]
    for ft, c in counts.most_common():
        pct = (100.0 * c / total_links) if total_links else 0.0
        lines.append(f"  {ft}\t{c}\t{pct:.4f}%")
    lines.append("")
    lines.append("show_id coverage (at least one link of type):")
    for t in TARGET_TYPES:
        lines.append(f"  show_ids_with_{t}={coverage[t]}")
    lines.append(f"portals_with_no_links_file_type_none={len(no_link_shows)}")
    lines.append(f"rows_with_file_type_none={counts.get('none', 0)}")

    text = "\n".join(lines) + "\n"
    args.summary.write_text(text, encoding="utf-8")
    print(text, end="")
    print(f"wrote {args.output}", flush=True)
    print(f"wrote {args.summary}", flush=True)


if __name__ == "__main__":
    main()
