#!/bin/bash

set -e

SCRIPT="$(basename "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

copy_docs() {
  if ! type -p mkdocs >/dev/null; then
    pip install .[docs]
    pip cache purge
  fi
  echo "Copying top-level README/LICENSE/PRIVACY files to docs"
  cp README.md docs/index.md
  cp LICENSE.md docs/license.md
  cp PRIVACY.md docs/privacy.md
}

if [ "$1" = "docs-publish" ]; then
  echo "Publishing documentation to GitHub Pages"
  ( cd "$SCRIPT_DIR" && copy_docs && mkdocs gh-deploy --force )
elif [ "$1" = "docs-serve" ]; then
  ( cd "$SCRIPT_DIR" && copy_docs && mkdocs serve ) &
  childPID=$!
  trap "kill -1 $childPID" 1 2 3 6 14 15
  sleep 10
  xdg-open http://127.0.0.1:8000/ybox/
  wait $childPID
elif [ -n "$1" ]; then
  echo "Usage: $SCRIPT [ docs-publish | docs-serve ]"
  exit 1
else
  echo "Building python distribution packages"
  ( cd "$SCRIPT_DIR" && rm -rf dist/ build/ src/*.egg-info && python3 -m build )
fi
