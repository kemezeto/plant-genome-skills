# plant-genome-skills

公开可复用的植物基因组比较分析 Skill 包（Grok Bot / Cursor skill 格式：`SKILL.md` + 可选 `scripts/` / `references/` / `assets/`）。

## 结构

| 目录 | 对应阶段 | 说明 |
|------|----------|------|
| [01-plant-genome-compare-framework](01-plant-genome-compare-framework/) | 总框架 0–6 | 阶段顺序、分界点、子 skill 挂接 |
| [02-omics-resource-download](02-omics-resource-download/) | 阶段 1 | 预下载列表 → 解析链接 → 下载/人工补货/统计 |
| [03-genome-preprocess](03-genome-preprocess/) | 阶段 2 | 异源归类 → canonical → bridge，对接外部 HXC 预处理 |
| [resources](resources/) | 源表与中间表 | 步骤 1 输入与解析结果，见下 |

原始 skill id（本机 workflows 文件夹名）：

- 框架：`skill-1793405456014`
- 下载：`skill-1793405308920`
- 预处理：`skill-1793419436579`

## 使用

1. 把某一目录整份拷进助手的 skills / workflows，或按你的 Bot 文档导入 `SKILL.md`。
2. 阶段 1 脚本在 `02-omics-resource-download/scripts/`，读写仓库里的 `resources/` 表。阶段 2 脚本在 `03-genome-preprocess/scripts/`。基因组大文件放在本机 `data/downloads/`，不要提交进本仓库。
3. 改流程先改 `01-…` 的分界表，再改对应子 skill。

## 阶段 2 预处理（已对接 HXC）

`03-genome-preprocess/` 已从骨架补全：步骤 0/1 做异源格式归类与 canonical 选择，步骤 2 用 bridge 把 manifest 接到外部仓库 [hxc-plant-genome-preprocess](https://github.com/HXC-code/hxc-plant-genome-preprocess)，写出 `clean_v2/` 与 `analysis_v2/`（WGDI 四件套）。日常操作卡见根目录 [`PREPROCESS.md`](PREPROCESS.md)。

HXC 本体请单独 clone 为 vendor，**不要**把该仓库整份拷进本仓库：

```bash
git clone https://github.com/HXC-code/hxc-plant-genome-preprocess.git /path/to/vendor/hxc-plant-genome-preprocess
export HXC_ROOT=/path/to/vendor/hxc-plant-genome-preprocess
```

本 skills 仓库不含 DEMO `showid=900` 的数据文件；该样例留在工作区或 HXC 测试中，不入库。

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
