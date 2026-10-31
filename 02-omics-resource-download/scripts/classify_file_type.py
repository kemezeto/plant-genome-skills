#!/usr/bin/env python3
"""Shared file_type classifier for assembly download links.

Used by step2_parse_assembly_links.py (crawl) and step2_reclassify_links.py
(re-label existing TSV without re-fetching).
"""
from __future__ import annotations

import re
from urllib.parse import unquote, urlparse


def _basename(url: str) -> str:
    if not url:
        return ""
    path = unquote(urlparse(url).path)
    name = path.rstrip("/").split("/")[-1]
    # drop query leftovers if present on basename
    return name.split("?")[0]


def _token(blob: str, token: str) -> bool:
    """Match token as a non-alphanumeric-bounded word (underscores are separators)."""
    return re.search(rf"(^|[^a-z0-9]){re.escape(token)}([^a-z0-9]|$)", blob) is not None


def _is_seq_ext(name: str) -> bool:
    return bool(
        re.search(
            r"\.(?:fa|fasta|fna|faa|fq|fastq)(?:\.gz|\.bz2|\.xz)?$",
            name,
            re.I,
        )
    )


def _is_archive(name: str) -> bool:
    return bool(re.search(r"\.(?:tar\.gz|tgz|tar\.bz2|zip)$", name, re.I))


