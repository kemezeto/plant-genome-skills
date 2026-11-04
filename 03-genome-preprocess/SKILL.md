---
name: 植物基因组数据预处理
description: >-
  当阶段1资源已下载、要通过1→2分界做异源格式归类汇总，再经 step0/1 选定 canonical，并用 bridge 对接上游 WGDI
  预处理流水线写出 clean_v2/analysis_v2 WGDI 四件套与 chr_map/gene_map、过 validate 后进入阶段3时使用。
---
# 植物基因组数据预处理

## 1. 在总流程中的位置

本 skill = [植物基因组比较分析总流程](sand-workflow:skill-1793405456014) 的 **阶段 2**。

| 分界 | 含义 |
|------|------|
| **入口 1→2** | 阶段1完成：版本/链接表齐全；目标种有所需类型（或已记缺失）；`download_inventory.tsv` 已刷新。下载物可来自多站点、格式杂乱——**先归类汇总，再清洗**。 |
| **阶段内** | 步骤0 归类 → 步骤1 选 canonical → **步骤2 bridge + WGDI 预处理** 标准化为 WGDI bundle |
| **出口 2→3** | `analysis_v2/s{id}/` WGDI 四件套（cds/pep/new.gff/lens）+ `clean_v2` 的 chr_map/gene_map 过上游 validate；summary `status=OK` → 回总流程进 BLAST |

下载与文件夹规范见阶段1 skill（`skill-1793405308920`）。**不要**在本阶段 `--yes` 真下载大文件。  
上游对接细节：`references/wgdi-preprocess-integration.md`。

## 2. 目录结构

```text
（本 skill）/
├── SKILL.md
├── scripts/
│   ├── classify_local.py
│   ├── step0_classify_raw.py
│   ├── step0_summarize_raw.py
│   ├── step1_select_canonical.py
│   ├── step2_sync_inventory_from_manifest.py
│   ├── step2_prepare_wgdi_inputs.py
│   └── run_wgdi_preprocess.sh
├── references/
│   ├── raw-classify.md
│   ├── preprocess-layout.md
│   ├── naming-conventions.md
│   ├── qc-checklist.md
│   └── wgdi-preprocess-integration.md
└── assets/

工作区（示例）plant-genome-resources/
├── data/downloads/{showid}_{Order}_{Family}({Species})/
├── resources/   # catalog / matrix / manifest / inventory / preprocess summary
├── clean_v2/    # 上游映射与拒因
├── analysis_v2/ # WGDI 四件套
└── scripts/preprocess/   # 本 skill 脚本副本

Vendor（只读对待源码）:
  /workspace/vendor/plant-genome-wgdi-preprocess
  # 上游仓 URL: https://github.com/HXC-code/hxc-plant-genome-preprocess
```

细节见 `references/preprocess-layout.md`。

## 3. 步骤 0：异源资源归类汇总

对每个物种文件夹扫描文件（跳过隐藏文件与 `*.partial`），写出逐文件明细，并汇总 format 多样性。

工作目录：

```bash
cd /workspace/plant-genome-resources
SK=/home/box/agent-data/workflows/skill-1793419436579/scripts
# 或使用副本：SK=scripts/preprocess
```

```bash
python3 "$SK/step0_classify_raw.py" \
  --downloads-dir data/downloads \
  --links resources/assembly_download_links.tsv \
  -o resources/raw_file_catalog.tsv

python3 "$SK/step0_summarize_raw.py" \
  -i resources/raw_file_catalog.tsv \
  --matrix resources/raw_type_matrix.tsv \
  --summary resources/raw_classify_summary.md \
  --stats-tsv resources/raw_classify_stats.tsv
```

**产出列（catalog）**：`showid, Order, Family, Species, folder, filename, file_type, format, compression, size_bytes, size_mb, source_hint, notes`

对照表与优先级：`references/raw-classify.md`。

## 4. 步骤 1：选定 canonical 输入 manifest

```bash
python3 "$SK/step1_select_canonical.py" \
  -i resources/raw_file_catalog.tsv \
  --downloads-dir data/downloads \
  -o resources/preprocess_input_manifest.tsv
```

产出：`resources/preprocess_input_manifest.tsv`  
列：`showid, Species, file_type, chosen_path, format, compression, size_bytes, source_hint, rejected_alts, notes`

