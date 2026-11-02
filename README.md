# plant-genome-skills

公开可复用的植物基因组比较分析 Skill 包（Grok Bot / Cursor skill 格式：`SKILL.md` + 可选 `scripts/` / `references/` / `assets/`）。

## 结构

| 目录 | 对应阶段 | 说明 |
|------|----------|------|
| [01-plant-genome-compare-framework](01-plant-genome-compare-framework/) | 总框架 0–6 | 阶段顺序、分界点、子 skill 挂接 |
| [02-omics-resource-download](02-omics-resource-download/) | 阶段 1 | 预下载列表 → 解析链接 → 下载/人工补货/统计 |
| [03-genome-preprocess](03-genome-preprocess/) | 阶段 2 | 预处理骨架（脚本暂空） |

原始 skill id（本机 workflows 文件夹名）：

- 框架：`skill-1793405456014`
- 下载：`skill-1793405308920`
- 预处理：`skill-1793419436579`

## 使用

1. 把某一目录整份拷进助手的 skills / workflows，或按你的 Bot 文档导入 `SKILL.md`。
2. 阶段 1 脚本在 `02-omics-resource-download/scripts/`；工作数据仍放在你自己的项目目录（例如 `resources/` + `data/downloads/`），不要把大基因组文件提交进本仓库。
3. 改流程先改 `01-…` 的分界表，再改对应子 skill。

## 许可

未另声明时，文档与脚本按仓库默认许可使用；下游分析结论不构成医疗建议。
