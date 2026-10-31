#!/usr/bin/env python3
"""Step 3b: download allowed assembly files into per-show_id folders.

Default is --dry-run (plan only). Pass --yes to perform downloads.
Skips remote files larger than 300 MiB (Content-Length via HEAD).
If Content-Length is unknown, downloads with a max-bytes abort and
records size_unknown_* status.

Retries: after a failed attempt, retry up to --retries times (default 2;
3 attempts total) with a brief backoff sleep between tries.
Concurrency: ThreadPoolExecutor via --workers / -j (default 1; clamp 1–8;
useful range 2–4).
"""
from __future__ import annotations

import argparse
import csv
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from step3_common import (  # noqa: E402
    ALLOWED_FILE_TYPES,
    MAX_DOWNLOAD_BYTES,
    downloads_root,
    folder_name,
)

USER_AGENT = "plant-genome-resources-step3/1.0 (+local research; dry-run default)"

# Transient / retryable status prefixes (first attempt failed → retry)
_RETRYABLE_PREFIXES = ("http_", "error:")
_RETRYABLE_EXACT = frozenset(
    {
        "http_408",
        "http_429",
        "http_500",
        "http_502",
        "http_503",
        "http_504",
    }
)

_print_lock = threading.Lock()


def filename_from_url(url: str) -> str:
    path = unquote(urlparse(url).path)
    name = Path(path).name
    return name or "download.bin"


def head_content_length(url: str, timeout: float = 30.0) -> int | None:
    """Return Content-Length if present, else None. Follows redirects."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            cl = resp.headers.get("Content-Length")
            if cl is None:
                return None
            return int(cl)
    except Exception:
        # Some servers reject HEAD; treat as unknown
        return None


def download_with_limit(
    url: str,
    dest: Path,
    max_bytes: int,
    timeout: float = 120.0,
) -> tuple[str, int]:
    """Stream download; abort if bytes exceed max_bytes.

    Returns (status, bytes_written).
    status: ok | too_large_abort | http_error | error
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")
    written = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, tmp.open("wb") as out:
            cl = resp.headers.get("Content-Length")
            if cl is not None and int(cl) > max_bytes:
                tmp.unlink(missing_ok=True)
                return ("too_large_skip", 0)
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    out.close()
                    tmp.unlink(missing_ok=True)
                    return ("too_large_abort", written)
                out.write(chunk)
        tmp.replace(dest)
        return ("ok", written)
    except urllib.error.HTTPError as e:
        tmp.unlink(missing_ok=True)
        return (f"http_{e.code}", written)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        return (f"error:{type(e).__name__}", written)


def is_retryable(status: str) -> bool:
    """True if status indicates a transient failure worth retrying."""
    if status in _RETRYABLE_EXACT:
        return True
    if status.startswith("error:"):
        return True
    # Retry most HTTP failures except 4xx client errors that are permanent
    if status.startswith("http_"):
        try:
            code = int(status.split("_", 1)[1])
        except ValueError:
            return True
        if code in {408, 425, 429} or code >= 500:
            return True
        # 403/404 etc. — not worth retrying by default, but allow 403 once
        # some mirrors flap; keep narrow: only 5xx / rate-limit / timeout
        return False
    return False


def load_folder_map(predownload: Path) -> dict[str, str]:
    """show_id -> folder name."""
    mapping: dict[str, str] = {}
    with predownload.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            sid = str(row["show_id"]).strip()
            mapping[sid] = folder_name(
                sid, row["Order"], row["Family"], row["Species"]
            )
    return mapping


def iter_download_jobs(
    links: Path,
    folder_map: dict[str, str],
    allowed: Iterable[str],
) -> list[dict[str, str]]:
    allowed_set = set(allowed)
    jobs: list[dict[str, str]] = []
    with links.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            ft = (row.get("file_type") or "").strip().lower()
            if ft not in allowed_set:
                continue
            url = (row.get("download_url") or "").strip()
            if not url or url.lower() in {"na", "n/a", "none", "null"}:
                continue
            sid = str(row.get("show_id", "")).strip()
            folder = folder_map.get(sid)
            if not folder:
                continue
            jobs.append(
                {
                    "show_id": sid,
                    "Species": row.get("Species", ""),
                    "file_type": ft,
                    "download_url": url,
                    "folder": folder,
                    "filename": filename_from_url(url),
                }
            )
    return jobs


