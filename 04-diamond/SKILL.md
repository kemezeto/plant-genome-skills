---
name: 蛋白同源搜索（DIAMOND 自比 / 种间比对）
description: >-
  当需要在同一物种内（旁系同源、WGD 前置）或指定基准物种与其他物种之间做全对全蛋白比对，
  并产出下游共线性工具可直接使用的 outfmt 6 命中表时使用；包含 pep 放置规范、单物种 /
  批量自比、基准物种间比对三套脚本与产物约定。
---
# 蛋白同源搜索（DIAMOND）

## 1. 定位

本目录对应总流程的**阶段 3（同源基因鉴定）**的比对环节。输入是阶段 2 产出的
`analysis_v2/*.pep`（每基因一条代表转录本、canonical ID），输出是 12 列 outfmt 6 命中表，
供阶段 4 的共线性工具（WGDI `-icl`）直接读取。

两种用法：

| 场景 | 用途 | 脚本 |
|------|------|------|
| 一个物种自己跟自己比 | 找旁系同源，做种内共线性 / WGD | `run_self_diamond.sh`（单个）、`run_batch_self_diamond.sh`（批量） |
| 基准物种 vs 其他物种 | 找直系同源，做种间共线性 | `run_compare_diamond.sh` |

**只做蛋白比对**，不需要装 BLAST（DIAMOND 的 `blastp` 覆盖该场景；仅 `blastn` 才必须用 BLAST+）。

## 2. 目录一览

```text
04-diamond/
├── SKILL.md                      本文件
├── data/                         ★ 放物种 pep 的地方（每个物种一个文件）
│   ├── Vvi.pep                   文件名即物种缩写
│   └── Car.pep
├── scripts/
│   ├── run_self_diamond.sh       单物种自比（一个物种 → 一个目录）
│   ├── run_batch_self_diamond.sh 批量自比（data/ 下所有物种各跑各的，互不比较）
│   └── run_compare_diamond.sh    基准物种 vs 其他物种（每个物种对一个目录）
├── self_diamod/                  自比结果，按 {缩写}_{时间}/ 分目录
│   ├── Vvi_20261108-1153/
│   └── Car_20261108-1153/
└── compare_diamod/               种间比对结果，按 {基准}-{比对}-{时间}/ 分目录
    └── Vvi-Car-20261108-1157/
```

| 文件夹 | 作用 | 谁写入 |
|--------|------|--------|
| `data/` | 物种蛋白序列输入 | 人（从阶段 2 拷入） |
| `scripts/` | 三个可执行脚本 | 仓库 |
| `self_diamod/` | 自比产物，一个物种一个子目录 | 脚本自动创建 |
| `compare_diamod/` | 种间比对产物，一个物种对一个子目录 | 脚本自动创建 |

`data/` 与两个结果目录都可以随时清空重跑，脚本不会读旧结果。

## 3. 准备数据（第一步）

把每个物种的 pep 放进 `data/`，**一物种一个文件，文件名 = 物种缩写**：

```text
data/Vvi.pep     → 缩写 Vvi
data/Car.pep     → 缩写 Car
data/Ath.pep     → 缩写 Ath
```

缩写只影响目录命名和汇总表显示，但**必须唯一**（同名会被当成同一物种）。四条硬要求：

1. **用阶段 2 的 `analysis_v2/*.pep`**，不要用 `data/downloads/` 里的原始 `protein.faa`；
2. 每个基因**只能有一条**代表转录本（多 isoform 会互相抢命中）；
3. 序列 ID **文件内唯一**，且与 `.cds` / `.new.gff` 一致（`s9001g0001` 这种 canonical ID 最稳）；
4. 去掉序列末尾的 `*`（阶段 2 的 pep 已处理）。

放好后自查：

```bash
for f in data/*.pep; do
  echo "$f  序列=$(grep -c '^>' "$f")  重复ID=$(grep '^>' "$f" | awk '{print $1}' | sort | uniq -d | wc -l)"
done
```

重复 ID 必须是 0，否则自比会出现多余的对角命中（脚本会警告，但不会自动修）。

## 4. 环境

```bash
diamond version        # 需要 2.2.x；本机已装在 ~/bin/diamond.exe（v2.2.8）
```

没有的话：

```bash
# Windows：下载官方 release 的 diamond-windows.zip，diamond.exe 放进 PATH 里的目录
# Linux / 集群：
conda install -c bioconda diamond=2.2.8
```

`.dmnd` 索引**跨版本不保证兼容**，换版本后重新建库即可（几秒）。

## 5. 跑物种自身比对

### 5.1 先拿一个物种试跑

```bash
cd 04-diamond
bash scripts/run_self_diamond.sh -i data/Vvi.pep -o self_diamod/Vvi_test
```

