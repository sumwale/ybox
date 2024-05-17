#!/bin/bash -e

# this script has actions that need to be run as root

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

source "$SCRIPT_DIR/entrypoint-common.sh"

echo_color "$fg_cyan" "Copying prime-run and run-in-dir" >> $status_file
cp -a "$SCRIPT_DIR/prime-run" /usr/local/bin/prime-run
cp -a "$SCRIPT_DIR/run-in-dir" /usr/local/bin/run-in-dir
chmod 0755 /usr/local/bin/prime-run /usr/local/bin/run-in-dir
