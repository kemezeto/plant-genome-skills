# resources（源表与中间表）

| 文件 | 说明 |
|------|------|
| `raw_table.csv` | 原始物种/组装资源表（步骤1输入） |
| `predownload_list.tsv` | 物种去重后的预下载列表 |
| `assembly_download_links.tsv` | 解析出的下载链接（含 file_type） |
| `species_no_download_links.tsv` | 仅有 none / 无可用直链的物种 |
| `download_inventory.tsv` | 按文件夹扫描的清单（可随本机下载更新） |
| `STEP3_README.md` | 步骤3说明 |

不含 `data/downloads/` 基因组大文件。
