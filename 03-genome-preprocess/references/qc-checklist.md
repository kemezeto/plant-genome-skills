# 预处理粗质检清单

过关才宣称阶段 2 完成（对应总流程 **2→3**）。下列为可勾选项 + 建议阈值；脚本未自动跑时人工抽查。

## 文件存在与命名

- [ ] 目标种具备下游所需：至少 `cds` 或 `pep`；做共线性时还要 `gff`（+ 可对齐的 `genome`）
- [ ] `clean/{SpeciesCode}/{assembly}/` 命名符合 `naming-conventions.md`
- [ ] 无空文件（`size_bytes == 0`）；catalog 里 `empty_file` 不得入选为唯一 canonical（除非注明跳过该种）
- [ ] `over_300mb` / `skipped_size` 文件默认不进清洗；若必须用，在 notes 明示

## 序列与注释一致性

- [ ] genome 与 gff 的序列 ID 可对齐，或已有完整 `chr_map.tsv`
- [ ] fasta 头无异常空白、控制字符；**无重复 ID**（`seqkit rmdup -n` 或等价检查应为空）
- [ ] gff/gtf 必要列齐全；基因/转录本 ID 无大面积缺失

## CDS / pep 数量与可读框

建议阈值（可按项目收紧）：

| 检查 | 建议阈值 | 动作 |
|------|----------|------|
| 空文件 / 不可读 | 任一关键文件 size=0 或解析失败 | 停机，该种不进 2→3 |
| 重复 fasta ID | >0 | 去重或修正后再过 |
| CDS 长度非 3 倍数 | 占比 **> 5%** 记警告；**> 20%** 停机复查提取参数 | 检查 gffread/AGAT 与相位 |
| pep 条数 / cds 条数 | 比 **< 0.5 或 > 2.0** | 停机核对是否混入异构体/错误文件 |
| pep 条数 / gff gene 数 | 比 **< 0.3 或 > 5**（若有 gene 统计） | 警告或停机 |
| 异常字符 | DNA 非 ACGTN；蛋白非标准字母占比高 | 警告 |

## 流程与元数据

- [ ] `preprocess_input_manifest.tsv` 与最终 `clean/.../manifest.tsv` 路径一致或可追溯
- [ ] 所用工具与版本已写入 manifest（如 `gffread 0.12.7; seqkit 2.x`）
- [ ] 缺类型物种已记入 summary「missing primary types」，不强行编造序列

## 抽检命令示例（可选）

```bash
# 重复 ID
seqkit rmdup -n -d dup.fa clean/Abedis/ASM1/Abedis.cds.fa && test ! -s dup.fa

# CDS %3（粗：长度模 3；正式可用自定义脚本）
seqkit fx2tab -n -l clean/Abedis/ASM1/Abedis.cds.fa | awk '$2%3!=0{c++} END{print c+0}'
```


## 上游 validate（步骤 2+ 硬门）

对接上游 WGDI 预处理后，粗质检以管道自带 validate 为准：

- [ ] `resources/stage_preprocess_v2_summary.tsv` 目标种 `status=OK`
- [ ] `resources/wgdi_v2_index.tsv` 对应行 `wgdi_ready=yes`
- [ ] `bash …/run_wgdi_preprocess.sh . --species ID --expected-count N` 打印 `[PASS]`
- [ ] 四件套与 `gene_map`/`chr_map` 路径可读；勿混用过滤前后文件

契约与拒因：vendor `references/validation-rules.md`；常见 FAIL 见本目录 `wgdi-preprocess-integration.md`。
