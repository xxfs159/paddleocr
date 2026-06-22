#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8000}"
TOOLS_DIR="${ROOT_DIR}/.tools"
CLOUDFLARED="${TOOLS_DIR}/cloudflared"

if [[ ! -x "${ROOT_DIR}/.venv/bin/uvicorn" ]]; then
  echo "Virtual environment is missing. Run ./setup.sh first." >&2
  exit 1
fi

mkdir -p "${TOOLS_DIR}"
if [[ ! -x "${CLOUDFLARED}" ]]; then
  ARCH="$(uname -m)"
  case "${ARCH}" in
    x86_64|amd64) ASSET="cloudflared-linux-amd64" ;;
    aarch64|arm64) ASSET="cloudflared-linux-arm64" ;;
    *)
      echo "Unsupported architecture for automatic cloudflared download: ${ARCH}" >&2
      exit 1
      ;;
  esac
  URL="https://github.com/cloudflare/cloudflared/releases/latest/download/${ASSET}"
  echo "Downloading cloudflared..."
  if command -v curl >/dev/null 2>&1; then
    curl -fL \
      --retry 20 \
      --retry-all-errors \
      --retry-delay 3 \
      --connect-timeout 30 \
      -C - \
      "${URL}" \
      -o "${CLOUDFLARED}"
  elif command -v wget >/dev/null 2>&1; then
    wget -c --tries=20 --timeout=60 -O "${CLOUDFLARED}" "${URL}"
  else
    echo "curl or wget is required to download cloudflared." >&2
    exit 1
  fi
  chmod +x "${CLOUDFLARED}"
fi

export PADDLE_PDX_MODEL_SOURCE="${PADDLE_PDX_MODEL_SOURCE:-BOS}"
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK="${PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK:-True}"
export PYTHONUNBUFFERED=1
cd "${ROOT_DIR}"

"${ROOT_DIR}/.venv/bin/uvicorn" app.main:app \
  --host 127.0.0.1 \
  --port "${PORT}" \
  --workers 1 \
  --no-access-log &
SERVER_PID=$!

cleanup() {
  kill "${SERVER_PID}" >/dev/null 2>&1 || true
  wait "${SERVER_PID}" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 60); do
  if curl --noproxy "*" -fsS "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
    echo "Web service failed to start." >&2
    exit 1
  fi
  sleep 1
done

echo
echo "The temporary public URL will appear below."
echo "Keep this terminal open while the demonstration is running."
echo
"${CLOUDFLARED}" tunnel --url "http://127.0.0.1:${PORT}" --no-autoupdate