def classify(url: str, label: str = "") -> str:
    """Return a file_type label for a download URL (+ optional link text).

    Primary types: genome, gff, gtf, gbff, cds, pep, rna, feature_table
    Finer other_* subtypes for ambiguous / mixed archives and non-targets.
    """
    name = _basename(url).lower()
    lab = (label or "").lower().strip()
    # ignore generic crawler labels
    if lab in {"dir_listing", "dna"}:
        # keep dna as genome hint via lab == dna below
        pass
    blob = f"{name} {lab}"

    # --- non-target / noisy first (so they don't steal pep/cds via keywords) ---
    if re.search(r"blastp|_vs_(?:nr|tair|sprot|trembl|swiss)", blob) or re.search(
        r"(?:_hit|_nohit)\.fasta", name
    ):
        return "other_blast"
    if re.search(r"\.(?:fastq|fq)(?:\.gz)?$", name) or _token(blob, "fastq"):
        return "other_fastq"
    if re.search(r"\.(?:vcf)(?:\.gz)?$", name) or ".vcf.tar" in name or _token(blob, "vcf"):
        return "other_vcf"
    if re.search(r"\.gfa(?:\.gz)?$", name) or _token(blob, "gfa"):
        return "other_gfa"
    # TE sequence libraries only (TE*.gff stays gff — handled later)
    if "te_db" in name or re.search(
        r"(?:^|[^a-z0-9])(?:te|ltr|repeatmasker)(?:[^a-z0-9]|$)", name
    ):
        if _is_seq_ext(name) and not re.search(r"\.gff3?(?:\.gz)?$", name):
            return "other_te"
    if re.search(r"(?:^|[^a-z0-9])md5(?:[^a-z0-9]|$)", name) or name.endswith("_md5.txt"):
        return "other_md5"
    if re.search(r"genes2(?:go|ipr)|kegg-|orthologs\.xlsx|pathways\.xlsx", name):
        return "other_annotation_table"

    # --- primary biological file types ---
    if (
        re.search(r"\.gbff(?:\.gz)?$", name)
        or re.search(r"\.gbf(?:\.gz)?$", name)
        or _token(blob, "gbff")
        or _token(blob, "genbank")
    ):
        return "gbff"

    if (
        "feature_table" in blob
        or re.search(r"\.feature(?:\.gz)?$", name)
        or re.search(r"(?:^|[^a-z0-9])feature_table(?:[^a-z0-9]|$)", blob)
    ):
        return "feature_table"

    # CDS before genome (cds_from_genomic.fna etc.)
    if (
        _token(blob, "cds")
        or "cds_from_genomic" in name
        or re.search(r"\.cds\.(?:fa|fasta|fna)", name)
        or re.search(r"[_\.-]cds[_\.-]", name)
        or re.search(r"\.CDS\.(?:fa|fasta)", _basename(url))  # rare
    ):
        return "cds"

    # Proteins / peptides
    if re.search(r"\.fsa_aa(?:\.gz)?$", name):
        return "pep"
    if (
        re.search(r"\.faa(?:\.gz)?$", name)
        or _token(blob, "pep")
        or _token(blob, "protein")
        or _token(blob, "proteins")
        or _token(blob, "peptides")
        or _token(blob, "peptide")
        or re.search(r"[_\.-]pep[_\.-]", name)
        or re.search(r"[_\.-]prot[_\.-]", name)
        or re.search(r"\.pep\.(?:fa|fasta|faa)", name)
        or re.search(r"proteins?\.(?:fa|fasta|faa)", name)
        or name.endswith(".prot.fa.gz")
        or ".prot.fa" in name
    ):
        return "pep"

    if re.search(r"\.gff3?(?:\.gz)?$", name) or _token(blob, "gff") or _token(blob, "gff3"):
        return "gff"
    if re.search(r"\.gtf(?:\.gz)?$", name) or _token(blob, "gtf"):
        return "gtf"

    if (
        _token(blob, "rna")
        or _token(blob, "mrna")
        or _token(blob, "ncrna")
        or _token(blob, "transcript")
        or _token(blob, "transcripts")
        or "rna_from_genomic" in name
        or "ncrna" in name
        or re.search(r"[_\.-](?:mrna|ncrna|transcripts?)[_\.-]", name)
    ):
        # expression-matrix archives are not sequence rna
        if _is_archive(name) and re.search(r"expression|tpm|fpkm|counts?", name):
            return "other_archive"
        return "rna"

    # Mixed annotation packs (often tar/gz of gff+pep+cds) — subtype, not primary
    if "genome_annotation" in name or re.search(
        r"(?:annotation|annots?).*\.(?:tar\.gz|tgz|zip)$", name
    ):
        if "gff" in name:
            return "other_gff_tar"
        return "other_annotation_pack"

    # Genome / assembly sequences
    genome_name_hit = (
        "genomic.fna" in name
        or "genomic.fa" in name
        or "genome.fasta" in name
        or "genome.fa" in name
        or re.search(r"\.fna(?:\.gz)?$", name)
        or re.search(r"\.fsa_nt(?:\.gz)?$", name)
        or lab == "dna"
        or _token(blob, "genome")
        or _token(blob, "genomic")
        or re.search(r"(?:^|[^a-z0-9])(?:chrs?|chromosomes?|scaffolds?|contigs?|assembly|pseudomolecules?)(?:[^a-z0-9]|$)", name)
        or re.search(r"\.fixed\.fa(?:\.gz)?$", name)
        or re.search(r"[_\.-]pilon\.fa(?:\.gz)?$", name)
        or re.search(r"\.fa\.smallletter", name)
        or re.search(r"\.replace\.fa", name)
    )
    if genome_name_hit and not _is_archive(name):
        return "genome"

    # Plain sequence files without conflicting tokens → treat as genome
    if _is_seq_ext(name) and not _is_archive(name):
        # already excluded cds/pep/rna/te above
        if not re.search(r"\.(?:xlsx|tsv|txt|bed|bedpe|bw|bam|bai)(?:\.gz)?$", name):
            return "genome"

    # Archives of fasta / ambiguous packs
    if name.endswith(".fa.tar.gz") or name.endswith(".fasta.tar.gz") or name.endswith(
        ".fna.tar.gz"
    ):
        return "other_fa_tar"
    if name.endswith(".gff.tar.gz") or name.endswith(".gff3.tar.gz"):
        return "other_gff_tar"
    if _is_archive(name):
        if "gff" in name:
            return "other_gff_tar"
        if re.search(r"(?:fa|fasta|fna|genome)", name):
            return "other_fa_tar"
        return "other_archive"

    if re.search(r"\.(?:tsv|txt|bed|bedpe|xlsx|bw|bam|bai)(?:\.gz)?$", name):
        return "other_table"

    return "other_unknown"


def classify_row(download_url: str, label: str = "", portal_url: str = "") -> tuple[str, str, str]:
    """Classify a links-TSV row. If download_url empty but portal looks like a
    direct file, use portal_url as the download target (no HTTP fetch).

    Returns (file_type, download_url_maybe_filled, notes_addon).
    """
    url = (download_url or "").strip()
    notes_addon = ""
    if not url and portal_url:
        page = portal_url.strip()
        page_name = _basename(page)
        if page_name and re.search(
            r"\.(?:gz|fasta|fa|fna|faa|gbff|gbf|gff3?|gtf|txt)(?:\?|$)",
            page_name,
            re.I,
        ):
            url = page
            notes_addon = "reclassified_direct_portal_url"
    ft = classify(url, label) if url else "none"
    return ft, url, notes_addon


