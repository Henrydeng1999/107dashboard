#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/data/107dashboard.env"
LOG_FILE="${PROJECT_ROOT}/data/107dashboard.log"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}; run scripts/107-dashboard-service.sh configure first." >&2
  exit 1
fi

set -a
source "${ENV_FILE}"
set +a

cd "${PROJECT_ROOT}"
exec "${PROJECT_ROOT}/backend/.venv/bin/python" -m uvicorn app.main:app \
  --app-dir backend \
  --host "${APP_HOST:-127.0.0.1}" \
  --port "${APP_PORT:-8000}" \
  --workers 1 >>"${LOG_FILE}" 2>&1
