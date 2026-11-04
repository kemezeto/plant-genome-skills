# 命名约定（阶段 2 清洗输出）

全流程固定一套物种代码与组装版本，避免下游 BLAST / 共线性对不上。

## SpeciesCode

建议规则（项目内二选一，写进 `resources/species_code_map.tsv` 后勿改）：

1. **属3 + 种加3**：`Abeliophyllum distichum` → `Abedis`（属前 3 字母小写化首字母大写 + 种加前 3；冲突时加数字 `Abedis2`）。
2. **项目固定表**：手工维护 `showid → SpeciesCode`，优先于自动缩写。

| 字段 | 说明 |
|------|------|
| showid | 与阶段1文件夹/`predownload_list` 一致 |
| Species | 学名原文 |
| SpeciesCode | 清洗路径与文件名前缀 |
| assembly | 组装版本或 GCA/GCF accession |

冲突处理：同属多种时加种加更多字母或 accession 末 4 位。

## 目录

```text
clean/{SpeciesCode}/{assembly}/
├── {SpeciesCode}.genome.fa
├── {SpeciesCode}.gff3
├── {SpeciesCode}.cds.fa
├── {SpeciesCode}.pep.fa
├── {SpeciesCode}.chr_map.tsv      # 可选但推荐
└── {SpeciesCode}.manifest.tsv     # 本组装元数据
```

- raw 仍留在 `data/downloads/{showid}_{Order}_{Family}({Species})/`，**不改动下载原件**。
- 多组装并存时每个 `assembly/` 一份；选定进入下游的那套在总 manifest 里标记 `primary=yes`。

## 标准文件名

| 类型 | 文件名 | 备注 |
|------|--------|------|
| genome | `{SpeciesCode}.genome.fa` | 解压后的 DNA fasta；软链可指向原 `.gz` 但推荐写出解压标准化本 |
| gff | `{SpeciesCode}.gff3` | 统一为 GFF3；若源为 GTF 需转换后再放 |
| cds | `{SpeciesCode}.cds.fa` | 核酸；ID 尽量与 pep / gff 基因或转录本 ID 可对应 |
| pep | `{SpeciesCode}.pep.fa` | 氨基酸 |
| rna | `{SpeciesCode}.rna.fa` | 可选 |
| chr_map | `{SpeciesCode}.chr_map.tsv` | 见下 |

禁止在 `clean/` 使用未记录的临时名（如 `final.fa`、`new.gff`）。

## chr_map.tsv 列

| 列 | 含义 |
|----|------|
| raw_id | genome / gff 中原始序列 ID |
| clean_id | 标准化后 ID（如 `Chr01`、`scaffold_0001`） |
| length | 可选，bp |
| notes | 可选（merged / renamed / dropped） |

genome 与 gff 必须能通过 `raw_id` 或 `clean_id` 对齐；无法对齐则停在检查点，勿进阶段 3。

## manifest 字段（每组装一份）

建议列：

`showid, Species, SpeciesCode, assembly, source_hint, genome_path, gff_path, cds_path, pep_path, rna_path, chr_map_path, tools_versions, qc_pass, notes`

另见阶段 2 入口汇总：`resources/preprocess_input_manifest.tsv`（选定的 raw 路径）→ 清洗后写 `clean/.../manifest.tsv`。


## HXC / WGDI 产出命名（步骤 2+）

对接 HXC 后，阶段 2 主产出改为：

```text
clean_v2/s{showid}/{code}.gene_map.tsv
clean_v2/s{showid}/{code}.chr_map.tsv
clean_v2/s{showid}/{code}.rejected.tsv
analysis_v2/s{showid}/{code}.cds
analysis_v2/s{showid}/{code}.pep
analysis_v2/s{showid}/{code}.new.gff
analysis_v2/s{showid}/{code}.lens
```

其中 `{code}` = `s{showid}`。WGDI 四件套必须成套使用（见 vendor `references/wgdi-input-contract.md`）。历史手工约定的 `clean/{SpeciesCode}/` 仍可作为可选并行布局，**2→3 出口以 analysis_v2 + validate 为准**。
