---
name: 植物组学资源检索与下载
description: >-
  当用户给出植物基因组资源表并需要物种去重预下载列表、解析/补救下载链接、按 show_id 建目录并筛选下载
  gff/genome/cds/pep/rna/gbff/gtf（可重试与并发）、再按文件夹统计清单时使用。
---
# 植物组学资源检索与下载

## 在总流程中的位置

本 skill = [植物基因组比较分析总流程](sand-workflow:skill-1793405456014) 的 **阶段 1**。

| 分界 | 含义 |
|------|------|
| **入口 0→1** | 总流程已定物种表、科学问题、需要的文件类型（cds/gff/pep…）后才开跑 |
| **阶段内** | 步骤 1 预下载列表 → 2 解析链接 → 3 建目录/下载/统计（下文） |
| **出口 1→2** | `resources` 版本/链接表齐全；目标种目录有所需类型（或已记缺失）；已跑 `step3_stats.py` 刷新 inventory → 回到总流程过关后再进预处理 |

分界细则见总流程 `references/phase-checklist.md`。

## 本 skill 目录

```text
skill-1793405308920/
├── SKILL.md
├── scripts/              # step1–3 与 classify/domain
├── references/           # step3.md、project-data-layout.md
└── assets/
```

工作数据默认 `/workspace/plant-genome-resources`。脚本用本目录 `scripts/`（可拷到工作区再跑）。

## 步骤 1：预下载列表

```bash
python3 scripts/step1_predownload_list.py -i resources/raw_table.csv -o resources/predownload_list.tsv
```

按标准化 Species 去重（非 show_id）；`species_rank`：靠近当前年 → 年份更新 → show_id 更小。输出列：`show_id, Species, Ploidy, Order, Family, Genome assembly`。

## 步骤 2：解析链接

```bash
python3 scripts/step2_parse_assembly_links.py -i resources/predownload_list.tsv -o resources/assembly_download_links.tsv
# 整表重爬：加 --no-resume
```

none 补救：`scripts/domain_handlers.py` + `scripts/step2_recover_none.py`；重标：`scripts/step2_reclassify_links.py`。

## 步骤 3：建目录 / 下载 / 统计

```bash
python3 scripts/step3_mkdirs.py
python3 scripts/step3_download.py              # 默认 dry-run
python3 scripts/step3_download.py --yes        # 真实下载
python3 scripts/step3_download.py --yes -j 4   # 4 并发
python3 scripts/step3_stats.py                 # 只扫文件夹 → 刷新 inventory
```

1. 目录：`data/downloads/{show_id}_{Order}_{Family}({Species})`
2. 只下 `gff/genome/cds/pep/rna/gbff/gtf`；**>300 MiB 跳过**（`--max-mb` 可改）
3. **重试**：`--retries` 默认 **2**；`--backoff` 默认 1.5s；对 `error:*`、HTTP 408/429/5xx 重试
4. **并发**：`-j` / `--workers` 默认 **1**；实用 **2–4**；钳制 1–8
5. `resources/download_inventory.tsv` 只依赖当前文件夹内容

### 人工下载提示

脚本拿不到或只标成 `none` 时，优先人工补货：

1. **优先物种**：`resources/species_no_download_links.tsv` 以及链接表里 `file_type=none` 的物种（门户解析失败/无直链）
2. **优先文件类型**（名称含近似词即可认）：
   - `gff` / `gtf`（基因组注释：gff3、annotation 等）
   - `gbff`（GenBank flat file）
   - `cds`
   - `pep`（Protein / protein / aa / peptide 等近似词）
   - `rna` / `mrna`
   - （有余力再补 `genome` 组装序列）
3. **体积**：单文件 **>300 MiB 可跳过**（与脚本 `--max-mb` 默认一致）
4. 文件放进对应物种目录后，**必须重跑** `python3 scripts/step3_stats.py` 刷新 inventory

详见 `references/step3.md`。完成后按 **1→2** 回到总流程。
