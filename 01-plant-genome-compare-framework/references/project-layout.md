# 全局项目目录约定

```text
project/
├── raw/        # 阶段1：原始下载（可对应 plant-genome-resources/data/downloads）
├── clean/      # 阶段2：标准化 genome/gff/cds/pep + 命名对照
├── blast/      # 阶段3：同源搜索与过滤结果
├── synteny/    # 阶段4：共线性区块与图
├── tree/       # 阶段5：比对、树、支持率
└── wgd/        # 阶段6：Ks/加倍推断与加倍共线性
```

阶段间只通过「上一阶段出口目录/表 + 分界检查表」交接，禁止混用未记录版本的组装。
