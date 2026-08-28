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

for command in "${PYTHON_BIN}" git tmux sbatch scancel squeue sacct sha256sum flock; do
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

if [[ ! -e "${PROJECT_ROOT}/data" ]]; then
  mkdir -p "${PROJECT_ROOT}/data"
fi
RUNTIME_DIRECTORY="$(cd "${PROJECT_ROOT}/data" && pwd -P)"
VENV_CACHE_ROOT="${RUNTIME_DIRECTORY}/python-venvs"
REQUIREMENTS_HASH="$(sha256sum backend/requirements.txt | awk '{print $1}')"
[[ "${REQUIREMENTS_HASH}" =~ ^[a-f0-9]{64}$ ]] || {
  echo "Could not calculate a valid requirements hash." >&2
  exit 1
}

VENV_LINK="${PROJECT_ROOT}/backend/.venv"
CACHED_VENV="${VENV_CACHE_ROOT}/${REQUIREMENTS_HASH}"
ACTIVE_VENV="${CACHED_VENV}"

# A standalone install may already have a real backend/.venv. Keep using it for
# compatibility, while new versioned releases use the persistent runtime cache.
if [[ -d "${VENV_LINK}" && ! -L "${VENV_LINK}" ]]; then
  ACTIVE_VENV="${VENV_LINK}"
elif [[ -L "${VENV_LINK}" ]]; then
  linked_venv="$(readlink -f "${VENV_LINK}" 2>/dev/null || true)"
  if [[ "${linked_venv}" != "${CACHED_VENV}" ]]; then
    rm -f -- "${VENV_LINK}"
  fi
fi

mkdir -p "${VENV_CACHE_ROOT}"
exec 8>"${VENV_CACHE_ROOT}/install.lock"
flock -x 8

venv_matches_requirements() {
  local venv_directory="$1"
  [[ -x "${venv_directory}/bin/python" ]] || return 1
  [[ -f "${venv_directory}/.requirements.sha256" ]] || return 1
  [[ "$(tr -d '\r\n' <"${venv_directory}/.requirements.sha256")" == "${REQUIREMENTS_HASH}" ]] || return 1
  "${venv_directory}/bin/python" -m pip check >/dev/null 2>&1
}

if venv_matches_requirements "${ACTIVE_VENV}"; then
  echo "Python dependencies unchanged; reusing cached virtual environment."
else
  echo "Python dependency cache is missing or stale; installing requirements."
  if [[ "${ACTIVE_VENV}" == "${CACHED_VENV}" ]]; then
    venv_stage="$(mktemp -d "${VENV_CACHE_ROOT}/.staging-${REQUIREMENTS_HASH}.XXXXXX")"
    cleanup_venv_stage() {
      if [[ -n "${venv_stage:-}" && -d "${venv_stage}" ]]; then
        rm -rf -- "${venv_stage}"
      fi
    }
    trap cleanup_venv_stage EXIT
    "${PYTHON_BIN}" -m venv "${venv_stage}"
    "${venv_stage}/bin/python" -m pip install --quiet --disable-pip-version-check --no-input -r backend/requirements.txt
    "${venv_stage}/bin/python" -m pip check
    printf '%s\n' "${REQUIREMENTS_HASH}" >"${venv_stage}/.requirements.sha256"
    rm -rf -- "${CACHED_VENV}"
    mv -- "${venv_stage}" "${CACHED_VENV}"
    venv_stage=""
  else
    "${PYTHON_BIN}" -m venv "${ACTIVE_VENV}"
    "${ACTIVE_VENV}/bin/python" -m pip install --quiet --disable-pip-version-check --no-input -r backend/requirements.txt
    "${ACTIVE_VENV}/bin/python" -m pip check
    printf '%s\n' "${REQUIREMENTS_HASH}" >"${ACTIVE_VENV}/.requirements.sha256"
  fi
fi

if [[ "${ACTIVE_VENV}" == "${CACHED_VENV}" && ! -L "${VENV_LINK}" ]]; then
  ln -s "${CACHED_VENV}" "${VENV_LINK}"
fi
exec 8>&-

if [[ "${RUN_TESTS}" == true ]]; then
  echo "Running backend checks..."
  test_output="$(mktemp)"
  if ! {
    backend/.venv/bin/python -m ruff check backend/app backend/tests
    backend/.venv/bin/python -m pytest -q backend/tests
  } >"${test_output}" 2>&1; then
    cat "${test_output}" >&2
    rm -f -- "${test_output}"
    exit 1
  fi
  tail -n 1 "${test_output}"
  rm -f -- "${test_output}"
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
