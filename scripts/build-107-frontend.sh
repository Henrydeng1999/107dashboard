#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_ROOT="${PROJECT_ROOT}/frontend"
STAGING_DIRECTORY="${FRONTEND_ROOT}/dist.107-staging"
DIST_DIRECTORY="${FRONTEND_ROOT}/dist"

cleanup() {
  rm -rf "${STAGING_DIRECTORY}"
}
trap cleanup EXIT

cd "${FRONTEND_ROOT}"
rm -rf "${STAGING_DIRECTORY}"
npx tsc -b
npx vite build --mode navigation --base=/107-dashboard/ \
  --outDir "${STAGING_DIRECTORY}" --emptyOutDir

grep -q '/107-dashboard/assets/' "${STAGING_DIRECTORY}/index.html" || {
  echo "107 frontend build is missing the /107-dashboard/assets/ prefix." >&2
  exit 1
}
grep -Rqs '/107-dashboard/api' "${STAGING_DIRECTORY}/assets" || {
  echo "107 frontend build is missing the /107-dashboard/api prefix." >&2
  exit 1
}
if grep -RqsE 'https?://(localhost|127\.0\.0\.1):[0-9]+/api' "${STAGING_DIRECTORY}"; then
  echo "107 frontend build contains a development API address." >&2
  exit 1
fi

rm -rf "${DIST_DIRECTORY}"
mv "${STAGING_DIRECTORY}" "${DIST_DIRECTORY}"
trap - EXIT
echo "107 frontend release build validated and installed in ${DIST_DIRECTORY}."
