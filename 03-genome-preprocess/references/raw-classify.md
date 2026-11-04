# 异源下载物归类（步骤 0）

阶段1 的 `download_inventory.tsv` 只回答「某物种文件夹里有没有某类」；步骤 0 的 **catalog** 回答「每个文件是什么、什么物理格式、多大、可能来自哪」。

| 产物 | 粒度 | 用途 |
|------|------|------|
| `download_inventory.tsv`（阶段1） | 物种 × 类型有无 | 下载是否齐 |
| `raw_file_catalog.tsv`（本 skill） | **每个文件一行** | 归类、选 canonical、跳过超大文件 |
| `raw_type_matrix.tsv` | 物种 × 类型，格内列文件名:format | 一眼看 format 多样性 |
| `preprocess_input_manifest.tsv` | 每物种每类型一个代表路径 | 进入清洗 |

## 扩展名 → format → file_type

压缩后缀（`.gz` / `.bz2` / `.xz` / `.zip` / `.tar.gz`）先剥离再认 format。

| 扩展名（去压缩后） | format | 常见 file_type |
|--------------------|--------|----------------|
| `.gff3` | gff3 | gff |
| `.gff` | gff | gff |
| `.gtf` | gtf | gtf |
| `.gbff` / `.gbk` | gbff | gbff |
| `.fna` / `.fsa_nt` | fna | genome / cds / rna（看文件名关键词） |
| `.fa` / `.fasta` | fa / fasta | genome / cds / pep / rna |
| `.faa` / `.fsa_aa` | faa | pep |
| `.tar.gz` 等且名含 annot/gff | — | other_*_tar / other_annotation_pack |

文件名关键词优先于裸扩展名（与阶段1 `classify_local_filename` 一致）：`cds_from_genomic`→cds，`protein`/`pep`/`.faa`→pep，`rna_from_genomic`→rna，`genomic.fna`→genome。

分类实现：本 skill `scripts/classify_local.py`（**内联副本**，与阶段1对齐；改规则时两边同步）。

## 同类型多文件选取优先级（步骤 1）

对每个 `(showid, file_type)` 只留一个进入清洗：

1. 排除倾向：`empty_file` ≪ `over_300mb`/`skipped_size` ≪ 正常文件（仍登记在 catalog）。
2. format 分：
   - **gff**：gff3 > gff（gtf 单独类型，不自动替代 gff，除非下游明确接受）
   - **genome**：fna > fasta > fa
   - **pep**：faa > fasta/fa
   - **cds/rna**：fna > fasta > fa
3. 压缩：无压缩略优于 gz；tar/zip 包通常不作为 canonical（标 `multi_type_archive`，需先解包）。
4. 仍并列时：较大非空文件优先。

## notes 常用标记

| notes | 含义 |
|-------|------|
| empty_file | 0 字节 |
| over_300mb / skipped_size | 超过 300MB；归类仍登记，默认不进清洗 |
| multi_type_archive | 混合包，需解包后再扫 |
| unclassified | file_type=unknown |

## 跳过扫描的文件

隐藏文件（`.` 开头）、`*.partial` / `*.tmp` / `*.part`：不写入 catalog。
