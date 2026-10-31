# Step 3: download folders, download script, inventory

Work directory: project root `plant-genome-resources/`.

## 1. Create folders (one per show_id)

Naming: `{show_id}_{Order}_{Family}({Species})`  
Unsafe path characters (`/ \ : * ? " < > |`) and odd whitespace → `_`.

```bash
python3 scripts/step3_mkdirs.py
# preview only:
python3 scripts/step3_mkdirs.py --dry-run
```

Folders land in `data/downloads/`.

## 2. Download (default dry-run)

Reads `resources/predownload_list.tsv` + `resources/assembly_download_links.tsv`.  
Only `file_type` in: `gff`, `genome`, `cds`, `pep`, `rna`, `gbff`, `gtf`.  
Skip if `Content-Length` > 300 MiB; if size unknown, attempt with abort when over limit (`--yes` only).

**Retries** (default on): `--retries 2` means 2 retries after the first failure → up to **3 attempts** total. Brief linear backoff (`--backoff 1.5` seconds × attempt) between retries. Only transient failures (network/`error:*`, HTTP 408/429/5xx) are retried.

**Concurrency**: `-j` / `--workers` (default **1**). Useful range **2–4**; values are clamped to **1–8**.

```bash
# plan only (default) — example first 5 jobs:
python3 scripts/step3_download.py --limit 5
# dry-run smoke with concurrency + retries:
python3 scripts/step3_download.py -j 2 --retries 2 --limit 3
# real download (explicit):
python3 scripts/step3_download.py --yes
# real download with 4 workers:
python3 scripts/step3_download.py --yes -j 4
# one species:
python3 scripts/step3_download.py --yes --show-id 1
```

| Flag | Default | Notes |
|------|---------|--------|
| `--dry-run` / `--yes` | dry-run | Must pass `--yes` for real downloads |
| `--retries` | `2` | Retries after first failure (≤3 attempts total) |
| `--backoff` | `1.5` | Base seconds for linear backoff between retries |
| `-j` / `--workers` | `1` | ThreadPool workers; useful 2–4; clamped 1–8 |
| `--max-mb` | `300` | Skip if Content-Length > this many MiB |
| `--limit` | `0` | First N jobs only (`0` = all) |
| `--show-id` | (empty) | Restrict to one show_id |

Log: `resources/step3_download_log.tsv` (includes `attempts` column).

## 3. Inventory / stats (folders only)

Scans `data/downloads/*` folder names + files. Does **not** use the TSV link tables.  
Writes `resources/download_inventory.tsv` columns:  
`showid`, `Order`, `Family`, `Species`, `gff`, `genome`, `cds`, `pep`, `rna`, `gbff`, `gtf`  
(cell = filename if present, else empty).

```bash
python3 scripts/step3_stats.py
```

### Important tip

`download_inventory.tsv` does **not** auto-update. After you **manually add or replace** files in any `data/downloads/...` folder, re-run:

```bash
python3 scripts/step3_stats.py
```

to refresh the inventory table.

## 4. Manual download tips

When the portal yields `file_type=none` or the automated download cannot reach the file:

1. **Priority species**: those in `resources/species_no_download_links.tsv`, and rows with `file_type=none` in `assembly_download_links.tsv`.
2. **Priority file kinds** (match approximate name tokens):
   - `gff` / `gtf` (genome annotation: gff3, annotation, …)
   - `gbff`
   - `cds`
   - `pep` (Protein / protein / aa / peptide, …)
   - `rna` / `mrna`
   - then `genome` if still needed
3. **Size**: skip any single file **>300 MiB** (same default as `--max-mb`).
4. Place files into the matching `data/downloads/{show_id}_.../` folder, then re-run `python3 scripts/step3_stats.py`.
