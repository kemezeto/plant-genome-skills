#!/usr/bin/env bash
# 批量自比：data/ 下每个 pep 各自跑「自身 vs 自身」，互不交叉。
# 每个物种一个独立目录：{out-root}/{物种缩写}_{时间戳}/
#
#   bash scripts/run_batch_self_diamond.sh                 # data/*.pep → self_diamod/Vvi_20261108-1150/
#   bash scripts/run_batch_self_diamond.sh --dry-run       # 只列出会跑什么
#   bash scripts/run_batch_self_diamond.sh -t 8 -k 0 --audit
#
# 每个物种目录内只有 3 个文件（dmnd / self.blast / self.uniq.blast），
# 加 --audit 时再多 5 个审计文件。
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
SINGLE="$SCRIPT_DIR/run_self_diamond.sh"

DATA_DIR="$PROJECT_DIR/data"
OUT_ROOT="$PROJECT_DIR/self_diamod"
PATTERN="*.pep"
STAMP="$(date '+%Y%m%d-%H%M')"
DRY=0
FORCE=0
PASS_ARGS=()

usage() {
    sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    cat <<'EOF'

Options:
  -d, --data-dir PATH   输入目录（默认 data/）
  -o, --out-root PATH   结果根目录（默认 self_diamod/）
      --pattern GLOB    匹配的输入文件（默认 '*.pep'）
      --stamp TEXT      自定义时间戳（默认 年月日-时分）
      --dry-run         只打印计划，不执行
      --force           目标目录已存在时也继续
  -h, --help            显示本帮助

透传给 run_self_diamond.sh 的参数：
  -e/--evalue, -k/--max-targets, -t/--threads, --mode, --comp-stats,
  --no-dedup, --keep-identical, --with-self-hits, --audit
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -d|--data-dir)  DATA_DIR="$2"; shift 2 ;;
        -o|--out-root)  OUT_ROOT="$2"; shift 2 ;;
        --pattern)      PATTERN="$2"; shift 2 ;;
        --stamp)        STAMP="$2"; shift 2 ;;
        --dry-run)      DRY=1; shift ;;
        --force)        FORCE=1; shift ;;
        -h|--help)      usage; exit 0 ;;
        -e|--evalue|-k|--max-targets|-t|--threads|--mode|--comp-stats)
            PASS_ARGS+=("$1" "$2"); shift 2 ;;
        --no-dedup|--keep-identical|--with-self-hits|--audit)
            PASS_ARGS+=("$1"); shift ;;
        *) echo "未知参数: $1（-h 看帮助）" >&2; exit 2 ;;
    esac
done

[[ -x "$SINGLE" || -f "$SINGLE" ]] || { echo "找不到单物种脚本: $SINGLE" >&2; exit 2; }
[[ -d "$DATA_DIR" ]] || { echo "输入目录不存在: $DATA_DIR" >&2; exit 2; }

shopt -s nullglob
mapfile -t FILES < <(printf '%s\n' "$DATA_DIR"/$PATTERN | sort)
shopt -u nullglob
# 去掉空行（无匹配时的占位）
CLEAN=()
for f in ${FILES[@]+"${FILES[@]}"}; do
    [[ -n "$f" && -f "$f" ]] && CLEAN+=("$f")
done
FILES=(${CLEAN[@]+"${CLEAN[@]}"})
[[ ${#FILES[@]} -gt 0 ]] || { echo "在 $DATA_DIR 下没找到 $PATTERN" >&2; exit 2; }

echo "输入目录 : $DATA_DIR"
echo "结果根目录: $OUT_ROOT"
echo "时间戳   : $STAMP"
echo "物种数   : ${#FILES[@]}"
echo "------------------------------------------------------------"

ok=0
skipped=0
failed=0
declare -a REPORT=()

for f in "${FILES[@]}"; do
    name="$(basename "$f")"
    abbr="${name%.*}"
    abbr="${abbr// /_}"
    target="$OUT_ROOT/${abbr}_${STAMP}"
    seqs="$(grep -c '^>' "$f" || true)"

    if [[ -e "$target" && $FORCE -eq 0 ]]; then
        echo "[skip ] $abbr（$target 已存在，加 --force 覆盖）"
        skipped=$((skipped + 1))
        REPORT+=("$abbr	$seqs	-	-	skipped")
        continue
    fi

    if [[ $DRY -eq 1 ]]; then
        echo "[plan ] $abbr（$seqs 条序列） -> $target"
        REPORT+=("$abbr	$seqs	-	-	dry-run")
        continue
    fi

    mkdir -p "$OUT_ROOT"
    echo "[start] $abbr（$seqs 条序列） -> $target"
    start=$SECONDS
    if bash "$SINGLE" -i "$f" -o "$target" --force ${PASS_ARGS[@]+"${PASS_ARGS[@]}"} \
            > "$OUT_ROOT/.${abbr}_${STAMP}.log" 2>&1; then
        elapsed=$((SECONDS - start))
        uniq_n="$(wc -l < "$target/${abbr}.self.uniq.blast" 2>/dev/null | tr -d ' ' || echo 0)"
        echo "[ ok  ] $abbr  ${elapsed}s  uniq=${uniq_n}"
        REPORT+=("$abbr	$seqs	$uniq_n	$elapsed	ok")
        rm -f "$OUT_ROOT/.${abbr}_${STAMP}.log"
        ok=$((ok + 1))
    else
        elapsed=$((SECONDS - start))
        echo "[FAIL ] $abbr  见 $OUT_ROOT/.${abbr}_${STAMP}.log"
        REPORT+=("$abbr	$seqs	-	$elapsed	failed")
        failed=$((failed + 1))
    fi
done

echo "------------------------------------------------------------"
if [[ ${#REPORT[@]} -gt 0 ]]; then
    printf '%-12s %10s %12s %8s %s\n' 物种 序列数 命中对 秒 状态
    for r in "${REPORT[@]}"; do
        IFS=$'\t' read -r a b c d e <<< "$r"
        printf '%-12s %10s %12s %8s %s\n' "$a" "$b" "$c" "$d" "$e"
    done
fi
echo "完成：成功 $ok，跳过 $skipped，失败 $failed"
[[ $failed -gt 0 ]] && exit 1 || exit 0
