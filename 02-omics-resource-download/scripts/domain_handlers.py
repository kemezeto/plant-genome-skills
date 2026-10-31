#!/usr/bin/env python3
"""Domain-specific portal handlers to recover file download links.

Used by step2_parse_assembly_links.py (fallback) and step2_recover_none.py
(targeted re-parse of none show_ids). Enumerates public download URLs only;
does not download large genomics payloads.
"""
from __future__ import annotations

import json
import random
import re
import ssl
import time
import urllib.error
import urllib.request
from typing import Callable
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from classify_file_type import classify

UA = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; plant-genome-download/1.1; "
        "+https://github.com/local/plant-genome-resources)"
    ),
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
}
FILE_RE = re.compile(
    r"\.(?:gz|fasta|fa|fna|faa|gbff|gbf|gff3?|gtf|txt)(?:\?|$)",
    re.I,
)
GCA_RE = re.compile(r"\b(GC[AF]_\d+(?:\.\d+)?)\b", re.I)
GWH_RE = re.compile(r"\b(GWH[A-Z]{4}\d+(?:\.\d+)?)\b", re.I)
PRJ_RE = re.compile(r"\b(PRJ[A-Z]{2}\d+)\b", re.I)
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.I)
FIGSHARE_ART_RE = re.compile(
    r"figshare\.com/articles/(?:dataset|figure|online_resource|media)/[^/]+/(\d+)",
    re.I,
)
FIGSHARE_DOI_RE = re.compile(r"(?:m9\.)?figshare\.(\d+)", re.I)
ZENODO_RE = re.compile(r"zenodo\.org/(?:records?|record)/(\d+)", re.I)
ZENODO_DOI_RE = re.compile(r"10\.5281/zenodo\.(\d+)", re.I)

_SSL_CTX = ssl.create_default_context()
_CACHE_LOCK = __import__("threading").Lock()
_BIOPROJECT_CACHE: dict[str, list] = {}
_GWH_ACC_CACHE: dict[str, dict | None] = {}


class FetchError(Exception):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


def _sleep_backoff(attempt: int, base: float = 0.6) -> None:
    time.sleep(base * (2**attempt) + random.uniform(0, 0.3))


