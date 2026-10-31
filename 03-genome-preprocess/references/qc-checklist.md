# 预处理粗质检（骨架）

过关才宣称阶段 2 完成（对应总流程 2→3）：

- [ ] 每目标种至少具备下游所需的 cds 或 pep（及 gff 位置信息，若做共线性）
- [ ] genome 与 gff 序列 ID 可对齐（或已有 chr_map）
- [ ] 无空文件；主要 fasta 头无异常空白/重复 ID
- [ ] cds/pep 条数与注释基因数无数量级偏差（规则数值待定）
- [ ] `clean/` 命名符合 naming-conventions；软件版本已记录
