#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PADDLEOCR_DIR="${PADDLEOCR_DIR:-/home/lyc/PaddleOCR}"
MODE="${1:-all}"

if [[ ! -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  echo "Virtual environment is missing. Run ./setup.sh first." >&2
  exit 1
fi

export PADDLE_PDX_MODEL_SOURCE="${PADDLE_PDX_MODEL_SOURCE:-BOS}"
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK="${PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK:-True}"
export PYTHONUNBUFFERED=1
cd "${ROOT_DIR}"

run_mode() {
  local target_mode="$1"
  local attempt
  for attempt in 1 2 3; do
    if "${ROOT_DIR}/.venv/bin/python" scripts/preload.py \
      --mode "${target_mode}" \
      --paddleocr-dir "${PADDLEOCR_DIR}"; then
      return 0
    fi
    if [[ "${attempt}" -lt 3 ]]; then
      echo "Preload ${target_mode} failed (attempt ${attempt}/3); retrying in 5 seconds..." >&2
      sleep 5
    fi
  done
  return 1
}

if [[ "${MODE}" == "all" ]]; then
  for CURRENT_MODE in ocr structure vl; do
    run_mode "${CURRENT_MODE}"
  done
else
  run_mode "${MODE}"
fi
