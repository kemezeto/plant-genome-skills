#!/usr/bin/env bash
# 单物种蛋白自身比对（self-vs-self）：diamond makedb + blastp
#
#   bash scripts/run_self_diamond.sh -i data/Vvi.pep -o self_diamod/Vvi_test
#   bash scripts/run_self_diamond.sh -i data/Car.pep -o self_diamod/Car_test -k 0 -t 8
#
# 产出（OUTDIR 下，默认只有三个文件）：
#   {base}.dmnd               DIAMOND 索引
#   {base}.self.blast         outfmt 6 原始结果（12 列，回溯用）
#   {base}.self.uniq.blast    干净结果：无对角线、无重复对、无同序列命中（下游用这个）
# 加 --audit 时额外落盘 identical.blast / dupseq_map.tsv / stats.tsv / params.txt
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"

DIAMOND="${DIAMOND:-diamond}"
INPUT="$PROJECT_DIR/data/Vvi.pep"
OUTDIR="$PROJECT_DIR/self_diamod"
EVALUE="1e-5"
MAX_TARGET=50
THREADS="$(nproc 2>/dev/null || echo 4)"
MODE="more-sensitive"
COMP_STATS=0
DEDUP=1
DROP_IDENTICAL=1
KEEP_SELF_HITS=0
FORCE=0
AUDIT=0

usage() {
    sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    cat <<'EOF'

Options:
  -i, --input PATH     输入 pep FASTA（默认 data/Vvi.pep）
  -o, --outdir PATH    输出目录（默认 self_diamod）
  -e, --evalue FLOAT   e-value 阈值（默认 1e-5）
  -k, --max-targets N  每 query 最多报告的目标数（默认 50；0=不限，自比最保险）
  -t, --threads N      线程数（默认全部核心）
      --mode MODE      default|sensitive|more-sensitive|very-sensitive|ultra-sensitive
      --comp-stats N   --comp-based-stats 取值（默认 0，自比建议保持 0）
      --no-dedup       不去对称重复，也不剔除同序列命中
      --keep-identical 保留"不同 ID 但序列完全相同"的命中（默认剔除，不落盘）
      --audit          额外保留 5 个审计文件：identical.blast / dupseq_map.tsv
                       / stats.tsv / params.txt / run.log（默认只输出 dmnd + 两份 blast）
      --with-self-hits 保留对角线自身命中（默认去掉）
      --force          输出目录非空时仍继续（覆盖同名文件）
  -h, --help           显示本帮助
EOF
}

# Git Bash 把 E:\a\b 这类路径统一成 /e/a/b 再递给原生 exe
norm_path() {
    local p="$1"
    if [[ "$p" =~ ^[A-Za-z]:[\\/] ]]; then
        p="/$(printf '%s' "${p:0:1}" | tr 'A-Z' 'a-z')/${p:3}"
    fi
    printf '%s' "$p" | tr '\\' '/'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--input)        INPUT="$(norm_path "$2")"; shift 2 ;;
        -o|--outdir)       OUTDIR="$(norm_path "$2")"; shift 2 ;;
        -e|--evalue)       EVALUE="$2"; shift 2 ;;
        -k|--max-targets)  MAX_TARGET="$2"; shift 2 ;;
        -t|--threads)      THREADS="$2"; shift 2 ;;
        --mode)            MODE="$2"; shift 2 ;;
        --comp-stats)      COMP_STATS="$2"; shift 2 ;;
        --no-dedup)        DEDUP=0; shift ;;
        --keep-identical)  DROP_IDENTICAL=0; shift ;;
        --audit)           AUDIT=1; shift ;;
        --with-self-hits)  KEEP_SELF_HITS=1; shift ;;
        --force)           FORCE=1; shift ;;
        -h|--help)         usage; exit 0 ;;
        *) echo "未知参数: $1（-h 看帮助）" >&2; exit 2 ;;
    esac
