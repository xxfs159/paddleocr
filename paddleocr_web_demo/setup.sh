#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PADDLEOCR_DIR="${PADDLEOCR_DIR:-/home/lyc/PaddleOCR}"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv}"

if [[ ! -d "${PADDLEOCR_DIR}" ]]; then
  echo "PaddleOCR repository not found: ${PADDLEOCR_DIR}" >&2
  exit 1
fi

python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"
PIP_ARGS=(--retries 20 --timeout 60)
python -m pip install "${PIP_ARGS[@]}" --upgrade pip wheel setuptools setuptools_scm

echo "Installing PaddlePaddle GPU 3.2.1 for CUDA 12.9 / NVIDIA Blackwell..."
PYTHON_TAG="$("${VENV_DIR}/bin/python" -c 'import sys; print(f"cp{sys.version_info.major}{sys.version_info.minor}")')"
ARCH="$(uname -m)"
if [[ "${PYTHON_TAG}" != "cp312" || "${ARCH}" != "x86_64" ]]; then
  echo "This setup currently expects Python 3.12 on Linux x86_64." >&2
  exit 1
fi
PADDLE_WHEEL_URL="${PADDLE_WHEEL_URL:-https://paddle-whl.bj.bcebos.com/stable/cu129/paddlepaddle-gpu/paddlepaddle_gpu-3.2.1-cp312-cp312-linux_x86_64.whl}"
if python -c 'import paddle; raise SystemExit(0 if paddle.__version__ == "3.2.1" else 1)' 2>/dev/null; then
  echo "PaddlePaddle GPU 3.2.1 is already installed."
else
  python -m pip install "${PIP_ARGS[@]}" "${PADDLE_WHEEL_URL}"
fi

echo "Installing local PaddleOCR with document parser dependencies..."
python -m pip install "${PIP_ARGS[@]}" --no-build-isolation -e "${PADDLEOCR_DIR}[doc-parser]"

echo "Installing web application and test dependencies..."
python -m pip install "${PIP_ARGS[@]}" -e "${ROOT_DIR}[dev]"

mkdir -p "${ROOT_DIR}/data/jobs" "${ROOT_DIR}/.tools"

python - <<'PY'
import paddle
import paddleocr
print(f"PaddlePaddle: {paddle.__version__}")
print(f"PaddleOCR: {paddleocr.__version__}")
print(f"CUDA available: {paddle.device.is_compiled_with_cuda()}")
PY

echo
echo "Setup complete."
echo "Preload models: ${ROOT_DIR}/preload_models.sh"
echo "Start locally:  ${ROOT_DIR}/run_local.sh"
