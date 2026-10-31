#!/usr/bin/env python3
"""Shared helpers for step 3: folder naming and file-type detection."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

# Allowed download file types (step 3)
ALLOWED_FILE_TYPES = ("gff", "genome", "cds", "pep", "rna", "gbff", "gtf")

# Max download size: 300 MiB
MAX_DOWNLOAD_BYTES = 300 * 1024 * 1024

# Characters unsafe on common filesystems
_UNSAFE_RE = re.compile(r'[\/\\:\*\?"<>\|]+')
_WS_RE = re.compile(r"[\s\u200b\u200c\u200d\ufeff]+")
# Folder pattern: showid_Order_Family(Species)
_FOLDER_RE = re.compile(
    r"^(?P<showid>.+?)_(?P<order>.+?)_(?P<family>.+?)\((?P<species>.+)\)$"
)

# Filename heuristics for inventory (case-insensitive)
_TYPE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("gff", re.compile(r"\.(gff3?|gff\.gz)$", re.I)),
    ("gtf", re.compile(r"\.(gtf|gtf\.gz)$", re.I)),
    ("gbff", re.compile(r"\.(gbff|gbk|genbank)(\.gz)?$", re.I)),
    ("pep", re.compile(r"(protein|pep|proteome|translated).*\.(fa|fasta|faa|fna)(\.gz)?$|\.(faa)(\.gz)?$", re.I)),
    ("cds", re.compile(r"(cds|coding).*\.(fa|fasta|fna)(\.gz)?$", re.I)),
    ("rna", re.compile(r"(rna|transcript|mrna|cdna).*\.(fa|fasta|fna)(\.gz)?$", re.I)),
    ("genome", re.compile(r"(genomic|genome|assembly|scaffold|contig).*\.(fa|fasta|fna|fa\.gz|fasta\.gz|fna\.gz)$|\.(fna|fasta|fa)(\.gz)?$", re.I)),
]


def sanitize_fs_component(text: str | None) -> str:
    """Make Order/Family/Species safe for a directory name; keep readable.

    Replaces filesystem-illegal chars and odd/zero-width whitespace with `_`.
    Normal spaces are kept (collapsed to single spaces).
    """
    if text is None:
        return "NA"
    s = unicodedata.normalize("NFKC", str(text))
    # Drop control / format chars (incl. zero-width ZWSP etc.)
    s = "".join(ch for ch in s if unicodedata.category(ch)[0] not in {"C"})
    # Weird whitespace (non-ordinary space) -> underscore, then collapse spaces
    s = re.sub(r"[^\S ]+", "_", s)  # any whitespace that is not ASCII space
    s = re.sub(r" +", " ", s).strip()
    s = _UNSAFE_RE.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("._ ")
    return s or "NA"


def folder_name(show_id: str, order: str, family: str, species: str) -> str:
    """Literal format: {show_id}_{Order}_{Family}({Species}) with sanitized parts."""
    sid = str(show_id).strip()
    o = sanitize_fs_component(order)
    fam = sanitize_fs_component(family)
    sp = sanitize_fs_component(species)
    return f"{sid}_{o}_{fam}({sp})"


def parse_folder_name(name: str) -> dict[str, str] | None:
    """Parse showid_Order_Family(Species); returns None if not matching."""
    m = _FOLDER_RE.match(name)
    if not m:
        return None
    return {
        "showid": m.group("showid"),
        "Order": m.group("order"),
        "Family": m.group("family"),
        "Species": m.group("species"),
    }


def classify_local_filename(filename: str) -> str | None:
    """Best-effort map a local filename to one of ALLOWED_FILE_TYPES."""
    fn = filename.strip()
    lower = fn.lower()
    # Prefer explicit keywords first (order matters for pep/cds/rna vs generic fasta)
    checks: list[tuple[str, bool]] = [
        ("gff", bool(re.search(r"\.(gff3?|gff\.gz)$", lower) or ".gff" in lower)),
        ("gtf", bool(re.search(r"\.(gtf)(\.gz)?$", lower))),
        ("gbff", bool(re.search(r"\.(gbff|gbk)(\.gz)?$", lower) or "genbank" in lower)),
        ("pep", bool(re.search(r"(^|[._-])(pep|protein|proteome|faa)([._-]|$)", lower) or lower.endswith(".faa") or lower.endswith(".faa.gz"))),
        ("cds", bool(re.search(r"(^|[._-])(cds)([._-]|$)", lower) or "cds_from_genomic" in lower)),
        ("rna", bool(re.search(r"(^|[._-])(rna|mrna|cdna|transcript)([._-]|$)", lower) or "rna_from_genomic" in lower)),
        ("genome", bool(
            re.search(r"(genomic|genome|assembly|scaffold|contig)", lower)
            and re.search(r"\.(fa|fasta|fna)(\.gz)?$", lower)
        ) or bool(re.search(r"_genomic\.(fna|fasta|fa)(\.gz)?$", lower))),
    ]
    for typ, ok in checks:
        if ok:
            return typ
    # Fallback: bare fasta as genome if nothing else matched
    if re.search(r"\.(fa|fasta|fna)(\.gz)?$", lower):
        return "genome"
    return None


def downloads_root(project_root: Path) -> Path:
    return project_root / "data" / "downloads"