def fetch(
    url: str,
    timeout: int = 45,
    retries: int = 3,
    accept: str | None = None,
    method: str = "GET",
    data: bytes | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Return (body_text, final_url). Retries on 403/500/transient errors."""
    headers = dict(UA)
    if accept:
        headers["Accept"] = accept
    if extra_headers:
        headers.update(extra_headers)
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
                raw = resp.read()
                # Cap body read already done; reject huge accidental downloads (>15MB text)
                if len(raw) > 15 * 1024 * 1024:
                    raise FetchError(f"response too large ({len(raw)} bytes)")
                charset = "utf-8"
                ctype = resp.headers.get_content_charset() or charset
                try:
                    text = raw.decode(ctype, "replace")
                except Exception:
                    text = raw.decode("utf-8", "replace")
                return text, resp.geturl()
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (403, 429, 500, 502, 503, 504) and attempt < retries:
                _sleep_backoff(attempt)
                continue
            raise FetchError(f"http {e.code}", code=e.code) from e
        except Exception as e:
            last_err = e
            if attempt < retries:
                _sleep_backoff(attempt)
                continue
            raise FetchError(f"fetch failed: {e}") from e
    raise FetchError(f"fetch failed: {last_err}")


def fetch_json(url: str, **kwargs) -> tuple[object, str]:
    body, final = fetch(url, accept="application/json", **kwargs)
    return json.loads(body), final


def _dedupe(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for u, t in items:
        if not u or u in seen:
            continue
        seen.add(u)
        out.append((u, t))
    return out


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
    # bare download.cncb / ftp URLs in text/JSON
    for m in re.finditer(
        r"https?://(?:download\.cncb\.ac\.cn|ftp\.ncbi\.nlm\.nih\.gov)/[^\s\"'<>]+",
        html,
        re.I,
    ):
        u = m.group(0).rstrip(".,);")
        if FILE_RE.search(u):
            links.append((u, ""))
    return _dedupe(links)


def list_dir_files(dir_url: str) -> list[str]:
    if not dir_url.endswith("/"):
        dir_url += "/"
    try:
        html, _ = fetch(dir_url, retries=2, timeout=40)
    except Exception:
        return []
    files: list[str] = []
    for href in re.findall(r'href=["\']([^"\']+)["\']', html, re.I):
        if href in ("./", "../") or href.endswith("/"):
            continue
        if FILE_RE.search(href):
            files.append(urljoin(dir_url, href))
    return sorted(set(files))


def normalize_portal_url(raw: str) -> str:
    """Fix spaced hosts, accession labels, and mixed junk portals."""
    s = (raw or "").strip()
    if not s or s.upper() == "NA":
        return ""
    # Remove zero-width / odd unicode spaces
    s = s.replace("\u200b", "").replace("\u2009", "").replace("\u2010", "-")
    # Collapse spaces inside host-like URLs: "https:// ngdc. cncb. ..."
    if re.match(r"(?i)https?://", s) and " " in s:
        # Keep first URL if multiple concatenated with spaces
        parts = re.split(r"\s+(?=https?://)", s)
        s = parts[0]
        # Drop parenthetical junk: "URL (https://other...)"
        s = re.split(r"\s+\(", s)[0].strip()
        # Remove ALL whitespace inside the URL (common OCR/table artifact)
        m = re.match(r"(?i)(https?://)(.+)$", s)
        if m:
            s = m.group(1) + re.sub(r"\s+", "", m.group(2))
    # Accession labels
    m = re.match(r"(?i)^(NCBI|NGDC|ENA)\s*:\s*(.+)$", s)
    if m:
        kind, rest = m.group(1).upper(), m.group(2).strip()
        gca = GCA_RE.search(rest)
        gwh = GWH_RE.search(rest)
        prj = PRJ_RE.search(rest)
        if kind == "NCBI" and gca:
            return f"https://www.ncbi.nlm.nih.gov/datasets/genome/{gca.group(1)}/"
        if kind == "NCBI" and prj:
            return f"https://www.ncbi.nlm.nih.gov/bioproject/?term={prj.group(1)}"
        if kind == "NGDC" and gwh:
            return f"https://ngdc.cncb.ac.cn/search/?dbId=gwh&q={gwh.group(1)}"
        if kind == "NGDC" and prj:
            return f"https://ngdc.cncb.ac.cn/bioproject/browse/{prj.group(1)}"
        if kind == "ENA" and gca:
            return f"https://www.ebi.ac.uk/ena/browser/view/{gca.group(1)}"
        if kind == "ENA" and prj:
            return f"https://www.ebi.ac.uk/ena/browser/view/{prj.group(1)}"
    return s


def ncbi_ftp_prefix(accession: str) -> str | None:
    m = re.match(r"(GC[AF])_(\d+)(?:\.(\d+))?$", accession, re.I)
    if not m:
        return None
    prefix, digits, ver = m.group(1).upper(), m.group(2), m.group(3) or "1"
    acc = f"{prefix}_{digits}.{ver}"
    # zero-pad to 9 digits for path
    d = digits.zfill(9)
    a, b, c = d[0:3], d[3:6], d[6:9]
    return f"https://ftp.ncbi.nlm.nih.gov/genomes/all/{prefix}/{a}/{b}/{c}/", acc


def handle_ncbi(portal: str, ctx: dict) -> tuple[list[tuple[str, str]], str]:
    """Resolve NCBI datasets/assembly/label portals via public FTP listing."""
    notes = "ncbi_ftp"
    text = portal
    gca = GCA_RE.search(text)
    if not gca:
        return [], "ncbi_no_accession"
    accession = gca.group(1)
    # normalize version: GCA_123 -> try .1
    if "." not in accession:
        accession = accession + ".1"
    pref = ncbi_ftp_prefix(accession)
    if not pref:
        return [], "ncbi_bad_accession"
    base, acc = pref
    try:
        html, _ = fetch(base, retries=3, timeout=40)
    except FetchError as e:
        return [], f"ncbi_ftp_list_failed:{e}"
    # find assembly subdir
    dirs = re.findall(rf'href="({re.escape(acc)}[^"/]*/)"', html)
    if not dirs:
        # sometimes only one dir
        dirs = re.findall(r'href="(GC[AF]_[^"/]+/)"', html, re.I)
    if not dirs:
        return [], "ncbi_ftp_no_assembly_dir"
    asm_url = urljoin(base, dirs[0])
    files = list_dir_files(asm_url)
    # Also check for annotation subfolder? usually flat.
    # Prefer genomic.* and annotation-ish files
    links = [(u, "ncbi_ftp") for u in files]
    if not links:
        return [], "ncbi_ftp_empty"
    return _dedupe(links), notes


def _gwh_query_by_accession(accession: str) -> dict | None:
    key = accession.upper()
    with _CACHE_LOCK:
        if key in _GWH_ACC_CACHE:
            return _GWH_ACC_CACHE[key]
    payload = {
        "draw": 1,
        "columns": [
            {
                "data": None,
                "name": "",
                "searchable": False,
                "orderable": False,
                "search": {"value": "", "regex": False},
            },
            {
                "data": "scientificName",
                "name": "scientificName",
                "searchable": True,
                "orderable": True,
                "search": {"value": "", "regex": False},
            },
            {
                "data": "accession",
                "name": "accession",
                "searchable": True,
                "orderable": True,
                "search": {"value": accession, "regex": False},
            },
        ],
        "order": [{"column": 1, "dir": "asc"}],
        "start": 0,
        "length": 5,
        "search": {"value": "", "regex": False},
    }
    body = json.dumps(payload).encode()
    raw, _ = fetch(
        "https://ngdc.cncb.ac.cn/gwh/api/esdt/gwh_assemblies/query",
        method="POST",
        data=body,
        accept="application/json",
        extra_headers={
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://ngdc.cncb.ac.cn",
            "Referer": "https://ngdc.cncb.ac.cn/gwh/browse/assembly",
        },
        retries=3,
        timeout=50,
    )
    data = json.loads(raw)
    rows = data.get("data") or []
    # exact accession match preferred
    hit = None
    for row in rows:
        if (row.get("accession") or "").upper().startswith(accession.upper()[:12]):
            hit = row
            break
    if hit is None:
        hit = rows[0] if rows else None
    with _CACHE_LOCK:
        _GWH_ACC_CACHE[key] = hit
    return hit


def _links_from_gwh_row(row: dict) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    # metadataList often embeds full URLs
    for item in row.get("metadataList") or []:
        if isinstance(item, str) and item.startswith("http") and FILE_RE.search(item):
            links.append((item, "gwh_metadata"))
    ftp_dir = (row.get("ftpDir") or "").strip()
    if ftp_dir:
        base = ftp_dir
        if not base.startswith("http"):
            base = "https://download.cncb.ac.cn/gwh/" + base.lstrip("/")
        if not base.endswith("/"):
            base += "/"
        field_map = [
            ("dna", "DNA"),
            ("gff", "GFF"),
            ("rna", "RNA"),
            ("cds", "CDS"),
            ("protein", "Protein"),
            ("refseqDna", "RefSeq DNA"),
            ("refseqGff", "RefSeq GFF"),
            ("refseqRna", "RefSeq RNA"),
            ("refseqCds", "RefSeq CDS"),
            ("refseqProtein", "RefSeq Protein"),
        ]
        for key, label in field_map:
            fn = row.get(key)
            if fn and isinstance(fn, str) and FILE_RE.search(fn):
                links.append((urljoin(base, fn), label))
        # directory listing to catch versioned extras
        for fu in list_dir_files(base):
            links.append((fu, "dir_listing"))
        # also try .1 variant dir
        if not base.rstrip("/").endswith(".1"):
            for fu in list_dir_files(base.rstrip("/") + ".1/"):
                links.append((fu, "dir_listing"))
    return _dedupe(links)


def _match_bioproject_assembly(
    assemblies: list[dict], accession_name: str, species: str
) -> dict | None:
    if not assemblies:
        return None
    if len(assemblies) == 1:
        return assemblies[0]
    name = (accession_name or "").strip()
    tokens: list[str] = []
    if name:
        tokens.append(name)
        m = re.match(r"^([A-Za-z]*\d+)", name)
        if m:
            tokens.append(m.group(1))
    # index by strain token in folder
    by_strain: dict[str, dict] = {}
    for a in assemblies:
        dls = (
            (a.get("downloadLinks") or {}).get("downloadLinksList")
            or []
        )
        if not dls:
            continue
        folder = dls[0].get("link", "").split("/")[-2]
        m = re.search(r"_([^_/]+)_GWH[A-Z]{4}\d+", folder)
        if m:
            by_strain[m.group(1)] = a
        # also index full folder
        by_strain[folder] = a
    for t in sorted(tokens, key=len, reverse=True):
        if t in by_strain:
            return by_strain[t]
        for strain, a in by_strain.items():
            if t and t in strain:
                return a
    # species filter
    sp = (species or "").strip().replace(" ", "_")
    if sp:
        cand = []
        for a in assemblies:
            dls = (a.get("downloadLinks") or {}).get("downloadLinksList") or []
            if dls and sp.lower() in dls[0].get("link", "").lower():
                cand.append(a)
        if len(cand) == 1:
            return cand[0]
    return None


def handle_ngdc(portal: str, ctx: dict) -> tuple[list[tuple[str, str]], str]:
    url = portal
    notes_parts: list[str] = []

    # Assembly / Genome / ncbi_assembly show pages: parse HTML + dir listing
    if re.search(r"/gwh/(?:Assembly|Genome|ncbi_assembly)/\d+/show", url, re.I):
        try:
            html, final = fetch(url, retries=4, timeout=50)
        except FetchError as e:
            return [], f"ngdc_show_fetch:{e}"
        links = extract_page_file_links(final, html)
        dirs = {
            u.rsplit("/", 1)[0] + "/"
            for u, _ in links
            if "download.cncb.ac.cn" in u
        }
        for d in dirs:
            for fu in list_dir_files(d):
                links.append((fu, "dir_listing"))
        links = _dedupe(links)
        if links:
            return links, "ngdc_show_page"
        return [], "ngdc_show_no_links"

    # Search pages with GWH accession
    gwh = GWH_RE.search(url) or GWH_RE.search(ctx.get("annotation") or "")
    if not gwh and "search" in url:
        qs = parse_qs(urlparse(url).query)
        q = (qs.get("q") or qs.get("keyword") or [""])[0]
        gwh = GWH_RE.search(q)

    if gwh:
        acc = gwh.group(1)
        # strip version for query (API uses unversioned often)
        acc_q = acc.split(".")[0]
        try:
            row = _gwh_query_by_accession(acc_q)
        except FetchError as e:
            return [], f"ngdc_gwh_query:{e}"
        if not row:
            return [], "ngdc_gwh_not_found"
        links = _links_from_gwh_row(row)
        # also follow Genome page for richer files
        gid = row.get("genomeId")
        if gid:
            try:
                html, final = fetch(
                    f"https://ngdc.cncb.ac.cn/gwh/Genome/{gid}/show",
                    retries=2,
                    timeout=45,
                )
                extra = extract_page_file_links(final, html)
                # keep files matching this GWH accession
                for u, t in extra:
                    if acc_q in u or (row.get("accession") or "") in u:
                        links.append((u, t or "genome_page"))
            except FetchError:
                pass
        links = _dedupe(links)
        if links:
            return links, "ngdc_gwh_api"
        return [], "ngdc_gwh_api_no_files"

    # BioProject PRJCA (browse or search q=)
    prj = None
    m = re.search(r"/bioproject/browse/(PRJ[A-Z]{2}\d+)", url, re.I)
    if m:
        prj = m.group(1)
    if not prj and "search" in url:
        qs = parse_qs(urlparse(url).query)
        q = (qs.get("q") or [""])[0]
        m = PRJ_RE.search(q)
        if m and m.group(1).upper().startswith("PRJCA"):
            prj = m.group(1)
    if not prj:
        m = PRJ_RE.search(url)
        if m and m.group(1).upper().startswith("PRJCA"):
            prj = m.group(1)

    if prj and prj.upper().startswith("PRJCA"):
        prj_key = prj.upper()
        with _CACHE_LOCK:
            cached = _BIOPROJECT_CACHE.get(prj_key)
        if cached is not None:
            assemblies = cached
        else:
            api = (
                "https://ngdc.cncb.ac.cn/gwh/gsa/ajax/"
                f"getAssembliesListByBioProjectAccession/{prj}"
            )
            try:
                raw, _ = fetch(api, retries=3, timeout=90, accept="application/json")
                data = json.loads(raw)
            except FetchError as e:
                return [], f"ngdc_bioproject_api:{e}"
            assemblies = data.get("assembliesList") or []
            with _CACHE_LOCK:
                _BIOPROJECT_CACHE[prj_key] = assemblies
        if not assemblies:
            return [], "ngdc_bioproject_no_assemblies"
        hit = _match_bioproject_assembly(
            assemblies,
            ctx.get("accession_name") or "",
            ctx.get("species") or "",
        )
        if not hit:
            return [], f"ngdc_bioproject_unmatched_n={len(assemblies)}"
        links: list[tuple[str, str]] = []
        for dl in (hit.get("downloadLinks") or {}).get("downloadLinksList") or []:
            link = dl.get("link") or ""
            if link:
                links.append((link, dl.get("label") or ""))
        # expand dir
        if links:
            d = links[0][0].rsplit("/", 1)[0] + "/"
            for fu in list_dir_files(d):
                links.append((fu, "dir_listing"))
        links = _dedupe(links)
        if links:
            return links, f"ngdc_bioproject:{prj}:{hit.get('accession','')}"
        return [], "ngdc_bioproject_no_files"

    return [], "ngdc_unhandled"


def handle_doi_figshare_zenodo(
    portal: str, ctx: dict
) -> tuple[list[tuple[str, str]], str]:
    url = portal
    notes: list[str] = []

    # Resolve DOI → target via Handle API (avoids some HTML 403s)
    doi_m = DOI_RE.search(url) or (
        DOI_RE.search(urlparse(url).path) if "doi.org" in url else None
    )
    resolved = url
    if "doi.org" in url or urlparse(url).netloc.lower() in {"doi.org", "dx.doi.org"}:
        doi = doi_m.group(0).rstrip(".") if doi_m else urlparse(url).path.lstrip("/")
        doi = unquote(doi)
        try:
            data, _ = fetch_json(
                f"https://doi.org/api/handles/{doi}", retries=2, timeout=30
            )
            for v in data.get("values") or []:
                if v.get("type") == "URL":
                    resolved = v.get("data", {}).get("value") or resolved
                    notes.append("doi_resolved")
                    break
        except FetchError as e:
            return [], f"doi_resolve_failed:{e}"

    # Figshare article id
    art_id = None
    m = FIGSHARE_ART_RE.search(resolved) or FIGSHARE_ART_RE.search(url)
    if m:
        art_id = m.group(1)
    if not art_id:
        m = FIGSHARE_DOI_RE.search(resolved) or FIGSHARE_DOI_RE.search(url)
        if m:
            art_id = m.group(1)
    if art_id:
        try:
            data, _ = fetch_json(
                f"https://api.figshare.com/v2/articles/{art_id}",
                retries=2,
                timeout=40,
            )
        except FetchError as e:
            return [], f"figshare_api:{e}"
        links: list[tuple[str, str]] = []
        for fobj in data.get("files") or []:
            name = fobj.get("name") or ""
            dl = fobj.get("download_url") or ""
            if dl and (
                FILE_RE.search(name)
                or FILE_RE.search(dl)
                or re.search(r"\.(fa|fasta|fna|faa|gff3?|gtf|gbff|gz|zip|tar)$", name, re.I)
            ):
                links.append((dl, name))
        if links:
            return _dedupe(links), "figshare_api:" + ",".join(notes + [art_id])
        return [], "figshare_api_no_files"

    # Zenodo
    zid = None
    m = ZENODO_RE.search(resolved) or ZENODO_RE.search(url)
    if m:
        zid = m.group(1)
    if not zid:
        m = ZENODO_DOI_RE.search(resolved) or ZENODO_DOI_RE.search(url)
        if m:
            zid = m.group(1)
    if zid:
        try:
            data, _ = fetch_json(
                f"https://zenodo.org/api/records/{zid}", retries=2, timeout=40
            )
        except FetchError as e:
            return [], f"zenodo_api:{e}"
        links = []
        for fobj in data.get("files") or []:
            key = fobj.get("key") or ""
            href = (fobj.get("links") or {}).get("content") or (
                fobj.get("links") or {}
            ).get("self")
            if not href:
                href = f"https://zenodo.org/api/records/{zid}/files/{key}/content"
            if key or href:
                links.append((href, key))
        if links:
            return _dedupe(links), "zenodo_api:" + zid
        return [], "zenodo_api_no_files"

    # Public HTML fallback on resolved URL
    if resolved.startswith("http"):
        try:
            html, final = fetch(resolved, retries=2, timeout=40)
            links = extract_page_file_links(final, html)
            if links:
                return links, "doi_html:" + ",".join(notes)
        except FetchError as e:
            return [], f"doi_html:{e}"
    return [], "doi_unhandled"


def handle_identifiers(portal: str, ctx: dict) -> tuple[list[tuple[str, str]], str]:
    # Extract embedded accessions without depending on redirect body
    gca = GCA_RE.search(portal)
    if gca:
        return handle_ncbi(
            f"https://www.ncbi.nlm.nih.gov/datasets/genome/{gca.group(1)}/", ctx
        )
    gwh = GWH_RE.search(portal)
    if gwh:
        return handle_ngdc(
            f"https://ngdc.cncb.ac.cn/search/?dbId=gwh&q={gwh.group(1)}", ctx
        )
    # follow redirect once conceptually by fetching
    try:
        html, final = fetch(portal, retries=2, timeout=40)
    except FetchError as e:
        return [], f"identifiers_fetch:{e}"
    if "ncbi.nlm.nih.gov" in final or GCA_RE.search(final):
        return handle_ncbi(final, ctx)
    if "ngdc.cncb" in final or GWH_RE.search(final):
        return handle_ngdc(final, ctx)
    links = extract_page_file_links(final, html)
    if links:
        return links, "identifiers_html"
    # ENA GCA on final
    gca = GCA_RE.search(final) or GCA_RE.search(html)
    if gca:
        return handle_ncbi(
            f"https://www.ncbi.nlm.nih.gov/datasets/genome/{gca.group(1)}/", ctx
        )
    return [], "identifiers_no_links"


def handle_ibi(portal: str, ctx: dict) -> tuple[list[tuple[str, str]], str]:
    """N3database is often NA / HTTP 500. Try Annotation alternate if present."""
    annot = (ctx.get("annotation") or "").strip()
    candidates = []
    if annot and annot.upper() != "NA" and annot != portal:
        candidates.append(annot)
    # portal itself if not NA stub
    if portal and not re.search(r"/N3database/NA/?$", portal, re.I):
        candidates.append(portal)
    if not candidates:
        return [], "ibi_na_or_down"
    for cand in candidates:
        if not cand.startswith("http"):
            continue
        # If annotation points at another domain, dispatch
        host = urlparse(cand).netloc.lower()
        if "ncbi" in host or GCA_RE.search(cand):
            return handle_ncbi(cand, ctx)
        if "ngdc" in host or "cncb" in host:
            return handle_ngdc(cand, ctx)
        if "doi.org" in host or "figshare" in host or "zenodo" in host:
            return handle_doi_figshare_zenodo(cand, ctx)
        try:
            html, final = fetch(cand, retries=2, timeout=30)
            links = extract_page_file_links(final, html)
            if links:
                return links, "ibi_alt_page"
        except FetchError:
            continue
    return [], "ibi_unreachable"


def handle_generic_show(portal: str, ctx: dict) -> tuple[list[tuple[str, str]], str]:
    """Retry generic HTML extract with backoff (helps flaky 500/403)."""
    try:
        html, final = fetch(portal, retries=3, timeout=45)
    except FetchError as e:
        return [], f"generic_fetch:{e}"
    links = extract_page_file_links(final, html)
    dirs = {
        u.rsplit("/", 1)[0] + "/"
        for u, _ in links
        if "download.cncb.ac.cn" in u
    }
    for d in dirs:
        for fu in list_dir_files(d):
            links.append((fu, "dir_listing"))
    links = _dedupe(links)
    if links:
        return links, "generic_retry"
    return [], "generic_no_links"


def handle_phytozome(portal: str, ctx: dict) -> tuple[list[tuple[str, str]], str]:
    # JGI Phytozome downloads require login; do not pretend success.
    return [], "phytozome_login_required"


Handler = Callable[[str, dict], tuple[list[tuple[str, str]], str]]


def select_handler(portal: str) -> tuple[str, Handler] | None:
    if not portal:
        return None
    host = urlparse(portal).netloc.lower()
    path = portal.lower()
    if "phytozome" in host or "data.jgi.doe.gov" in host or "genome.jgi.doe.gov" in host:
        return "phytozome", handle_phytozome
    if "ibi.zju.edu.cn" in host:
        return "ibi", handle_ibi
    if "identifiers.org" in host or "identifers.org" in host:
        return "identifiers", handle_identifiers
    if (
        "doi.org" in host
        or "figshare.com" in host
        or "zenodo.org" in host
        or "dx.doi.org" in host
    ):
        return "doi_figshare_zenodo", handle_doi_figshare_zenodo
    if (
        "ngdc.cncb.ac.cn" in host
        or "download.cncb.ac.cn" in host
        or "bigd.big.ac.cn" in host
    ):
        return "ngdc", handle_ngdc
    if (
        "ncbi.nlm.nih.gov" in host
        or "ftp.ncbi.nlm.nih.gov" in host
        or path.startswith("ncbi:")
        or GCA_RE.search(portal)
        and ("ena" in host or "ebi.ac.uk" in host or "datasets/genome" in path)
    ):
        # ENA browser view of GCA → NCBI FTP
        if "ebi.ac.uk" in host and GCA_RE.search(portal):
            return "ncbi", handle_ncbi
        if "ncbi" in host or GCA_RE.search(portal):
            return "ncbi", handle_ncbi
    if re.match(r"(?i)NCBI:", portal) or (
        GCA_RE.search(portal) and not portal.startswith("http")
    ):
        return "ncbi", handle_ncbi
    if re.match(r"(?i)NGDC:", portal) or GWH_RE.search(portal):
        return "ngdc", handle_ngdc
    return None


def recover_links(
    portal_url: str, ctx: dict | None = None
) -> tuple[list[tuple[str, str]], str, str]:
    """Try domain handler then optional generic retry.

    Returns (links, handler_name, notes).
    """
    ctx = dict(ctx or {})
    portal = normalize_portal_url(portal_url)
    if not portal:
        return [], "none", "no portal url"

    # Direct file URL
    page_name = portal.rstrip("/").split("/")[-1].split("?")[0]
    if FILE_RE.search(page_name):
        return [(portal, page_name)], "direct", "direct_file_url"

    selected = select_handler(portal)
    if selected:
        name, fn = selected
        links, notes = fn(portal, ctx)
        if links:
            return links, name, notes
        # NCBI bioproject without GCA: stop
        if name in {"phytozome", "ibi"}:
            return [], name, notes
        # Fall through to generic for some failures
        if name in {"doi_figshare_zenodo"} and "403" in notes:
            return [], name, notes
        if links or notes.endswith("login_required") or "unmatched" in notes:
            return [], name, notes
        # If handler returned empty with a specific note, keep it unless generic might help
        if name == "ncbi" and "no_accession" in notes:
            # try generic page for bioproject HTML (rarely has files)
            glinks, gnotes = handle_generic_show(portal, ctx)
            if glinks:
                return glinks, "generic", gnotes
            return [], name, notes
        if name == "ngdc":
            return [], name, notes
        return [], name, notes

    glinks, gnotes = handle_generic_show(portal, ctx)
    if glinks:
        return glinks, "generic", gnotes
    return [], "generic", gnotes


def links_to_rows(
    base: dict[str, str],
    links: list[tuple[str, str]],
    notes: str,
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for u, t in links:
        ft = classify(u, t)
        n = notes
        if ft == "gbff" and "gbff" not in n:
            n = (n + ";gbff_available") if n else "gbff_available"
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
