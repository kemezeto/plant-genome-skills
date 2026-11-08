#!/usr/bin/env bash
# 基准物种 vs 其他物种（不含自身）：每个物种对一个目录，目录名 {基准}-{比对}-{时间}/
#
# 在下面 REF 处改成你要的物种缩写（= data/ 下的文件名去掉扩展名），或命令行 --ref 覆盖。
set -euo pipefail

REF="Vvi"        # ← 基准物种缩写（data/ 下文件名去掉扩展名）；也可用 --ref 覆盖

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"

DIAMOND="${DIAMOND:-diamond}"
DATA_DIR="$PROJECT_DIR/data"
OUT_ROOT="$PROJECT_DIR/compare_diamod"
PATTERN="*.pep"
STAMP="$(date '+%Y%m%d-%H%M')"
EVALUE="1e-5"
MAX_TARGET=50
THREADS="$(nproc 2>/dev/null || echo 4)"
MODE="more-sensitive"
COMP_STATS=0
DRY=0
FORCE=0

usage() {
    sed -n '2,6p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    cat <<'EOF'

Options:
  -r, --ref ABBR        基准物种缩写（默认取脚本顶部 REF 变量）
  -d, --data-dir PATH   输入目录（默认 data/）
  -o, --out-root PATH   结果根目录（默认 compare_diamod/）
      --pattern GLOB    匹配的输入文件（默认 '*.pep'）
      --stamp TEXT      自定义时间戳（默认 年月日-时分）
  -e, --evalue FLOAT    e-value 阈值（默认 1e-5）
  -k, --max-targets N   每 query 最多报告目标数（默认 50；0=不限，会很慢很大）
  -t, --threads N       线程数（默认全部核心）
      --mode MODE       default|sensitive|more-sensitive|very-sensitive|ultra-sensitive
      --comp-stats N    --comp-based-stats（默认 0）
      --dry-run         只打印计划
      --force           目标目录已存在时也继续
  -h, --help            显示本帮助

目录命名：compare_diamod/{基准}-{比对}-{时间}/
  {比对}.dmnd              比对物种的 DIAMOND 索引
  {基准}-{比对}.blast      outfmt 6，query=基准物种，subject=比对物种
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -r|--ref)        REF="$2"; shift 2 ;;
        -d|--data-dir)   DATA_DIR="$2"; shift 2 ;;
        -o|--out-root)   OUT_ROOT="$2"; shift 2 ;;
        --pattern)       PATTERN="$2"; shift 2 ;;
        --stamp)         STAMP="$2"; shift 2 ;;
        -e|--evalue)     EVALUE="$2"; shift 2 ;;
        -k|--max-targets) MAX_TARGET="$2"; shift 2 ;;
        -t|--threads)    THREADS="$2"; shift 2 ;;
        --mode)          MODE="$2"; shift 2 ;;
        --comp-stats)    COMP_STATS="$2"; shift 2 ;;
        --dry-run)       DRY=1; shift ;;
        --force)         FORCE=1; shift ;;
        -h|--help)       usage; exit 0 ;;
        *) echo "未知参数: $1（-h 看帮助）" >&2; exit 2 ;;
    esac
done

case "$MODE" in
    default) MODE_FLAG="" ;;
    sensitive|more-sensitive|very-sensitive|ultra-sensitive) MODE_FLAG="--$MODE" ;;
    *) echo "不支持的 --mode: $MODE" >&2; exit 2 ;;
esac

[[ -n "$REF" ]] || { echo "未指定基准物种：改脚本顶部 REF= 或用 --ref" >&2; exit 2; }
REF="${REF%.*}"                       # 允许写成 Vvi.pep
command -v "$DIAMOND" >/dev/null || { echo "找不到 diamond" >&2; exit 2; }
[[ -d "$DATA_DIR" ]] || { echo "输入目录不存在: $DATA_DIR" >&2; exit 2; }

REF_FILE="$DATA_DIR/$REF.pep"
[[ -f "$REF_FILE" ]] || { echo "基准物种文件不存在: $REF_FILE" >&2; exit 2; }

