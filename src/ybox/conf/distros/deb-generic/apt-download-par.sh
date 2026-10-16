#!/bin/bash

#
# Script to download given package files in parallel (specified by --jobs=N option with default
#   of 8). Both Debian and Ubuntu default repositories point to generic URLs that resolve as per
# geo-location and/or load, so parallel has a significant improvement in download speeds.
# This does not perform any package validation which is supposed to be done by a subsequent
# apt/apt-get invocation.
#

set -e
set -o pipefail

# ensure that only system paths are searched for all the system utilities
export PATH="/usr/sbin:/usr/bin:/sbin:/bin"

[ $(id -u) -ne 0 ] && { echo "This utility should be run as root" >&2; exit 1; }

function usage() {
  echo "Usage: $0 [--jobs N] package [package ...]" >&2
  exit 1
}

jobs=8  # default is 8 splits
if [ "$1" == "--jobs" ]; then
  [ $# -lt 2 ] && usage
  jobs="$2"
  [[ "$jobs" =~ ^[1-9][0-9]*$ ]] || { echo "Job count must be a positive integer" >&2; usage; }
  shift 2
fi
[ $# -lt 1 ] && usage

archives=/var/cache/apt/archives
partial="$archives/partial"
[ ! -d "$partial" ] && mkdir -p -m 0700 "$partial"

function fetch_debs() {
  declare -A url_names
  while (( $# )); do
    url_names["$1"]="$2"
    shift 2
  done

  wget -q --show-progress -c -P "$partial" "${!url_names[@]}" || return
  for url in "${!url_names[@]}"; do
    url_name="${url##*/}"
    printf -v url_name '%b' "${url_name//%/\\x}"  # percent decode
    mv "$partial/$url_name" "$archives/${url_names[$url]}"
  done
}
export -f fetch_debs
export archives partial

apt-get install --reinstall --print-uris -qq "$@" \
  | sed -nE "s/^'([^']+)'[[:space:]]+([^[:space:]]+).*/\1\n\2/p" \
  | xargs -d'\n' -P$jobs -L20 -r bash -c 'fetch_debs "$@"' _
