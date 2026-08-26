#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"
TEST_PROJECT_DIRECTORY="${TEST_PROJECT_DIRECTORY:-${HOME}/dashboard-test-projects}"
RUN_TESTS=true
START_SERVICE=true
REFRESH_TEST_PROJECTS=false

usage() {
  cat <<'EOF'
Usage: deploy/release/install.sh [options]

Options:
  --no-start                 Install and configure without starting the service
  --skip-tests               Skip the backend pytest suite
  --refresh-test-projects    Replace installed acceptance test projects
  -h, --help                 Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-start) START_SERVICE=false ;;
    --skip-tests) RUN_TESTS=false ;;
    --refresh-test-projects) REFRESH_TEST_PROJECTS=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

require_command() {
  command -v "$1" >/dev/null || { echo "Missing required command: $1" >&2; exit 1; }
}

[[ "$(uname -s)" == "Linux" ]] || { echo "This deployment package must be installed on Linux." >&2; exit 1; }
[[ "$(id -u)" -ne 0 ]] || { echo "Install as the trusted Slurm user, not root." >&2; exit 1; }
[[ "${PROJECT_ROOT}" != *[[:space:]]* ]] || { echo "The installation path must not contain whitespace." >&2; exit 1; }

for command in "${PYTHON_BIN}" git tmux sbatch scancel squeue sacct; do
  require_command "${command}"
done

"${PYTHON_BIN}" - <<'PY'
import sys
if sys.version_info[:2] != (3, 12):
    raise SystemExit(f"Python 3.12 is required, found {sys.version.split()[0]}")
PY

cd "${PROJECT_ROOT}"
"${PYTHON_BIN}" deploy/release/verify-release.py

[[ -f frontend/dist/index.html ]] || { echo "Prebuilt frontend is missing." >&2; exit 1; }
grep -q '/107-dashboard/assets/' frontend/dist/index.html || {
  echo "Prebuilt frontend has the wrong public path." >&2
  exit 1
}

if [[ ! -d backend/.venv ]]; then
  "${PYTHON_BIN}" -m venv backend/.venv
fi
backend/.venv/bin/python -m pip install -r backend/requirements.txt

if [[ "${RUN_TESTS}" == true ]]; then
  backend/.venv/bin/python -m ruff check backend/app backend/tests
  backend/.venv/bin/python -m pytest -q backend/tests
fi

if [[ -e "${TEST_PROJECT_DIRECTORY}" && "${REFRESH_TEST_PROJECTS}" == true ]]; then
  backup="${TEST_PROJECT_DIRECTORY}.backup-$(date -u +%Y%m%dT%H%M%SZ)"
  mv "${TEST_PROJECT_DIRECTORY}" "${backup}"
  echo "Previous test projects moved to ${backup}"
fi
if [[ ! -e "${TEST_PROJECT_DIRECTORY}" ]]; then
  mkdir -p "${TEST_PROJECT_DIRECTORY}"
  cp -a examples/test-projects/. "${TEST_PROJECT_DIRECTORY}/"
fi
chmod -R go-rwx "${TEST_PROJECT_DIRECTORY}"

bash scripts/107-dashboard-service.sh configure
if [[ "${START_SERVICE}" == true ]]; then
  bash scripts/107-dashboard-service.sh start
else
  echo "Installation complete. Start with: bash scripts/107-dashboard-service.sh start"
fi
