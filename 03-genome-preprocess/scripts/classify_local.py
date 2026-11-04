#!/usr/bin/env python3
"""Local filename → file_type / format / compression.

Aligned with stage-1 `step3_common.classify_local_filename` + URL classifier
heuristics (skill-1793405308920). Kept as an inline copy so preprocess does
not depend on fragile relative imports of the download skill.
"""
from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

PRIMARY_TYPES = ("genome", "gff", "gtf", "gbff", "cds", "pep", "rna")

_COMPRESS_SUFFIXES = (
    (".tar.gz", "tgz"),
    (".tgz", "tgz"),
    (".tar.bz2", "tbz2"),
    (".tar.xz", "txz"),
    (".gz", "gz"),
    (".bz2", "bz2"),
    (".xz", "xz"),
    (".zip", "zip"),
)

_FORMAT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("gff3", re.compile(r"\.gff3$", re.I)),
    ("gff", re.compile(r"\.gff$", re.I)),
    ("gtf", re.compile(r"\.gtf$", re.I)),
    ("gbff", re.compile(r"\.(gbff|gbk|genbank)$", re.I)),
    ("faa", re.compile(r"\.(faa|fsa_aa)$", re.I)),
    ("fna", re.compile(r"\.(fna|fsa_nt)$", re.I)),
    ("fasta", re.compile(r"\.fasta$", re.I)),
    ("fa", re.compile(r"\.fa$", re.I)),
    ("fastq", re.compile(r"\.(fastq|fq)$", re.I)),
    ("bed", re.compile(r"\.bed$", re.I)),
    ("tsv", re.compile(r"\.tsv$", re.I)),
    ("txt", re.compile(r"\.txt$", re.I)),
]


def strip_compression(filename: str) -> tuple[str, str]:
    """Return (name_without_compression, compression_label)."""
    lower = filename.lower()
    for suf, label in _COMPRESS_SUFFIXES:
        if lower.endswith(suf):
            return filename[: -len(suf)], label
    return filename, "none"


def detect_format(filename: str) -> str:
    base, _ = strip_compression(filename)
    for fmt, pat in _FORMAT_PATTERNS:
        if pat.search(base):
            return fmt
    return "unknown"


def detect_compression(filename: str) -> str:
    return strip_compression(filename)[1]


def classify_local_filename(filename: str) -> str:
    """Best-effort map a local filename to file_type.

    Returns PRIMARY_TYPES member or other_* / unknown.
    Mirrors stage-1 step3_common.classify_local_filename (same check order).
    """
    fn = (filename or "").strip()
    if not fn:
        return "unknown"
    lower = fn.lower()

    if lower.endswith(".partial") or lower.endswith(".tmp") or lower.endswith(".part"):
        return "other_partial"
    if re.search(r"(^|[._-])md5([._-]|$)", lower) or lower.endswith("_md5.txt"):
        return "other_md5"
    if re.search(r"\.(fastq|fq)(\.(gz|bz2|xz))?$", lower):
        return "other_fastq"
    if re.search(r"\.vcf(\.(gz|bz2))?$", lower):
        return "other_vcf"

    # Same order as stage-1 step3_common.classify_local_filename
    checks: list[tuple[str, bool]] = [
        (
            "gff",
            bool(re.search(r"\.(gff3?|gff\.gz)$", lower) or ".gff" in lower)
            and not bool(re.search(r"\.gtf(\.(gz|bz2|xz))?$", lower)),
        ),
        ("gtf", bool(re.search(r"\.gtf(\.(gz|bz2|xz))?$", lower))),
        (
            "gbff",
            bool(
                re.search(r"\.(gbff|gbk)(\.(gz|bz2|xz))?$", lower)
                or "genbank" in lower
            ),
        ),
        (
            "pep",
            bool(
                re.search(r"(^|[._-])(pep|protein|proteome|faa)([._-]|$)", lower)
                or lower.endswith(".faa")
                or lower.endswith(".faa.gz")
                or re.search(r"\.fsa_aa(\.gz)?$", lower)
                or re.search(r"\.pep\.(fa|fasta|faa)", lower)
                or ".prot.fa" in lower
            ),
        ),
        (
            "cds",
            bool(
                re.search(r"(^|[._-])(cds)([._-]|$)", lower)
                or "cds_from_genomic" in lower
                or re.search(r"\.cds\.(fa|fasta|fna)", lower)
            ),
        ),
        (
            "rna",
            bool(
                re.search(r"(^|[._-])(rna|mrna|cdna|transcript|ncrna)([._-]|$)", lower)
                or "rna_from_genomic" in lower
                or re.search(r"\.rna\.(fa|fasta|fna)", lower)
            ),
        ),
        (
            "genome",
            bool(
                re.search(r"(genomic|genome|assembly|scaffold|contig)", lower)
                and re.search(r"\.(fa|fasta|fna)(\.(gz|bz2|xz))?$", lower)
            )
            or bool(re.search(r"_genomic\.(fna|fasta|fa)(\.(gz|bz2|xz))?$", lower)),
        ),
    ]
    for typ, ok in checks:
        if ok:
            return typ

    if re.search(r"\.(tar\.gz|tgz|tar\.bz2|zip)$", lower):
        if "gff" in lower:
            return "other_gff_tar"
        if re.search(r"(fa|fasta|fna|genome)", lower):
            return "other_fa_tar"
        if "annot" in lower:
            return "other_annotation_pack"
        return "other_archive"

    if re.search(r"\.(fa|fasta|fna)(\.(gz|bz2|xz))?$", lower):
        return "genome"

    if re.search(r"\.(tsv|txt|bed|xlsx|bw|bam|bai)(\.gz)?$", lower):
        return "other_table"

    return "unknown"


def url_basename(url: str) -> str:
    if not url:
        return ""
    path = unquote(urlparse(url).path)
    name = path.rstrip("/").split("/")[-1]
    return name.split("?")[0]


def source_hint_from_url(url: str) -> str:
    if not url:
        return ""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    if not host:
        return ""
    if host.startswith("www."):
        host = host[4:]
    known = (
        ("ncbi.nlm.nih.gov", "NCBI"),
        ("ftp.ncbi", "NCBI"),
        ("download.cncb.ac.cn", "CNCB/GWH"),
        ("ngdc.cncb.ac.cn", "CNCB/GWH"),
        ("ensembl", "Ensembl"),
        ("phytozome", "Phytozome"),
        ("plantgdb", "PlantGDB"),
        ("figshare", "figshare"),
        ("zenodo", "Zenodo"),
        ("github.com", "GitHub"),
    )
    for key, label in known:
        if key in host:
            return label
    return host
