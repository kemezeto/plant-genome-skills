#!/usr/bin/env bash
# Wrap HXC plant-genome-preprocess for the plant-genome-resources workspace.
# Usage (same options as HXC run_pipeline.sh, plus bridge flags):
#   bash scripts/preprocess/run_hxc_preprocess.sh [DATA_ROOT] [--sync-inventory] [--prepare-accession] [--species ID] ...
# DATA_ROOT defaults to current directory.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
HXC_ROOT="${HXC_ROOT:-/workspace/vendor/hxc-plant-genome-preprocess}"
HXC_SCRIPTS="${HXC_ROOT}/scripts"

if [[ ! -d "$HXC_SCRIPTS" ]]; then
    echo "ERROR: HXC scripts not found at $HXC_SCRIPTS (set HXC_ROOT)" >&2
    exit 2
fi

DATA_ROOT="."
SYNC_INVENTORY=false
PREPARE_ACCESSION=false
FORWARD=()

# First positional may be DATA_ROOT (directory) or an option.
if (($# > 0)) && [[ "$1" != -* ]]; then
    DATA_ROOT="$1"
    shift
fi

while (($# > 0)); do
    case "$1" in
        --sync-inventory)
            SYNC_INVENTORY=true
            shift
            ;;
        --prepare-accession)
            PREPARE_ACCESSION=true
            shift
            ;;
        --help|-h)
            cat <<'EOF'
Usage: run_hxc_preprocess.sh [DATA_ROOT] [bridge options] [HXC options]

Bridge options:
  --sync-inventory      Run step2_sync_inventory_from_manifest.py
  --prepare-accession   Run step2_prepare_hxc_inputs.py (hardlink GCA_/GCF_ aliases)

HXC options (forwarded to run_pipeline.sh):
  --species LIST
  --expected-count N
  --refresh-links
  --skip-hashes

Environment:
  HXC_ROOT   default /workspace/vendor/hxc-plant-genome-preprocess
  PYTHON     python interpreter (default: python3)
EOF
            exit 0
            ;;
        *)
            FORWARD+=("$1")
            shift
            ;;
    esac
done

if [[ ! -d "$DATA_ROOT" ]]; then
    echo "ERROR: DATA_ROOT is not a directory: $DATA_ROOT" >&2
    exit 2
fi
DATA_ROOT="$(cd -- "$DATA_ROOT" && pwd -P)"
PYTHON_BIN="${PYTHON:-python3}"
export PYTHON="$PYTHON_BIN"

# Optional showid filter for prepare (extract from forwarded --species).
SPECIES_FOR_PREPARE=""
for ((i = 0; i < ${#FORWARD[@]}; i++)); do
    if [[ "${FORWARD[$i]}" == "--species" ]] && ((i + 1 < ${#FORWARD[@]})); then
        SPECIES_FOR_PREPARE="${FORWARD[$((i + 1))]}"
        break
    fi
done

if [[ "$SYNC_INVENTORY" == true ]]; then
    echo "[bridge] sync inventory from preprocess_input_manifest.tsv"
    "$PYTHON_BIN" "$SCRIPT_DIR/step2_sync_inventory_from_manifest.py" --project-root "$DATA_ROOT"
fi

if [[ "$PREPARE_ACCESSION" == true ]]; then
    echo "[bridge] prepare HXC accession aliases"
    prepare_args=(--project-root "$DATA_ROOT")
    if [[ -n "$SPECIES_FOR_PREPARE" ]]; then
        prepare_args+=(--species "$SPECIES_FOR_PREPARE")
    fi
    "$PYTHON_BIN" "$SCRIPT_DIR/step2_prepare_hxc_inputs.py" "${prepare_args[@]}"
fi

export PYTHONPATH="${HXC_SCRIPTS}${PYTHONPATH:+:$PYTHONPATH}"
echo "[hxc] run_pipeline.sh $DATA_ROOT ${FORWARD[*]:-}"
bash "$HXC_SCRIPTS/run_pipeline.sh" "$DATA_ROOT" ${FORWARD[@]+"${FORWARD[@]}"}