混合压缩包（`other_*_tar`）不会自动入选；需人工解包后再跑步骤 0。

## 5. 步骤 2：Bridge + WGDI 预处理标准化

上游流水线读取固定路径 `resources/download_inventory.tsv`（每列**单个** basename）与 `data/downloads/…`，要求 gff/cds/pep 文件名共享同一 `GCA_/GCF_\d+.\d+_` 前缀。

### 5.1 同步 inventory（manifest → basename）

```bash
python3 "$SK/step2_sync_inventory_from_manifest.py" --project-root .
# 写出 resources/preprocess_bridge_log.tsv；打印具备 gff+cds+pep 三角的物种数
```

规则摘要：按 showid 写入 gff/gtf/cds/pep/gbff/genome/rna 的 basename；**gff 优先 gff，仅有 gtf 时写入 gff 列并 WARNING**；保留其它行/列；缺行则从文件夹名补。

### 5.2 Accession 适配（不改 raw 语义）

```bash
python3 "$SK/step2_prepare_wgdi_inputs.py" --project-root . [--species ID]
```

对三角齐全但缺统一 accession 的物种：在同目录硬链 `GCA_…_<原名>`（或占位 `GCA_000000000.0_`），更新 inventory 指向别名；备份 `download_inventory.pre_wgdi.tsv`；旁路 `wgdi_run_inventory.tsv` / `wgdi_accession_alias_log.tsv`。别名可删，原文件保留。

### 5.3 一键包装（推荐）

```bash
bash "$SK/run_wgdi_preprocess.sh" . \
  --sync-inventory \
  --prepare-accession \
  --species 900 \
  --expected-count 1
```

等价于先可选 sync/prepare，再调用  
`/workspace/vendor/plant-genome-wgdi-preprocess/scripts/run_pipeline.sh`。  
环境变量 `WGDI_PREPROCESS_ROOT` 可改 vendor 路径；默认 `PYTHON=python3`。

### 5.4 产出与 2→3 出口

| 路径 | 内容 |
|------|------|
| `clean_v2/s{id}/` | `{code}.gene_map.tsv` / `.chr_map.tsv` / `.rejected.tsv` |
| `analysis_v2/s{id}/` | `{code}.cds` `.pep` `.new.gff` `.lens` + `.qc.json` |
| `resources/stage_preprocess_v2_summary.tsv` | 每物种 status/reason |
| `resources/wgdi_v2_index.tsv` | WGDI 就绪索引 |

**出口**：四件套成套 + chr_map/gene_map 过 validate（`[PASS]`）；勿混用过滤前后文件。契约见 vendor `references/wgdi-input-contract.md`。

### 5.5 DEMO

工作区含 fixture 物种 **showid=900**（`Demo plantus`，文件名带 `GCA_900000001.1_`）。最小 GFF3 + cds + pep，可：

```bash
cd /workspace/plant-genome-resources
bash scripts/preprocess/run_wgdi_preprocess.sh . --species 900 --expected-count 1
```

## 6. 检查点与停机条件

**可继续**：catalog/matrix 已生成；canonical manifest 无「唯一选择却 empty」的关键类型；目标种 preprocess summary `OK` 且 validate PASS。

**停机**：

- 关键物种无 gff+cds+pep 三角且下游需要 → 回阶段1补齐；**本 bridge 不自动 gffread 提取**
- `accession_mismatch` → 跑 `--prepare-accession`
- QC / 上游流水线：空文件、多核 taxon、无有效代表基因、validate 失败（见 `qc-checklist.md`、`wgdi-preprocess-integration.md`）
- 唯一候选为 `over_300mb` 且未获「强制纳入」说明

## 7. 与阶段1 / vendor 的衔接

- 文件夹名：`{showid}_{Order}_{Family}({Species})`，与 `step3_common.parse_folder_name` 一致。
- `scripts/classify_local.py` 为阶段1 分类内联副本；规则变更需两边同步。
- **不要删除或改坏阶段1脚本**；本 skill 副本在 `scripts/preprocess/`。
- **不要改 vendor 源码做永久 fork**；可 `git pull`。适配只在本 skill bridge。
- 阶段1 inventory 刷新仍用：`python3 scripts/step3_stats.py`。

完成后按 **2→3** 回到总流程（BLAST 输入 = `analysis_v2` WGDI bundle）。
