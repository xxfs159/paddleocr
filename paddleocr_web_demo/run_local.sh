#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

if [[ ! -x "${ROOT_DIR}/.venv/bin/uvicorn" ]]; then
  echo "Virtual environment is missing. Run ./setup.sh first." >&2
  exit 1
fi

export PADDLE_PDX_MODEL_SOURCE="${PADDLE_PDX_MODEL_SOURCE:-BOS}"
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK="${PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK:-True}"
export PYTHONUNBUFFERED=1
cd "${ROOT_DIR}"
exec "${ROOT_DIR}/.venv/bin/uvicorn" app.main:app \
  --host "${HOST}" \
  --port "${PORT}" \
  --workers 1 \
  --no-access-log