产物（`-o` 目录下只有这三个文件）：

```text
Vvi_test/
├── Vvi.dmnd               索引
├── Vvi.self.blast         outfmt 6 原始结果
└── Vvi.self.uniq.blast    ★ 下游用这个：无对角线、无重复对、无同序列命中
```

常见参数：

```bash
bash scripts/run_self_diamond.sh -i data/Vvi.pep -o self_diamod/Vvi_test \
  -k 0 -e 1e-5 -t 8 --mode more-sensitive   # -k 0 = 不限命中数（推荐，避免截断）
```

`--audit` 可额外保留 5 个审计文件（同序列清单、分组表、统计、参数、日志），默认不落盘。

### 5.2 批量跑 data/ 下所有物种

```bash
bash scripts/run_batch_self_diamond.sh --dry-run     # 先看会跑什么
bash scripts/run_batch_self_diamond.sh -k 0          # 真跑
```

每个物种一个目录，同批次共用一个时间戳：

```text
self_diamod/
├── Car_20261108-1153/
│   ├── Car.dmnd
│   ├── Car.self.blast
│   └── Car.self.uniq.blast
└── Vvi_20261108-1153/
```

**只做自身比自身，物种之间不会互相比较**。要改目录名时间戳用 `--stamp`；重复跑会生成新目录（不覆盖）。

## 6. 跑物种间比对

先设定基准物种——改脚本顶部一行：

```bash
REF="Vvi"        # ← 基准物种缩写
```

或命令行覆盖：`--ref Car`。然后：

```bash
bash scripts/run_compare_diamond.sh --dry-run    # 计划
bash scripts/run_compare_diamond.sh              # 真跑
```

产物按 `{基准}-{比对}-{时间}/` 分目录，**基准物种自身会被排除**：

```text
compare_diamod/
└── Vvi-Car-20261108-1157/
    ├── Car.dmnd             比对物种的索引
    └── Vvi-Car.blast        query=Vvi，subject=Car，12 列
```

方向固定为「基准 → 其他」；要反向（Car 为基准）就 `--ref Car` 再跑一遍。

## 7. 产物与下游对接

命中表是标准 outfmt 6，12 列，无表头：

```text
qseqid  sseqid  pident  length  mismatch  gapopen  qstart  qend  sstart  send  evalue  bitscore
Vvi18g0396  Car7g0429  28.7  512  317  11  1  490  5  490  4.54e-64  216
```

- ID 就是 pep 头里的 canonical ID，必须与 WGDI bundle 的 `.cds` / `.new.gff` 一致，否则共线性空跑；
- 自比用 `.uniq.blast`（每对一行），种间用 `{基准}-{比对}.blast`（本身无重复方向）；
- 进共线性前常再按覆盖度过滤（如 `length ≥ 100 aa` 或 ≥ query 长度 30%），因为 `-k 0` + `1e-5` 会留下短命中。

## 8. 参数速查

| 参数 | 默认 | 说明 |
|------|------|------|
| `-e` | `1e-5` | e-value 阈值（DIAMOND 自身默认是 0.001，脚本已收紧） |
| `-k` | `50` | 每 query 最多报告目标数；**0 = 不限**，自比建议 0 |
| `-t` | 全部核心 | 线程数，集群上务必显式限制 |
| `--mode` | `more-sensitive` | 可选 `sensitive` / `very-sensitive` / `ultra-sensitive` |
| `--comp-stats` | `0` | 关闭组成偏好校正，保留远缘同源 |
| `--audit` | 关 | 保留中间审计文件（仅自比脚本） |
| `--force` | 关 | 目标目录已存在时仍继续 |

## 9. 检查点与常见问题

**跑成功的标志**：目录里 `.dmnd` 非空、`.blast` 行数 > 0、末尾汇总表状态为 `ok`。

| 现象 | 原因 / 处理 |
|------|-------------|
| 提示「N 个 query 命中数正好等于 -k」 | 被截断了，用 `-k 0` 重跑 |
| 输出里有 `A → A` 自身命中 | 没加 `--no-self-hits`；或 pep 里有重复 ID |
| 自比结果不对称 | DIAMOND 启发式所致（约 0.6% 序列对只在单方向），脚本按无序对去重已处理 |
| `cannot stat` / 路径找不到 | Git Bash 下用 `/e/bio/...` 或相对路径；`E:\...` 会被脚本自动转换 |
| `diamond: command not found` | 装好后重开终端，或 `DIAMOND=/path/to/diamond bash ...` |
| 想换 DIAMOND 版本 | 改 `DIAMOND=` 环境变量；旧 `.dmnd` 需重建 |