shopt -s nullglob
mapfile -t ALL < <(printf '%s\n' "$DATA_DIR"/$PATTERN | sort)
shopt -u nullglob
OTHERS=()
for f in ${ALL[@]+"${ALL[@]}"}; do
    [[ -z "$f" || ! -f "$f" ]] && continue
    abbr="$(basename "$f")"; abbr="${abbr%.*}"
    [[ "$abbr" == "$REF" ]] && continue
    OTHERS+=("$f")
done
[[ ${#OTHERS[@]} -gt 0 ]] || { echo "除 $REF 外没有别的物种" >&2; exit 2; }

echo "基准物种 : $REF（$(grep -c '^>' "$REF_FILE") 条序列）"
echo "比对物种 : ${#OTHERS[@]} 个"
echo "结果目录 : $OUT_ROOT"
echo "时间戳   : $STAMP"
echo "参数     : -e $EVALUE  -k $MAX_TARGET  mode=$MODE  threads=$THREADS"
echo "------------------------------------------------------------"

ok=0; skipped=0; failed=0
declare -a REPORT=()

for f in "${OTHERS[@]}"; do
    other="$(basename "$f")"; other="${other%.*}"
    target="$OUT_ROOT/${REF}-${other}-${STAMP}"
    db="$target/${other}.dmnd"
    out="$target/${REF}-${other}.blast"
    seqs="$(grep -c '^>' "$f" || true)"

    if [[ -e "$target" && $FORCE -eq 0 ]]; then
        echo "[skip ] ${REF}-${other}（已存在，加 --force 覆盖）"
        skipped=$((skipped + 1))
        REPORT+=("${REF}-${other}	$seqs	-	-	skipped")
        continue
    fi
    if [[ $DRY -eq 1 ]]; then
        echo "[plan ] ${REF}-${other}（$seqs 条序列） -> $target"
        REPORT+=("${REF}-${other}	$seqs	-	-	dry-run")
        continue
    fi

    mkdir -p "$target"
    echo "[start] ${REF}-${other}（$seqs 条序列）"
    start=$SECONDS
    runlog="$OUT_ROOT/.${REF}-${other}-${STAMP}.log"

    if ! "$DIAMOND" makedb --in "$f" -d "${db%.dmnd}" -p "$THREADS" --quiet > "$runlog" 2>&1; then
        echo "[FAIL ] ${REF}-${other}：建库失败，见 $runlog"
        REPORT+=("${REF}-${other}	$seqs	-	$((SECONDS-start))	failed_makedb")
        failed=$((failed + 1)); continue
    fi

    if "$DIAMOND" blastp -q "$REF_FILE" -d "$db" -o "$out" \
            -f 6 -e "$EVALUE" -k "$MAX_TARGET" \
            ${MODE_FLAG:+"$MODE_FLAG"} --comp-based-stats "$COMP_STATS" \
            -p "$THREADS" >> "$runlog" 2>&1; then
        elapsed=$((SECONDS - start))
        hits="$(wc -l < "$out" | tr -d ' ')"
        echo "[ ok  ] ${REF}-${other}  ${elapsed}s  hits=${hits}"
        REPORT+=("${REF}-${other}	$seqs	$hits	$elapsed	ok")
        rm -f "$runlog"
        ok=$((ok + 1))
    else
        echo "[FAIL ] ${REF}-${other}：比对失败，见 $runlog"
        REPORT+=("${REF}-${other}	$seqs	-	$((SECONDS-start))	failed_blastp")
        failed=$((failed + 1))
    fi
done

echo "------------------------------------------------------------"
if [[ ${#REPORT[@]} -gt 0 ]]; then
    printf '%-18s %10s %10s %8s %s\n' 物种对 比对序列 命中 秒 状态
    for r in "${REPORT[@]}"; do
        IFS=$'\t' read -r a b c d e <<< "$r"
        printf '%-18s %10s %10s %8s %s\n' "$a" "$b" "$c" "$d" "$e"
    done
fi
echo "完成：成功 $ok，跳过 $skipped，失败 $failed"
[[ $failed -gt 0 ]] && exit 1 || exit 0
