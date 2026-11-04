---
name: 植物基因组数据预处理
description: >-
  当阶段1资源已下载、要通过1→2分界进入清洗与标准化（统一染色体名、整理/提取
  genome·gff·cds·pep、建索引与对照表）时使用；当前为骨架，脚本待补。
---
# 植物基因组数据预处理

## 在总流程中的位置

本 skill = [植物基因组比较分析总流程](sand-workflow:skill-1793405456014) 的 **阶段 2**。

| 分界 | 含义 |
|------|------|
| **入口 1→2** | 阶段1完成：版本/链接表齐全；目标种有所需类型（或已记缺失）；inventory 已刷新 |
| **阶段内** | 校验 raw → 统一命名 → 清洗/提取 CDS·pep → 染色体对照 → 粗质检（下文骨架） |
| **出口 2→3** | `clean/` 下各物种命名统一的 genome/gff/cds/pep；染色体/scaffold 对照表齐 → 回总流程过关后进同源基因鉴定 |

## 本 skill 目录

```text
（本 skill）/
├── SKILL.md                 # 必须；步骤与检查点
├── scripts/                 # 暂空，待补可运行脚本
├── references/              # 需要时再读
│   ├── naming-conventions.md
│   └── qc-checklist.md
└── assets/                  # 预留
```

建议工作目录：`clean/`（raw 来自阶段1，如 `plant-genome-resources/data/downloads/` 或项目 `raw/`）。

## 步骤骨架（脚本待补）

1. **盘点 raw**：按物种列出已有 gff/gtf/gbff/cds/pep/rna/genome；缺项记入清单，不强行编造。
2. **统一物种与文件命名**：学名缩写/固定代码 + 组装版本写进路径或清单（细则见 `references/naming-conventions.md`）。
3. **注释与序列对齐**：染色体/scaffold ID 与 genome 一致；必要时建 `chr_map.tsv`。
4. **整理或提取 CDS / pep**：已有 cds/pep 则校验与 gff 基因 ID 对应；仅有 gff+genome 时再提取（工具选型待定：gffread / AGAT 等）。
5. **粗质检**：空文件、异常字符、CDS 非 3 倍数占比、pep 与 cds 条数严重不符等 → 见 `references/qc-checklist.md`。
6. **写出 `clean/`**：每物种标准化 `*.genome.fa` / `*.gff3` / `*.cds.fa` / `*.pep.fa` + 对照表；记录所用软件版本。

## 待补（占位）

- [ ] `scripts/` 可运行脚本与依赖
- [ ] 默认工具栈（seqkit / AGAT / gffread / biopython 等）与版本
- [ ] 从 gbff 抽注释/序列的规则
- [ ] 多组装版本并存时的选择规则

完成后按 **2→3** 回到总流程。
