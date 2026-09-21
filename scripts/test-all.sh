#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for skill_dir in "$repo_dir"/skills/*; do
  if [[ ! -d "$skill_dir/tests" ]]; then
    continue
  fi

  printf 'Testing %s\n' "$(basename "$skill_dir")"
  (
    cd "$skill_dir"
    python3 -m py_compile scripts/*.py tests/*.py
    python3 -m unittest discover -s tests -v
  )
done

