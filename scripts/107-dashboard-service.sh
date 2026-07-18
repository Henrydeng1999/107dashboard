#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/data/107dashboard.env"
ENV_TEMPLATE="${PROJECT_ROOT}/deploy/107-native-interactive.env.example"
SESSION_NAME="107dashboard"
RUNNER="${PROJECT_ROOT}/scripts/run-107-dashboard.sh"

usage() {
  echo "Usage: $0 {configure|start|stop|restart|status|logs}"
}

require_tmux() {
  command -v tmux >/dev/null || { echo "tmux is required" >&2; exit 1; }
}

load_environment() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Missing ${ENV_FILE}; run '$0 configure' first." >&2
    exit 1
  fi
  set -a
  source "${ENV_FILE}"
  set +a
}

configure() {
  umask 077
  mkdir -p "${PROJECT_ROOT}/data/jobs"
  if [[ -f "${ENV_FILE}" ]]; then
    backup="${ENV_FILE}.backup-$(date -u +%Y%m%dT%H%M%SZ)"
    cp -p "${ENV_FILE}" "${backup}"
    echo "Previous configuration backed up to ${backup}"
  fi
  sed \
    -e "s|/home/scc/USERNAME/107dashboard|${PROJECT_ROOT}|g" \
    -e "s|USERNAME|$(id -un)|g" \
    "${ENV_TEMPLATE}" >"${ENV_FILE}"
  chmod 600 "${ENV_FILE}"
  echo "Wrote real Native product configuration to ${ENV_FILE}"
}

preflight() {
  load_environment
  require_tmux
  [[ -x "${PROJECT_ROOT}/backend/.venv/bin/python" ]] || { echo "Backend venv is missing" >&2; exit 1; }
  [[ -f "${PROJECT_ROOT}/frontend/dist/index.html" ]] || { echo "Frontend build is missing" >&2; exit 1; }
  "${PROJECT_ROOT}/backend/.venv/bin/python" "${PROJECT_ROOT}/scripts/check-native-product.py"
}

start() {
  require_tmux
  if tmux has-session -t "=${SESSION_NAME}" 2>/dev/null; then
    echo "107 Dashboard is already running."
    status
    return
  fi
  preflight
  printf -v runner_command 'exec bash %q' "${RUNNER}"
  tmux new-session -d -s "${SESSION_NAME}" -c "${PROJECT_ROOT}" "${runner_command}"
  load_environment
  for _ in {1..20}; do
    if "${PROJECT_ROOT}/backend/.venv/bin/python" "${PROJECT_ROOT}/scripts/check-native-product.py" \
      --base-url "http://${APP_HOST:-127.0.0.1}:${APP_PORT:-8000}" >/dev/null 2>&1; then
      echo "107 Dashboard started at http://${APP_HOST:-127.0.0.1}:${APP_PORT:-8000}"
      status
      return
    fi
    sleep 1
  done
  tmux kill-session -t "=${SESSION_NAME}" 2>/dev/null || true
  echo "107 Dashboard failed to become healthy; inspect '$0 logs'." >&2
  exit 1
}

stop() {
  require_tmux
  if tmux has-session -t "=${SESSION_NAME}" 2>/dev/null; then
    tmux kill-session -t "=${SESSION_NAME}"
    echo "107 Dashboard stopped."
  else
    echo "107 Dashboard is not running."
  fi
}

status() {
  require_tmux
  if ! tmux has-session -t "=${SESSION_NAME}" 2>/dev/null; then
    echo "107 Dashboard is not running."
    return 1
  fi
  load_environment
  "${PROJECT_ROOT}/backend/.venv/bin/python" "${PROJECT_ROOT}/scripts/check-native-product.py" \
    --base-url "http://${APP_HOST:-127.0.0.1}:${APP_PORT:-8000}"
}

logs() {
  if [[ -f "${PROJECT_ROOT}/data/107dashboard.log" ]]; then
    tail -n 100 "${PROJECT_ROOT}/data/107dashboard.log"
  else
    echo "No service log exists yet."
  fi
}

case "${1:-}" in
  configure) configure ;;
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  logs) logs ;;
  *) usage; exit 2 ;;
esac
