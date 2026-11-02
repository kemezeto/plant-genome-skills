# plant-genome-skills

公开可复用的植物基因组比较分析 Skill 包（Grok Bot / Cursor skill 格式：`SKILL.md` + 可选 `scripts/` / `references/` / `assets/`）。

## 结构

| 目录 | 对应阶段 | 说明 |
|------|----------|------|
| [01-plant-genome-compare-framework](01-plant-genome-compare-framework/) | 总框架 0–6 | 阶段顺序、分界点、子 skill 挂接 |
| [02-omics-resource-download](02-omics-resource-download/) | 阶段 1 | 预下载列表 → 解析链接 → 下载/人工补货/统计 |
| [03-genome-preprocess](03-genome-preprocess/) | 阶段 2 | 预处理骨架（脚本暂空） |
| [resources](resources/) | 源表与中间表 | 步骤 1 输入与解析结果，见下 |

原始 skill id（本机 workflows 文件夹名）：

- 框架：`skill-1793405456014`
- 下载：`skill-1793405308920`
- 预处理：`skill-1793419436579`

## 使用

1. 把某一目录整份拷进助手的 skills / workflows，或按你的 Bot 文档导入 `SKILL.md`。
2. 阶段 1 脚本在 `02-omics-resource-download/scripts/`，读写仓库里的 `resources/` 表。基因组大文件放在本机 `data/downloads/`，不要提交进本仓库。
3. 改流程先改 `01-…` 的分界表，再改对应子 skill。

## 资源表

源表与中间表在 [resources/](resources/)（说明同 [resources/README.md](resources/README.md)）。不含 `data/downloads/` 基因组大文件。

| 文件 | 说明 |
|------|------|
| [`raw_table.csv`](resources/raw_table.csv) | 原始物种/组装资源表（步骤1输入） |
| [`predownload_list.tsv`](resources/predownload_list.tsv) | 物种去重后的预下载列表 |
| [`assembly_download_links.tsv`](resources/assembly_download_links.tsv) | 解析出的下载链接（含 file_type） |
| [`species_no_download_links.tsv`](resources/species_no_download_links.tsv) | 仅有 none / 无可用直链的物种 |
| [`download_inventory.tsv`](resources/download_inventory.tsv) | 按文件夹扫描的清单（可随本机下载更新） |
| [`STEP3_README.md`](resources/STEP3_README.md) | 步骤3说明 |

## 许可

未另声明时，文档与脚本按仓库默认许可使用；下游分析结论不构成医疗建议。
