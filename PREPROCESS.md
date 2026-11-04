# 阶段2 预处理操作卡（中文）

工作根：`/workspace/plant-genome-resources`  
Skill：`/home/box/agent-data/workflows/skill-1793419436579`  
上游 WGDI 预处理 vendor：`/workspace/vendor/plant-genome-wgdi-preprocess`  
上游仓：`https://github.com/HXC-code/hxc-plant-genome-preprocess`

## 三连（日常）

```bash
cd /workspace/plant-genome-resources
# 1) 归类 + 选 canonical（有新下载时）
python3 scripts/preprocess/step0_classify_raw.py \
  --downloads-dir data/downloads \
  --links resources/assembly_download_links.tsv \
  -o resources/raw_file_catalog.tsv
python3 scripts/preprocess/step0_summarize_raw.py \
  -i resources/raw_file_catalog.tsv \
  --matrix resources/raw_type_matrix.tsv \
  --summary resources/raw_classify_summary.md \
  --stats-tsv resources/raw_classify_stats.tsv
python3 scripts/preprocess/step1_select_canonical.py \
  -i resources/raw_file_catalog.tsv \
  --downloads-dir data/downloads \
  -o resources/preprocess_input_manifest.tsv

# 2) bridge + WGDI 预处理（把 ID / 期望种数换成你的）
bash scripts/preprocess/run_wgdi_preprocess.sh . \
  --sync-inventory --prepare-accession \
  --species 900 --expected-count 1

# 3) 看结果
# analysis_v2/s900/ 四件套；clean_v2/s900/ 映射；
# resources/stage_preprocess_v2_summary.tsv → status=OK
```

## 注意

- inventory 的 gff/cds/pep **每列一个文件名**，不要 `|` 拼接。
- 缺统一 `GCA_/GCF_` 前缀时靠 `--prepare-accession` 硬链别名；**勿删 raw**。
- 仅三角齐全（gff+cds+pep）可跑；不会自动从 genome 抽 CDS。
- DEMO：`showid=900` 已可过上游流水线。

更多：`skill …/references/wgdi-preprocess-integration.md`。