done

case "$MODE" in
    default) MODE_FLAG="" ;;
    sensitive|more-sensitive|very-sensitive|ultra-sensitive) MODE_FLAG="--$MODE" ;;
    *) echo "不支持的 --mode: $MODE" >&2; exit 2 ;;
esac

# ---------------------------------------------------------------- 前置检查
command -v "$DIAMOND" >/dev/null 2>&1 || {
    echo "找不到 diamond（命令：$DIAMOND）。装法：conda install -c bioconda diamond" >&2
    exit 2
}
[[ -f "$INPUT" ]] || { echo "输入文件不存在: $INPUT" >&2; exit 2; }
[[ -s "$INPUT" ]] || { echo "输入文件为空: $INPUT" >&2; exit 2; }

mkdir -p "$OUTDIR"
shopt -s nullglob dotglob
existing=("$OUTDIR"/*)
shopt -u nullglob dotglob
if [[ ${#existing[@]} -gt 0 && $FORCE -eq 0 ]]; then
    echo "输出目录非空：$OUTDIR（加 --force 覆盖，或换个 -o）" >&2
    exit 2
fi

BASE="$(basename "$INPUT")"
BASE="${BASE%.*}"
DB="$OUTDIR/$BASE.dmnd"
RAW="$OUTDIR/$BASE.self.blast"
UNIQ="$OUTDIR/$BASE.self.uniq.blast"

# 中间件放 .work/：默认跑完就删，--audit 时再复制出去
WORK="$OUTDIR/.work"
KEEP="$RAW"
IDENT="$WORK/$BASE.self.identical.blast"
DUP_MAP="$WORK/$BASE.dupseq_map.tsv"
STATS="$WORK/$BASE.self.stats.tsv"
PARAMS="$WORK/$BASE.params.txt"
LOG="$WORK/run.log"

mkdir -p "$WORK"
: > "$IDENT"
cleanup() {
    [[ "${AUDIT:-0}" -eq 1 ]] && return 0
    rm -f "$IDENT" "$DUP_MAP" "$STATS" "$PARAMS" "$LOG" "$RAW.tmp" 2>/dev/null || true
    rmdir "$WORK" 2>/dev/null || true
}
trap cleanup EXIT

log() { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*" | tee -a "$LOG"; }

: > "$LOG"

SEQ_COUNT="$(grep -c '^>' "$INPUT" || true)"
[[ "${SEQ_COUNT:-0}" -gt 0 ]] || { echo "输入里没有 FASTA 序列: $INPUT" >&2; exit 2; }
DUP_IDS="$(grep '^>' "$INPUT" | awk '{print $1}' | sort | uniq -d | wc -l | tr -d ' ')"
if [[ "$DUP_IDS" -gt 0 ]]; then
    log "警告：检测到 $DUP_IDS 个重复序列 ID；自比会因此产生对角命中，建议先去重"
fi

log "输入      : $INPUT（$SEQ_COUNT 条序列）"
log "输出目录  : $OUTDIR"
log "diamond   : $("$DIAMOND" version 2>&1 | head -1)"
log "参数      : -e $EVALUE  -k $MAX_TARGET  mode=${MODE}  comp-based-stats=${COMP_STATS}  threads=${THREADS}"
log "自身命中  : $([[ $KEEP_SELF_HITS -eq 1 ]] && echo 保留 || echo '去掉(--no-self-hits)')"

START_TS="$(date +%s)"

# ---------------------------------------------------------------- 1/4 建库
log "1/4 makedb ..."
"$DIAMOND" makedb --in "$INPUT" -d "${DB%.dmnd}" -p "$THREADS" --quiet 2>>"$LOG"
[[ -s "$DB" ]] || { echo "建库失败，未生成 $DB" >&2; exit 1; }
log "     -> $DB ($(du -h "$DB" | cut -f1))"

# ---------------------------------------------------------------- 2/4 自比
log "2/4 blastp（自比）..."
SELF_FLAG=()
[[ $KEEP_SELF_HITS -eq 0 ]] && SELF_FLAG=(--no-self-hits)
"$DIAMOND" blastp \
    -q "$INPUT" -d "$DB" -o "$RAW" \
    -f 6 -e "$EVALUE" -k "$MAX_TARGET" \
    ${MODE_FLAG:+"$MODE_FLAG"} \
    --comp-based-stats "$COMP_STATS" \
    ${SELF_FLAG[@]+"${SELF_FLAG[@]}"} -p "$THREADS" \
    2>>"$LOG"
RAW_N="$(wc -l < "$RAW" | tr -d ' ')"
log "     -> $RAW（$RAW_N 行）"

# ---------------------------------------------------------------- 3/4 剔除同序列命中
IDENT_N=0
DUP_GROUPS=0
KEEP="$RAW"
if [[ $DROP_IDENTICAL -eq 1 ]]; then
    log "3/4 找完全相同序列（isoform / 重复条目）..."
    awk '/^>/{if(id!="")print id"\t"seq; id=substr($1,2); seq=""; next}
         {seq=seq $0}
         END{if(id!="")print id"\t"seq}' "$INPUT" \
    | sort -t$'\t' -k2,2 \
    | awk -F'\t' '
        $2!=prev { if (cnt>1) { g++; for(i=1;i<=cnt;i++) print ids[i]"\tdup"g } cnt=0; prev=$2 }
        { ids[++cnt]=$1 }
        END { if (cnt>1) { g++; for(i=1;i<=cnt;i++) print ids[i]"\tdup"g } }' > "$DUP_MAP"
    DUP_GROUPS="$(cut -f2 "$DUP_MAP" | sort -u | wc -l | tr -d ' ')"
    if [[ "$DUP_GROUPS" -gt 0 ]]; then
        : > "$IDENT"
        awk -F'\t' -v keep="$KEEP.tmp" -v drop="$IDENT" '
            NR==FNR { g[$1]=$2; next }
            (($1 in g) && ($2 in g) && g[$1]==g[$2]) { print > drop; next }
            { print > keep }' "$DUP_MAP" "$RAW"
        mv "$KEEP.tmp" "$KEEP"
        IDENT_N="$(wc -l < "$IDENT" | tr -d ' ')"
        log "     -> $DUP_GROUPS 组同序列，剔除 $IDENT_N 条命中"
    else
        log "     -> 无完全相同序列"
    fi
else
    log "3/4 跳过同序列剔除（--keep-identical）"
fi

# ---------------------------------------------------------------- 4/4 每个序列对只留一行
FINAL="$RAW"
if [[ $DEDUP -eq 1 ]]; then
    log "4/4 每个序列对保留一行（优先 qseqid < sseqid）..."
    # 自比不严格对称：有约 0.6% 的序列对只在单方向出现。
    # 只按 $1<$2 过滤会丢掉这些对，所以按「无序对」去重、优先保留正向那一行。
    awk -F'\t' '{
            k = ($1<$2) ? $1 "\t" $2 : $2 "\t" $1
            f = ($1<$2) ? 0 : 1
            print k "\t" f "\t" $0
        }' "$KEEP" \
    | sort -t$'\t' -k1,1 -k2,2 -k3,3n \
    | awk -F'\t' '!seen[$1 "\t" $2]++ { sub(/^[^\t]*\t[^\t]*\t[^\t]*\t/, ""); print }' > "$UNIQ"
    FINAL="$UNIQ"
    log "     -> $UNIQ（$(wc -l < "$UNIQ" | tr -d ' ') 行）"
else
    FINAL="$RAW"
    log "4/4 跳过去重（--no-dedup）"
fi

# ---------------------------------------------------------------- 统计与参数
TOTAL="$(wc -l < "$RAW" | tr -d ' ')"
FINAL_N="$(wc -l < "$FINAL" | tr -d ' ')"
QUERY_WITH_HITS="$(cut -f1 "$FINAL" | sort -u | wc -l | tr -d ' ')"
SUBJ_N="$(cut -f2 "$FINAL" | sort -u | wc -l | tr -d ' ')"
DIAG="$(awk -F'\t' '$1==$2' "$RAW" | wc -l | tr -d ' ')"
SINGLE_DIR="$(awk -F'\t' '{k=($1<$2)?$1 SUBSEP $2:$2 SUBSEP $1; c[k]++}
    END{n=0; for(k in c) if(c[k]==1)n++; print n+0}' "$RAW")"
if [[ "$MAX_TARGET" -gt 0 ]]; then
    AT_CAP="$(cut -f1 "$RAW" | sort | uniq -c | awk -v k="$MAX_TARGET" '$1==k' | wc -l | tr -d ' ')"
else
    AT_CAP=0
fi
{
    printf 'item\tvalue\n'
    printf 'input_sequences\t%s\n' "$SEQ_COUNT"
    printf 'raw_hits\t%s\n' "$TOTAL"
    printf 'diagonal_hits\t%s\n' "$DIAG"
    printf 'pairs_one_direction_only\t%s\n' "$SINGLE_DIR"
    printf 'identical_seq_groups\t%s\n' "$DUP_GROUPS"
    printf 'identical_hits_dropped\t%s\n' "$IDENT_N"
    printf 'final_hits\t%s\n' "$FINAL_N"
    printf 'queries_with_hits\t%s\n' "$QUERY_WITH_HITS"
    printf 'subjects_hit\t%s\n' "$SUBJ_N"
    printf 'queries_at_cap\t%s\n' "$AT_CAP"
} > "$STATS"

if [[ "$AT_CAP" -gt 0 ]]; then
    log "注意：$AT_CAP 个 query 的命中数正好等于 -k $MAX_TARGET，可能被截断；要完整结果用 -k 0 重跑"
fi

END_TS="$(date +%s)"
{
    echo "# 单物种自比参数记录"
    echo "timestamp=$(date '+%Y-%m-%d %H:%M:%S %z')"
    echo "host=$(hostname 2>/dev/null || echo NA)"
    echo "diamond=$("$DIAMOND" version 2>&1 | head -1)"
    echo "input=$INPUT"
    echo "input_sequences=$SEQ_COUNT"
    echo "input_sha256=$(sha256sum "$INPUT" | cut -d' ' -f1)"
    echo "outfmt=6 (qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore)"
    echo "evalue=$EVALUE"
    echo "max_target_seqs=$MAX_TARGET"
    echo "mode=${MODE}"
    echo "comp_based_stats=$COMP_STATS"
    echo "self_hits=$([[ $KEEP_SELF_HITS -eq 1 ]] && echo kept || echo suppressed)"
    echo "drop_identical_seq=$DROP_IDENTICAL"
    echo "dedup_symmetric=$DEDUP"
    echo "threads=$THREADS"
    echo "db=$DB"
    echo "raw=$RAW"
    echo "final=$FINAL"
    echo "elapsed_seconds=$((END_TS - START_TS))"
} > "$PARAMS"

log "完成，用时 $((END_TS - START_TS)) 秒"
log "  原始结果 : $RAW（$TOTAL 行）"
log "  最终结果 : $FINAL（$FINAL_N 行）"

if [[ $AUDIT -eq 1 ]]; then
    mv "$IDENT" "$DUP_MAP" "$STATS" "$PARAMS" "$OUTDIR"/
    mv "$LOG" "$OUTDIR/run.log"
    rmdir "$WORK" 2>/dev/null || true
    LOG="$OUTDIR/run.log"
    log "  审计文件 : identical.blast / dupseq_map.tsv / stats.tsv / params.txt / run.log"
fi
