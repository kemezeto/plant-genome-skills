# 上游 WGDI 预处理对接说明

本阶段步骤 2+ 委托 **上游 WGDI 预处理仓**（GitHub：`https://github.com/HXC-code/hxc-plant-genome-preprocess`；本地 clone：`/workspace/vendor/plant-genome-wgdi-preprocess`；Python 包名 `pgci_preprocess`）生成 WGDI 四件套与映射表。本 skill 负责 **step0/1 归类选 canonical**，再用 bridge 把 manifest 接到上游固定路径约定。

## 仓库与入口

| 项 | 路径 / 命令 |
|----|-------------|
| Vendor | `/workspace/vendor/plant-genome-wgdi-preprocess`（保持 git clone，可 `git pull`；**勿改源文件做永久 fork**） |
| 上游原生入口 | `bash scripts/run_pipeline.sh DATA_ROOT [--species ID] [--expected-count N]` |
| 本 skill 包装 | `bash scripts/preprocess/run_wgdi_preprocess.sh [DATA_ROOT] [--sync-inventory] [--prepare-accession] …` |
| PYTHONPATH | 包装脚本指向 `…/plant-genome-wgdi-preprocess/scripts` |

上游硬性路径：

```text
DATA_ROOT/data/downloads/{showid}_…
DATA_ROOT/resources/download_inventory.tsv
```

产出：

```text
clean_v2/s{showid}/     # gene_map / chr_map / rejected
analysis_v2/s{showid}/  # cds pep new.gff lens + qc.json
resources/stage_preprocess_v2_summary.tsv
resources/wgdi_v2_index.tsv
resources/wgdi_v2_manifest_sha256.tsv
```

契约细节见 vendor：`references/wgdi-input-contract.md`、`validation-rules.md`、`workflow.md`。

## 与 step0 / step1 的关系

```text
step0 catalog/matrix
  → step1 preprocess_input_manifest.tsv   （chosen_path 指向 downloads）
  → step2_sync_inventory_from_manifest.py （basename → inventory 单列）
  → step2_prepare_wgdi_inputs.py          （缺统一 GCA_/GCF_ 时硬链别名）
  → 上游 run_pipeline                     （clean_v2 + analysis_v2）
```

- **不要**在 inventory 的 gff/cds/pep 列写 `|` 拼接的多文件名；上游每列只认一个 basename。
- sync：`gff` 优先真实 gff；若只有 gtf，则把 **gtf 文件名写入 gff 列**并打 WARNING（上游只读 gff 列）。GTF 语义未必被上游 gff 解析器接受——生产数据应尽量提供 GFF3。
- prepare：在同物种目录内为缺 accession 前缀的文件建 `GCA_…_<原名>` **硬链接**（失败则 copy），再改 inventory 指向别名；**原文件保留**。旁路表：`wgdi_run_inventory.tsv`、`wgdi_accession_alias_log.tsv`；首次改写前备份 `download_inventory.pre_wgdi.tsv`。

## Accession 规则

上游 `_discover_accession`：gff/cds/pep 三个 basename 中的 `^(GCA|GCF)_\d+\.\d+_` 必须 **恰好同一个**，否则 `FAIL reason=accession_mismatch`。

- 已有统一 NCBI 风格前缀 → 无需别名。
- 三者不一致 → prepare 选取其一（优先 cds→pep→gff）统一加前缀硬链。
- 全无 → 使用占位 `GCA_000000000.0_`（可用 `--placeholder-accession` 改）。
- 非 NCBI 命名的「真」用户文件语义不改；别名可删，raw 不删。

## 不改 raw 的原则

- 禁止删除 / 覆盖 `data/downloads` 内原始下载物语义。
- 允许：同目录硬链别名、DEMO fixture（如 showid `900`）、resources 旁路表与 backup。
- vendor 目录保持可 pull；适配只放在本 skill / 工作区 `scripts/preprocess/`。

## 常见失败 reason

| reason | 含义 / 处理 |
|--------|-------------|
| `accession_mismatch` | 三文件前缀不统一 → 跑 `--prepare-accession` |
| `missing_or_empty_input` | inventory 指向的文件不存在或空 |
| `multiple_nuclear_taxa` | GFF region 上多个核基因组 taxon |
| `no_valid_representative_genes` | CDS/pep 与 GFF protein_id 对不上，或翻译/可读框全拒 |
| `empty_wgdi_sequence_set` | 序列筛选后无保留染色体 |
| validate `expected_count_mismatch` | `--expected-count` 与 `wgdi_v2_index.tsv` 行数不符（部分跑时用实际 OK 种数） |

CDS FASTA 头需带 `[protein_id=…]`（或可被 fallback 解析），且与 GFF CDS `protein_id` / pep 头一致。最小可跑样例见工作区 `data/downloads/900_…` 与 vendor `tests/test_pipeline.py`。

## 限制（本 bridge 不做）

- 仅支持已具备 **gff（或写入 gff 列的 gtf 文件名）+ cds + pep** 的物种；缺一角不会自动从 genome+gff 用 gffread 提取。
- 不跑 BLAST / WGDI / 真下载。
- 不 UpdateSkill、不推 GitHub（由父代理决定）。
