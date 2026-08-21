#!/usr/bin/env bash
#
# Phase 33 · Release build for the AI Assistant browser extension.
#
#   Clean -> TypeScript Build -> MV3 Build -> Validate Manifest
#         -> Validate Required Files -> Security Audit
#         -> Generate ZIP -> Inspect ZIP
#
# Every step is verified and any failure exits non-zero, so a package that is
# missing a runtime file, requests a permission it does not need, or carries a
# .env / API key / database / test / source map can never be published.
#
# The audit rules are NOT re-implemented here: this script calls
# `python -m app.release audit` and `python -m app.release package`, the same
# functions the Phase 33 test suite imports.
#
# Usage:
#   bash release/build-release.sh                 # full release build
#   cd browser-extension && npm run release       # identical, via npm
#   SKIP_NPM_BUILD=1 bash release/build-release.sh  # re-package an existing dist
#
# This script reads the repository, writes only `browser-extension/dist/` and
# `release/AI-Assistant-extension.zip`, and touches nothing else. It never
# uploads, publishes, installs or executes the extension.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
EXTENSION_DIR="${REPO_ROOT}/browser-extension"
BRIDGE_DIR="${REPO_ROOT}/local-bridge"
DIST_DIR="${EXTENSION_DIR}/dist"
RELEASE_DIR="${SCRIPT_DIR}"
ARCHIVE="${RELEASE_DIR}/AI-Assistant-extension.zip"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    echo "FAIL: no python interpreter found (set PYTHON_BIN)" >&2
    exit 1
  fi
fi

step=0
say() { printf '\n=== [%d/8] %s ===\n' "$1" "$2"; }
fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }

# The auditors live in the Bridge package, so they run with `local-bridge` as the
# working directory. They are stdlib-only: no Bridge dependency needs installing.
audit() { ( cd "${BRIDGE_DIR}" && "${PYTHON_BIN}" -m app.release audit "$@" ); }
package_zip() { ( cd "${BRIDGE_DIR}" && "${PYTHON_BIN}" -m app.release package "$@" ); }

# 1. Clean -------------------------------------------------------------------
step=1; say "${step}" "Clean"
rm -rf "${DIST_DIR}"
rm -f "${ARCHIVE}" "${ARCHIVE}.partial"
mkdir -p "${RELEASE_DIR}"
echo "removed dist/ and any previous release archive"

# 2 + 3. TypeScript build and MV3 build --------------------------------------
# `npm run build` is the existing build system: `tsc --noEmit` first, then one
# Vite pass per MV3 entry point (content script, service worker).
if [[ "${SKIP_NPM_BUILD:-0}" == "1" ]]; then
  step=2; say "${step}" "TypeScript Build (skipped: SKIP_NPM_BUILD=1)"
  step=3; say "${step}" "MV3 Build (skipped: SKIP_NPM_BUILD=1)"
else
  step=2; say "${step}" "TypeScript Build"
  ( cd "${EXTENSION_DIR}" && npx tsc --noEmit ) || fail "TypeScript build failed"

  step=3; say "${step}" "MV3 Build"
  ( cd "${EXTENSION_DIR}" && CCB_TARGET=content npx vite build ) || fail "content script build failed"
  ( cd "${EXTENSION_DIR}" && CCB_TARGET=background npx vite build ) || fail "service worker build failed"
fi

[[ -d "${DIST_DIR}" ]] || fail "build produced no dist/ directory"

# 4. Validate manifest -------------------------------------------------------
step=4; say "${step}" "Validate Manifest"
audit --manifest "${DIST_DIR}/manifest.json" \
  || fail "manifest audit failed (see findings above)"

# 5. Validate required runtime files -----------------------------------------
step=5; say "${step}" "Validate Required Files"
missing=0
for required in manifest.json content/content.js background/service-worker.js; do
  if [[ -f "${DIST_DIR}/${required}" ]]; then
    echo "  ok  ${required}"
  else
    echo "  MISSING  ${required}" >&2
    missing=1
  fi
done
[[ "${missing}" -eq 0 ]] || fail "a required runtime file is missing from dist/"

# 6. Security audit of the build directory -----------------------------------
step=6; say "${step}" "Security Audit"
audit --dir "${DIST_DIR}" --list-entries \
  || fail "build directory audit failed (see findings above)"

# 7. Generate the ZIP --------------------------------------------------------
# The packager audits the directory again before writing, audits the finished
# archive afterwards, and deletes the archive if either audit finds something.
step=7; say "${step}" "Generate ZIP"
package_zip --source "${DIST_DIR}" --output "${ARCHIVE}" \
  || fail "release packaging failed (see findings above)"

# 8. Inspect the finished ZIP ------------------------------------------------
step=8; say "${step}" "Inspect ZIP"
[[ -f "${ARCHIVE}" ]] || fail "release zip was not created"
audit --zip "${ARCHIVE}" --list-entries \
  || fail "release zip audit failed (see findings above)"

size="$(wc -c < "${ARCHIVE}" | tr -d ' ')"

cat <<EOF

=== Release build complete ===
archive : ${ARCHIVE}
bytes   : ${size}
contents: manifest.json, content/content.js, background/service-worker.js
next    : follow release/INSTALL.md to load it in Chrome or Edge

Reminder: the ZIP is the extension only. It ships no API key, no .env, no
database and no workspace data, and installing it grants no execution rights —
every change still goes through Tool Proposal -> ApprovalStore -> human approval.
EOF