def process_job(
    j: dict[str, str],
    *,
    out_root: Path,
    do_download: bool,
    max_bytes: int,
    retries: int,
    backoff_base: float,
) -> dict[str, str]:
    """Process one download job; returns a log row dict."""
    dest = out_root / j["folder"] / j["filename"]
    (out_root / j["folder"]).mkdir(parents=True, exist_ok=True)

    if dest.exists() and dest.stat().st_size > 0:
        status = "already_exists"
        cl_s = str(dest.stat().st_size)
        written = dest.stat().st_size
        if not do_download:
            status = "dry_run_already_exists"
        attempts = 0
    elif not do_download:
        # dry-run: optional HEAD for size plan (no download retries)
        cl = head_content_length(j["download_url"])
        if cl is not None and cl > max_bytes:
            status = "dry_run_skip_too_large"
        elif cl is None:
            status = "dry_run_size_unknown"
        else:
            status = "dry_run_would_download"
        cl_s = "" if cl is None else str(cl)
        written = 0
        attempts = 0
    else:
        cl = head_content_length(j["download_url"])
        if cl is not None and cl > max_bytes:
            status = "too_large_skip"
            cl_s = str(cl)
            written = 0
            attempts = 0
        else:
            cl_s = "" if cl is None else str(cl)
            max_attempts = 1 + max(0, retries)
            status = "error:not_attempted"
            written = 0
            attempts = 0
            for attempt in range(1, max_attempts + 1):
                attempts = attempt
                status, written = download_with_limit(
                    j["download_url"], dest, max_bytes
                )
                if cl is None and status == "ok":
                    status = "ok_size_was_unknown"
                elif cl is None and status == "too_large_abort":
                    status = "size_unknown_abort"

                # Success or non-retryable terminal statuses
                if status in {
                    "ok",
                    "ok_size_was_unknown",
                    "too_large_skip",
                    "too_large_abort",
                    "size_unknown_abort",
                }:
                    break
                if attempt < max_attempts and is_retryable(status):
                    sleep_s = backoff_base * attempt
                    with _print_lock:
                        print(
                            f"[retry {attempt}/{retries}] show_id={j['show_id']} "
                            f"type={j['file_type']} file={j['filename']} "
                            f"status={status}; sleep {sleep_s:.1f}s",
                            flush=True,
                        )
                    time.sleep(sleep_s)
                    continue
                break

            if attempts > 1 and status.startswith(("ok",)):
                status = f"{status}_after_retry"
            elif attempts > 1 and is_retryable(status):
                status = f"{status}_retries_exhausted"

    row = {
        **{
            k: j[k]
            for k in (
                "show_id",
                "Species",
                "file_type",
                "filename",
                "folder",
                "download_url",
            )
        },
        "content_length": cl_s,
        "status": status,
        "bytes_written": str(written),
        "dest": str(dest),
        "attempts": str(attempts),
    }
    with _print_lock:
        print(
            f"[{status}] show_id={j['show_id']} type={j['file_type']} "
            f"file={j['filename']} cl={cl_s or 'NA'} attempts={attempts}",
            flush=True,
        )
    return row


def clamp_workers(n: int) -> int:
    """Allow 1–8 workers safely."""
    return max(1, min(8, int(n)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "-i",
        "--predownload",
        type=Path,
        default=Path("resources/predownload_list.tsv"),
    )
    ap.add_argument(
        "-l",
        "--links",
        type=Path,
        default=Path("resources/assembly_download_links.tsv"),
    )
    ap.add_argument(
        "-d",
        "--downloads-dir",
        type=Path,
        default=None,
        help="Root for per-show_id folders (default: data/downloads)",
    )
    ap.add_argument(
        "--max-mb",
        type=float,
        default=300.0,
        help="Skip if Content-Length > this many MiB (default 300)",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only process first N eligible jobs (0 = all)",
    )
    ap.add_argument(
        "--show-id",
        type=str,
        default="",
        help="Only process one show_id",
    )
    ap.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Retries after first failure (default 2 → up to 3 attempts total)",
    )
    ap.add_argument(
        "--backoff",
        type=float,
        default=1.5,
        help="Base seconds for linear backoff between retries (default 1.5)",
    )
    ap.add_argument(
        "-j",
        "--workers",
        type=int,
        default=1,
        help="Concurrent download workers (default 1; useful 2–4; clamped 1–8)",
    )
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Plan only (default)",
    )
    mode.add_argument(
        "--yes",
        action="store_true",
        help="Actually download (not dry-run)",
    )
    ap.add_argument(
        "--log",
        type=Path,
        default=Path("resources/step3_download_log.tsv"),
        help="TSV log of planned/performed actions",
    )
    args = ap.parse_args()
    do_download = bool(args.yes)
    max_bytes = int(args.max_mb * 1024 * 1024)
    retries = max(0, int(args.retries))
    workers = clamp_workers(args.workers)
    backoff_base = max(0.0, float(args.backoff))

    project_root = Path.cwd()
    out_root = args.downloads_dir or downloads_root(project_root)
    out_root.mkdir(parents=True, exist_ok=True)

    folder_map = load_folder_map(args.predownload)
    jobs = iter_download_jobs(args.links, folder_map, ALLOWED_FILE_TYPES)
    if args.show_id:
        jobs = [j for j in jobs if j["show_id"] == args.show_id.strip()]
    if args.limit and args.limit > 0:
        jobs = jobs[: args.limit]

    log_fields = [
        "show_id",
        "Species",
        "file_type",
        "filename",
        "folder",
        "download_url",
        "content_length",
        "status",
        "bytes_written",
        "dest",
        "attempts",
    ]

    print(
        f"mode: {'DOWNLOAD' if do_download else 'DRY-RUN'}\n"
        f"downloads_dir: {out_root}\n"
        f"eligible_jobs: {len(jobs)}\n"
        f"max_bytes: {max_bytes} ({args.max_mb} MiB)\n"
        f"retries: {retries} (max_attempts={1 + retries})\n"
        f"workers: {workers}"
    )

    log_rows: list[dict[str, str]] = []
    if workers <= 1 or len(jobs) <= 1:
        for j in jobs:
            log_rows.append(
                process_job(
                    j,
                    out_root=out_root,
                    do_download=do_download,
                    max_bytes=max_bytes,
                    retries=retries,
                    backoff_base=backoff_base,
                )
            )
    else:
        # Preserve input order in the log via index map
        results: dict[int, dict[str, str]] = {}
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {
                ex.submit(
                    process_job,
                    j,
                    out_root=out_root,
                    do_download=do_download,
                    max_bytes=max_bytes,
                    retries=retries,
                    backoff_base=backoff_base,
                ): i
                for i, j in enumerate(jobs)
            }
            for fut in as_completed(futures):
                idx = futures[fut]
                results[idx] = fut.result()
        log_rows = [results[i] for i in range(len(jobs))]

    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=log_fields, delimiter="\t")
        w.writeheader()
        w.writerows(log_rows)
    print(f"wrote log: {args.log} ({len(log_rows)} rows)")


if __name__ == "__main__":
    main()
