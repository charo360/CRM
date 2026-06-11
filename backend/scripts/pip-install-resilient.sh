#!/usr/bin/env bash
# Resilient backend venv install for slow/unstable PyPI links.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$ROOT/.venv/bin/python3.11"
REQ="$ROOT/requirements.txt"
LOG="$ROOT/pip-install.log"
WHEELS="$ROOT/.pip-wheels"

export PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-1800}"
export PIP_RETRIES="${PIP_RETRIES:-25}"
export PIP_PROGRESS_BAR=on

mkdir -p "$WHEELS"
exec > >(tee -a "$LOG") 2>&1

echo "=== $(date -Is) start resilient pip install ==="
"$VENV_PY" -m pip install --upgrade pip setuptools wheel

install_req() {
  local file="$1"
  local attempt=1
  local max="${2:-50}"
  while (( attempt <= max )); do
    echo "--- attempt $attempt/$max: pip install -r $file ---"
    if "$VENV_PY" -m pip install \
      --prefer-binary \
      --retries "$PIP_RETRIES" \
      --timeout "$PIP_DEFAULT_TIMEOUT" \
      -r "$file"; then
      return 0
    fi
    echo "attempt $attempt failed; sleeping 30s..."
    sleep 30
    (( attempt++ )) || true
  done
  return 1
}

# Playwright last (large wheel); optional skip: SKIP_PLAYWRIGHT=1
grep -v '^playwright==' "$REQ" > /tmp/requirements-no-playwright.txt

install_req /tmp/requirements-no-playwright.txt 30

if [[ "${SKIP_PLAYWRIGHT:-}" != "1" ]]; then
  attempt=1
  while (( attempt <= 30 )); do
    echo "--- playwright attempt $attempt ---"
  if "$VENV_PY" -m pip install \
      --prefer-binary \
      --retries "$PIP_RETRIES" \
      --timeout "$PIP_DEFAULT_TIMEOUT" \
      "playwright==1.49.0"; then
      break
    fi
    sleep 60
    (( attempt++ )) || true
  done
fi

echo "=== $(date -Is) done; package count: $( "$VENV_PY" -m pip list | wc -l ) ==="
