#!/usr/bin/env python3
"""Targeted re-parse of file_type=none show_ids using domain handlers.

Reads existing assembly_download_links.tsv, recovers download links for none
portals, merges recovered rows back, and writes a recovery summary.
"""
from __future__ import annotations

import argparse
import csv
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from classify_file_type import classify
from domain_handlers import links_to_rows, recover_links

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


def load_raw_context(path: Path) -> dict[str, dict[str, str]]:
    ctx: dict[str, dict[str, str]] = {}
    if not path.exists():
        return ctx
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            sid = (row.get("show_id") or "").strip()
            if not sid:
                continue
            ctx[sid] = {
                "accession_name": (row.get("Accession name") or "").strip(),
                "annotation": (row.get("Annotation") or "").strip(),
                "species": (row.get("Species") or "").strip(),
                "genome_assembly": (row.get("Genome assembly") or "").strip(),
            }
    return ctx


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "-i",
        "--input",
        type=Path,
        default=Path("resources/assembly_download_links.tsv"),
        help="existing links TSV (will be merged in place unless --output set)",
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="output TSV (default: overwrite --input)",
    )
    p.add_argument(
        "--raw-table",
        type=Path,
        default=Path("resources/raw_table.csv"),
        help="original table for Annotation / Accession name",
    )
    p.add_argument(
        "--recovery-out",
        type=Path,
        default=Path("resources/none_recovery_links.tsv"),
        help="TSV of only recovered (non-none) rows this run",
    )
    p.add_argument(
        "--still-none-out",
        type=Path,
        default=Path("resources/none_still_none.tsv"),
        help="TSV of show_ids still none after recovery",
    )
    p.add_argument(
        "--summary",
        type=Path,
        default=Path("resources/none_recovery_summary.txt"),
        help="human-readable summary for skill notes",
    )
    p.add_argument("-j", "--workers", type=int, default=12)
    p.add_argument(
        "--progress-every", type=int, default=50
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="optional cap on none show_ids to process (0=all)",
    )
    p.add_argument(
        "--domains",
        type=str,
        default="",
        help="optional comma filter on portal host substrings",
    )
    args = p.parse_args()
    out_path = args.output or args.input
    workers = max(1, min(args.workers, 16))

    raw_ctx = load_raw_context(args.raw_table)

    # Load all rows; identify none show_ids (one portal row each typically)
    all_rows: list[dict[str, str]] = []
    none_by_sid: dict[str, dict[str, str]] = {}
    with args.input.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            all_rows.append(row)
            if row.get("file_type") == "none":
                sid = (row.get("show_id") or "").strip()
                if sid and sid not in none_by_sid:
                    none_by_sid[sid] = row

    before_none = len(none_by_sid)
    print(f"none show_ids before: {before_none}", file=sys.stderr)

    domain_filter = [d.strip().lower() for d in args.domains.split(",") if d.strip()]
    todo_sids = list(none_by_sid.keys())
    if domain_filter:
        filtered = []
        for sid in todo_sids:
            portal = (none_by_sid[sid].get("portal_url") or "").lower()
            if any(d in portal for d in domain_filter):
                filtered.append(sid)
        todo_sids = filtered
        print(
            f"domain filter {domain_filter}: todo={len(todo_sids)}",
            file=sys.stderr,
        )
    if args.limit and args.limit > 0:
        todo_sids = todo_sids[: args.limit]

    recovered_rows: list[dict[str, str]] = []
    still_none_rows: list[dict[str, str]] = []
    recovered_sids: set[str] = set()
    by_handler = Counter()
    by_domain_recovered = Counter()
    recovered_types = Counter()
    fail_notes = Counter()
    lock = threading.Lock()
    completed = 0
    t0 = time.time()

    def _domain_key(portal: str) -> str:
        from urllib.parse import urlparse

        try:
            host = urlparse(portal).netloc.lower() or "(label_or_empty)"
        except Exception:
            host = "(bad)"
        return host

    def _work(sid: str) -> tuple[str, list[dict[str, str]], bool]:
        row = none_by_sid[sid]
        portal = (row.get("portal_url") or "").strip()
        ctx = dict(raw_ctx.get(sid) or {})
        ctx.setdefault("species", row.get("Species") or "")
        base = {
            "show_id": sid,
            "Species": row.get("Species") or ctx.get("species") or "",
            "Ploidy": row.get("Ploidy") or "",
            "portal_url": portal,
        }
        links, handler, notes = recover_links(portal, ctx)
        by_handler_local = handler
        if not links:
            out = [
                {
                    **base,
                    "file_type": "none",
                    "label": "",
                    "download_url": "",
                    "notes": notes or row.get("notes") or "recovery_failed",
                }
            ]
            return sid, out, False
        out = links_to_rows(base, links, notes)
        # stamp handler in notes already; track
        return sid, out, True

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_work, sid): sid for sid in todo_sids}
        for fut in as_completed(futs):
            sid = futs[fut]
            try:
                sid, rows, ok = fut.result()
            except Exception as e:
                row = none_by_sid[sid]
                rows = [
                    {
                        "show_id": sid,
                        "Species": row.get("Species", ""),
                        "Ploidy": row.get("Ploidy", ""),
                        "portal_url": row.get("portal_url", ""),
                        "file_type": "none",
                        "label": "",
                        "download_url": "",
                        "notes": f"recovery_exception:{e}",
                    }
                ]
                ok = False
            with lock:
                completed += 1
                if ok:
                    recovered_sids.add(sid)
                    recovered_rows.extend(rows)
                    portal = none_by_sid[sid].get("portal_url") or ""
                    by_domain_recovered[_domain_key(portal)] += 1
                    # handler from notes prefix-ish
                    note0 = rows[0].get("notes") or ""
                    by_handler[note0.split(":")[0].split(";")[0]] += 1
                    for r in rows:
                        recovered_types[r["file_type"]] += 1
                else:
                    still_none_rows.extend(rows)
                    fail_notes[rows[0].get("notes") or ""] += 1
                if completed % args.progress_every == 0 or completed == len(todo_sids):
                    elapsed = time.time() - t0
                    rate = completed / elapsed if elapsed else 0
                    print(
                        f"progress {completed}/{len(todo_sids)} "
                        f"recovered_sids={len(recovered_sids)} "
                        f"elapsed={elapsed:.1f}s rate={rate:.2f}/s "
                        f"last={sid} ok={ok}",
                        file=sys.stderr,
                        flush=True,
                    )

    # Merge: drop old rows for recovered sids + still-none sids we rewrote notes for;
    # keep other rows; append new recovered + updated still-none for processed sids.
    processed = set(todo_sids)
    kept = [
        r
        for r in all_rows
        if (r.get("show_id") or "").strip() not in processed
    ]
    recovered_by_sid: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in recovered_rows:
        recovered_by_sid[r["show_id"]].append(r)
    still_map = {r["show_id"]: r for r in still_none_rows}
    new_rows = list(kept)
    for sid in todo_sids:
        if sid in recovered_sids:
            new_rows.extend(recovered_by_sid.get(sid) or [])
        else:
            new_rows.append(still_map.get(sid) or none_by_sid[sid])

    # Write outputs
    args.recovery_out.parent.mkdir(parents=True, exist_ok=True)
    with args.recovery_out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(recovered_rows)

    with args.still_none_out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        # dedup still none by show_id from merged view
        seen = set()
        for r in new_rows:
            if r.get("file_type") != "none":
                continue
            sid = r.get("show_id") or ""
            if sid in seen:
                continue
            seen.add(sid)
            w.writerow(r)

    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(new_rows)

    after_none_sids = {
        (r.get("show_id") or "").strip()
        for r in new_rows
        if r.get("file_type") == "none"
    }
    after_none = len(after_none_sids)

    # Summary
    lines = []
    lines.append("none recovery summary")
    lines.append(f"input: {args.input}")
    lines.append(f"output: {out_path}")
    lines.append(f"none show_ids before (dedup): {before_none}")
    lines.append(f"none show_ids processed: {len(todo_sids)}")
    lines.append(f"none show_ids after (dedup): {after_none}")
    lines.append(f"recovered show_ids: {len(recovered_sids)}")
    lines.append(f"recovered link rows: {len(recovered_rows)}")
    lines.append("")
    lines.append("recovered show_ids by portal domain:")
    for dom, c in by_domain_recovered.most_common(30):
        lines.append(f"  {c}\t{dom}")
    lines.append("")
    lines.append("recovered rows by file_type:")
    for ft, c in recovered_types.most_common():
        lines.append(f"  {c}\t{ft}")
    lines.append("")
    lines.append("recovery notes (success handler tags):")
    for n, c in by_handler.most_common(40):
        lines.append(f"  {c}\t{n}")
    lines.append("")
    lines.append("still-none notes (top):")
    for n, c in fail_notes.most_common(40):
        lines.append(f"  {c}\t{n}")
    lines.append("")
    lines.append("Honest limits / known gaps:")
    lines.append(
        "- Phytozome / JGI portals: downloads require login → left as none "
        "(notes=phytozome_login_required)."
    )
    lines.append(
        "- ibi.zju.edu.cn N3database: portal often literally .../NA and HTTP 500; "
        "Annotation column usually identical → left as none (ibi_na_or_down)."
    )
    lines.append(
        "- Figshare: some article IDs return API 403 (private/embargoed/share-only); "
        "public articles recovered via api.figshare.com."
    )
    lines.append(
        "- NCBI BioProject pages without a GCA/GCF accession: no FTP target; "
        "left as none (ncbi_no_accession) unless datasets/genome URL present."
    )
    lines.append(
        "- NGDC BioProject with many assemblies: matched via Accession name "
        "token in download folder; unmatched stay none "
        "(ngdc_bioproject_unmatched_n=...)."
    )
    lines.append(
        "- Do not download large genomics files in step2; only enumerate URLs."
    )
    lines.append("")
    lines.append("Paths:")
    lines.append(f"  merged links: {out_path}")
    lines.append(f"  recovered only: {args.recovery_out}")
    lines.append(f"  still none: {args.still_none_out}")
    lines.append(f"  this summary: {args.summary}")

    summary_text = "\n".join(lines) + "\n"
    args.summary.write_text(summary_text, encoding="utf-8")
    print(summary_text)
    print(
        f"wrote merged={out_path} recovered_sids={len(recovered_sids)} "
        f"none {before_none}->{after_none}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
