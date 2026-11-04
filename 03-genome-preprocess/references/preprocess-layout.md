# 预处理目录与交接文件

```text
plant-genome-resources/          # 建议工作根目录
├── data/
│   └── downloads/               # 阶段1 raw（只读对待；可有 HXC 硬链别名）
│       └── {showid}_{Order}_{Family}({Species})/
├── resources/
│   ├── assembly_download_links.tsv   # 阶段1；步骤0 用来猜 source_hint
│   ├── download_inventory.tsv        # 阶段1 + bridge 写入 gff/cds/pep basename
│   ├── download_inventory.pre_hxc.tsv# prepare 首次改写前备份
│   ├── raw_file_catalog.tsv          # 步骤0 明细
│   ├── raw_type_matrix.tsv           # 步骤0 物种×类型
│   ├── raw_classify_summary.md       # 步骤0 统计
│   ├── raw_classify_stats.tsv        # 步骤0 计数表
│   ├── preprocess_input_manifest.tsv # 步骤1 canonical 路径
│   ├── preprocess_bridge_log.tsv     # sync 旁路日志
│   ├── hxc_run_inventory.tsv         # prepare 旁路：三角齐全种
│   ├── hxc_accession_alias_log.tsv   # prepare 别名日志
│   ├── stage_preprocess_v2_summary.tsv
│   ├── wgdi_v2_index.tsv
│   └── wgdi_v2_manifest_sha256.tsv
├── clean_v2/s{showid}/          # HXC：gene_map / chr_map / rejected
├── analysis_v2/s{showid}/       # HXC：WGDI 四件套 + qc
└── scripts/
    ├── …阶段1…
    └── preprocess/              # 本 skill 脚本副本
```

## 数据流

```text
downloads/  --step0_classify-->  raw_file_catalog.tsv
                --step0_summarize--> raw_type_matrix.tsv + summary
                --step1_select--> preprocess_input_manifest.tsv
                --step2_sync--> download_inventory.tsv (单文件 basename)
                --step2_prepare--> GCA_/GCF_ 硬链别名（按需）
                --HXC run_pipeline--> clean_v2/ + analysis_v2/
```

## 交接约定

| 方向 | 条件 |
|------|------|
| **1→2** | inventory 已刷新；目标种所需类型有文件或已记缺失；**先跑步骤 0–1** 得到 catalog/manifest |
| **2→3** | `analysis_v2` WGDI 四件套 + `clean_v2` 的 chr_map/gene_map 过 HXC validate；summary 为 OK |

对接细节见 `hxc-integration.md`。不要把 raw 直接改名冒充产物；也不要在未归类时批量解压超大档案。
