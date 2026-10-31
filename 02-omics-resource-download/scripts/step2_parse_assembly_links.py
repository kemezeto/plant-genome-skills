#!/usr/bin/env python3
"""Step 2: parse Genome assembly portal pages into all file download URLs.

Concurrent (ThreadPoolExecutor), progress logging, resume-by-show_id checkpoint,
robust HTTP error handling. Does not download data files — only enumerates links.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin

from classify_file_type import classify
from domain_handlers import links_to_rows, normalize_portal_url, recover_links

UA = {"User-Agent": "Mozilla/5.0 (compatible; plant-genome-download/1.0)"}
FILE_RE = re.compile(
    r"\.(?:gz|fasta|fa|fna|faa|gbff|gbf|gff3?|gtf|txt)(?:\?|$)",
    re.I,
)
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
_thread_local = threading.local()


def fetch(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")




def extract_page_file_links(page_url: str, html: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for m in re.finditer(r'href=["\']([^"\']+)["\'][^>]*>([^<]*)<', html, re.I):
        href, text = m.group(1).strip(), m.group(2).strip()
        if href.startswith("#"):
            continue
        full = urljoin(page_url, href)
        if FILE_RE.search(full):
            links.append((full, text))
    for href in re.findall(r'href=["\']([^"\']+)["\']', html, re.I):
        full = urljoin(page_url, href)
        if FILE_RE.search(full):
            links.append((full, ""))
    return _dedupe(links)


def list_dir_files(dir_url: str) -> list[str]:
    try:
        html = fetch(dir_url)
    except Exception:
        return []
    files: list[str] = []
    for href in re.findall(r'href=["\']([^"\']+)["\']', html, re.I):
        if href in ("./", "../") or href.endswith("/"):
            continue
        if FILE_RE.search(href):
            files.append(urljoin(dir_url, href))
    return sorted(set(files))


def _dedupe(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for u, t in items:
        if u in seen:
            continue
        seen.add(u)
        out.append((u, t))
    return out


def parse_assembly_row(row: dict[str, str], delay: float = 0.0) -> list[dict[str, str]]:
    if delay > 0:
        time.sleep(delay)
    page = normalize_portal_url((row.get("Genome assembly") or "").strip())
    base = {
        "show_id": row.get("show_id", ""),
        "Species": row.get("Species", ""),
        "Ploidy": row.get("Ploidy", ""),
        "portal_url": (row.get("Genome assembly") or "").strip() or page,
    }
    if not page:
        return [
            {
                **base,
                "file_type": "none",
                "label": "",
                "download_url": "",
                "notes": "no portal url",
            }
        ]

    # Direct file URLs (not HTML portals): classify without downloading content.
    page_name = page.rstrip("/").split("/")[-1].split("?")[0]
    if FILE_RE.search(page_name) or re.search(
        r"\.(?:fasta|fa|fna|faa|gbff|gbf|gff3?|gtf|gz)(?:\.|$)", page_name, re.I
    ):
        ft = classify(page, page_name)
        return [
            {
                **base,
                "file_type": ft,
                "label": page_name,
                "download_url": page,
                "notes": "direct_file_url",
            }
        ]

    ctx = {
        "species": row.get("Species") or "",
        "accession_name": row.get("Accession name") or "",
        "annotation": row.get("Annotation") or "",
    }

    # Domain-specific recovery first for known hard portals
    links, handler, notes = recover_links(page, ctx)
    if links:
        return links_to_rows(base, links, notes)

    # If handler already exhausted a known-dead portal, keep its note
    if handler in {"phytozome", "ibi"} or (
        notes
        and any(
            x in notes
            for x in (
                "login_required",
                "ibi_na_or_down",
                "ncbi_no_accession",
                "ngdc_bioproject_unmatched",
                "ngdc_bioproject_no_assemblies",
                "figshare_api:http 403",
            )
        )
    ):
        return [
            {
                **base,
                "file_type": "none",
                "label": "",
                "download_url": "",
                "notes": notes or "no file links found",
            }
        ]

    # Generic HTML crawl (original behavior) as last resort
    try:
        html = fetch(page)
    except urllib.error.HTTPError as e:
        return [
            {
                **base,
                "file_type": "none",
                "label": "",
                "download_url": "",
                "notes": notes or f"http {e.code}",
            }
        ]
    except Exception as e:
        return [
            {
                **base,
                "file_type": "none",
                "label": "",
                "download_url": "",
                "notes": notes or f"fetch failed: {e}",
            }
        ]

    file_links = extract_page_file_links(page, html)
    dirs = {
        u.rsplit("/", 1)[0] + "/"
        for u, _ in file_links
        if "download.cncb.ac.cn" in u
    }
    extra: list[tuple[str, str]] = []
    for d in dirs:
        for fu in list_dir_files(d):
            extra.append((fu, "dir_listing"))

    all_links = _dedupe(file_links + extra)
    if not all_links:
        return [
            {
                **base,
                "file_type": "none",
                "label": "",
                "download_url": "",
                "notes": notes or "no file links found",
            }
        ]

    out: list[dict[str, str]] = []
    for u, t in all_links:
        ft = classify(u, t)
        n = "gbff_available" if ft == "gbff" else ""
        out.append(
            {
                **base,
                "file_type": ft,
                "label": t,
                "download_url": u,
                "notes": n,
            }
        )
    return out



def load_done_show_ids(path: Path) -> set[str]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    done: set[str] = set()
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            sid = (row.get("show_id") or "").strip()
            if sid:
                done.add(sid)
    return done


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "-i",
        "--input",
        type=Path,
        default=Path("resources/predownload_list.tsv"),
        help="predownload list TSV from step1",
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("resources/assembly_download_links.tsv"),
        help="output links TSV",
    )
    p.add_argument(
        "-j",
        "--workers",
        type=int,
        default=12,
        help="ThreadPoolExecutor workers (default 12; keep <=16)",
    )
    p.add_argument(
        "--progress-every",
        type=int,
        default=50,
        help="log progress every N completed portal rows (default 50)",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=0.05,
        help="optional per-worker delay before each portal fetch (seconds)",
    )
    p.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="skip show_ids already present in output (default on)",
    )
    p.add_argument(
        "--no-resume",
        action="store_true",
        help="ignore existing output and rewrite from scratch",
    )
    args = p.parse_args()
    resume = args.resume and not args.no_resume

    with args.input.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    done: set[str] = set()
    if resume and args.output.exists():
        done = load_done_show_ids(args.output)
        print(
            f"resume: {len(done)} show_ids already in {args.output}",
            file=sys.stderr,
        )
    else:
        # fresh write with header
        with args.output.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
            w.writeheader()

    todo = [r for r in rows if (r.get("show_id") or "").strip() not in done]
    total = len(rows)
    remaining = len(todo)
    print(
        f"portals total={total} todo={remaining} workers={args.workers}",
        file=sys.stderr,
    )
    if remaining == 0:
        print("nothing to do", file=sys.stderr)
        return

    # Ensure header exists when resuming an empty/partial file without header
    if resume and args.output.exists():
        with args.output.open(encoding="utf-8") as f:
            first = f.readline()
        if not first.startswith("show_id"):
            with args.output.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(
                    f, fieldnames=FIELDS, delimiter="\t", lineterminator="\n"
                )
                w.writeheader()

    write_lock = threading.Lock()
    completed = 0
    link_rows_written = 0
    t0 = time.time()

    def _handle(row: dict[str, str]) -> tuple[str, list[dict[str, str]]]:
        sid = (row.get("show_id") or "").strip()
        parsed = parse_assembly_row(row, delay=args.delay)
        return sid, parsed

    workers = max(1, min(args.workers, 16))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_handle, r): r for r in todo}
        with args.output.open("a", newline="", encoding="utf-8") as out_f:
            w = csv.DictWriter(
                out_f, fieldnames=FIELDS, delimiter="\t", lineterminator="\n"
            )
            for fut in as_completed(futures):
                try:
                    sid, parsed = fut.result()
                except Exception as e:
                    row = futures[fut]
                    sid = (row.get("show_id") or "").strip()
                    parsed = [
                        {
                            "show_id": sid,
                            "Species": row.get("Species", ""),
                            "Ploidy": row.get("Ploidy", ""),
                            "portal_url": (row.get("Genome assembly") or "").strip(),
                            "file_type": "none",
                            "label": "",
                            "download_url": "",
                            "notes": f"worker exception: {e}",
                        }
                    ]
                with write_lock:
                    w.writerows(parsed)
                    out_f.flush()
                    completed += 1
                    link_rows_written += len(parsed)
                    if (
                        completed % args.progress_every == 0
                        or completed == remaining
                    ):
                        elapsed = time.time() - t0
                        rate = completed / elapsed if elapsed > 0 else 0
                        eta = (remaining - completed) / rate if rate > 0 else 0
                        print(
                            f"progress {completed}/{remaining} "
                            f"(done_total={len(done)+completed}/{total}) "
                            f"links+={link_rows_written} "
                            f"elapsed={elapsed:.1f}s rate={rate:.2f}/s eta={eta:.0f}s "
                            f"last_show_id={sid} nlinks={len(parsed)}",
                            file=sys.stderr,
                            flush=True,
                        )

    elapsed = time.time() - t0
    print(
        f"wrote {args.output} portals_this_run={completed} "
        f"link_rows_this_run={link_rows_written} elapsed={elapsed:.1f}s",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
