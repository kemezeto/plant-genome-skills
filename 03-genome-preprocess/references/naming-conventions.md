# 命名约定（骨架）

- 物种代码：固定学名缩写或项目代码，全流程一致。
- 路径建议：`clean/{SpeciesCode}/{assembly_version}/`
- 文件：`{SpeciesCode}.genome.fa` / `{SpeciesCode}.gff3` / `{SpeciesCode}.cds.fa` / `{SpeciesCode}.pep.fa`
- 染色体对照：`{SpeciesCode}.chr_map.tsv`（列：raw_id → clean_id）
- 组装版本必须写进路径或旁路 `manifest.tsv`，禁止混用未记录版本。
