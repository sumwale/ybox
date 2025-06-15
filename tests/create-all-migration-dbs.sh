#!/bin/bash

# create test migration databases for all versions listed in test_state.py#test_migration

set -e

# use only standard system paths for all utilities
export PATH="/usr/sbin:/usr/bin:/sbin:/bin"

SCRIPT="$(basename "${BASH_SOURCE[0]}")"
PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"

# keep this in sync with the list in test_state.py#test_migration
all_versions="0.9.0 0.9.1 0.9.2 0.9.5 0.9.6 0.9.7 0.9.10"

# checkout the repository in a temporary path
tmp_co_dir="$PROJ_DIR/tmp-ybox"
rm -rf "$tmp_co_dir" && mkdir -p "$tmp_co_dir"
git clone https://github.com/sumwale/ybox.git "$tmp_co_dir/"

pushd "$tmp_co_dir"
rm -f "$PROJ_DIR/tests/resources/migration"/*

# for all versions, checkout the tag, copy latest test artifacts and profiles used by
# test_migration, and run the create_migration_db.py script to create the db for the tag
for ver in $all_versions; do
  git reset --hard
  rm -rf tests src/ybox/conf/profiles
  git checkout v$ver
  rm -rf tests src/ybox/conf/profiles
  cp -r "$PROJ_DIR/tests" tests
  cp -r "$PROJ_DIR/src/ybox/conf/profiles" src/ybox/conf/profiles
  find . -name __pycache__ -type d -print0 | xargs -0 -r rm -rf
  echo
  echo "Creating test migration database for ybox version:"
  tail -n1 src/ybox/__init__.py
  echo
  PYTHONPATH=./src python3 ./tests/create_migration_db.py "$PROJ_DIR/tests/resources/migration/"
done

popd
rm -rf "$tmp_co_dir"

exit 0
