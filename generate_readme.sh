#!/usr/bin/env bash
# Generate the bilingual READMEs of this repository with mmg (Multilingual
# Markdown Generator): each README.base.md, at the root or in a module,
# gives README.md in English and README.fr.md in French beside it.
#
# Usage: ./generate_readme.sh [README.base.md ...]
#   Without argument, every README.base.md of the root and of the modules.
#
# mmg is looked up in this order: the MMG variable, the mmg of the PATH,
# then the .venv.erplibre of the ERPLibre checkout this repository sits in,
# found by walking up the parent directories; ERPLIBRE_HOME names that
# checkout when the repository lives elsewhere.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

find_mmg() {
  if [[ -n "${MMG:-}" ]]; then
    echo "${MMG}"
    return
  fi
  if command -v mmg >/dev/null 2>&1; then
    command -v mmg
    return
  fi
  local dir
  for dir in ${ERPLIBRE_HOME:+"${ERPLIBRE_HOME}"} "${REPO_DIR}"; do
    while [[ -n "${dir}" && "${dir}" != "/" ]]; do
      if [[ -x "${dir}/.venv.erplibre/bin/mmg" ]]; then
        echo "${dir}/.venv.erplibre/bin/mmg"
        return
      fi
      dir="$(dirname "${dir}")"
    done
  done
  return 1
}

if ! MMG_BIN="$(find_mmg)"; then
  echo "mmg not found: set MMG or ERPLIBRE_HOME, or install ERPLibre," \
    "whose .venv.erplibre holds mmg." >&2
  exit 1
fi

if [[ $# -gt 0 ]]; then
  BASE_FILES=("$@")
else
  # The root and the modules only: a README.base.md deeper down belongs to
  # a module's own documentation and is listed by hand.
  mapfile -t BASE_FILES < <(
    find "${REPO_DIR}" -maxdepth 2 -name README.base.md -not -path '*/.*' |
      sort
  )
fi

if [[ ${#BASE_FILES[@]} -eq 0 ]]; then
  echo "No README.base.md to generate." >&2
  exit 1
fi

for base_file in "${BASE_FILES[@]}"; do
  if [[ ! -f "${base_file}" ]]; then
    echo "Not a file: ${base_file}" >&2
    exit 1
  fi
  "${MMG_BIN}" --yes "${base_file}"
done
