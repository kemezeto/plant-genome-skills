#!/usr/bin/env bash
# Wrap upstream WGDI preprocess (pgci_preprocess) for the plant-genome-resources workspace.
# Usage (same options as upstream run_pipeline.sh, plus bridge flags):
#   bash scripts/preprocess/run_wgdi_preprocess.sh [DATA_ROOT] [--sync-inventory] [--prepare-accession] [--species ID] ...
# DATA_ROOT defaults to current directory.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
WGDI_PREPROCESS_ROOT="${WGDI_PREPROCESS_ROOT:-/workspace/vendor/plant-genome-wgdi-preprocess}"
WGDI_PREPROCESS_SCRIPTS="${WGDI_PREPROCESS_ROOT}/scripts"

if [[ ! -d "$WGDI_PREPROCESS_SCRIPTS" ]]; then
    echo "ERROR: WGDI preprocess scripts not found at $WGDI_PREPROCESS_SCRIPTS (set WGDI_PREPROCESS_ROOT)" >&2
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
            cat <<'HELP'
Usage: run_wgdi_preprocess.sh [DATA_ROOT] [bridge options] [upstream options]

Bridge options:
  --sync-inventory      Run step2_sync_inventory_from_manifest.py
  --prepare-accession   Run step2_prepare_wgdi_inputs.py (hardlink GCA_/GCF_ aliases)

Upstream options (forwarded to run_pipeline.sh):
  --species LIST
  --expected-count N
  --refresh-links
  --skip-hashes

Environment:
  WGDI_PREPROCESS_ROOT   default /workspace/vendor/plant-genome-wgdi-preprocess
  PYTHON                 python interpreter (default: python3)
HELP
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
    echo "[bridge] prepare WGDI preprocess accession aliases"
    prepare_args=(--project-root "$DATA_ROOT")
    if [[ -n "$SPECIES_FOR_PREPARE" ]]; then
        prepare_args+=(--species "$SPECIES_FOR_PREPARE")
    fi
    "$PYTHON_BIN" "$SCRIPT_DIR/step2_prepare_wgdi_inputs.py" "${prepare_args[@]}"
fi

export PYTHONPATH="${WGDI_PREPROCESS_SCRIPTS}${PYTHONPATH:+:$PYTHONPATH}"
echo "[wgdi-preprocess] run_pipeline.sh $DATA_ROOT ${FORWARD[*]:-}"
bash "$WGDI_PREPROCESS_SCRIPTS/run_pipeline.sh" "$DATA_ROOT" ${FORWARD[@]+"${FORWARD[@]}"}
