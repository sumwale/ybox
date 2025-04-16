#!/bin/bash

set -e

SCRIPT="$(basename "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/entrypoint-common.sh"

function show_usage() {
  echo
  echo "Usage: $SCRIPT SHARED_DIRS SHARED_BIND"
  echo
  echo "Arguments:"
  echo "  SHARED_DIRS     comma separated list of directories to share among containers"
  echo "  SHARED_BIND     shared bind mount where the DIRS above will be copied"
}

if [ $# -ne 2 ]; then
  show_usage
  exit 1
fi

shared_dirs="$1"
shared_bind="$2"

echo_color "$fg_purple" "Copying data from container to shared root mounted on '$shared_bind'"
IFS="," read -ra shared_dirs_arr <<< "$shared_dirs"
for dir in "${shared_dirs_arr[@]}"; do
  echo_color "$fg_orange" "Copying $dir to $shared_bind$dir"
  cp -an "$dir" "$shared_bind$dir"
done
