#!/bin/bash

set -e

# this script has actions that need to be run as root

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/entrypoint-common.sh"

echo_color "$fg_cyan" "Copying prime-run, run-in-dir and run-user-bash-cmd" >> $status_file
cp -a "$SCRIPT_DIR/prime-run" /usr/local/bin/prime-run
cp -a "$SCRIPT_DIR/run-in-dir" /usr/local/bin/run-in-dir
cp -a "$SCRIPT_DIR/run-user-bash-cmd" /usr/local/bin/run-user-bash-cmd
chmod 0755 /usr/local/bin/prime-run /usr/local/bin/run-in-dir /usr/local/bin/run-user-bash-cmd

# invoke the NVIDIA setup script if present
if [ -r "$SCRIPT_DIR/nvidia-setup.sh" ]; then
  /bin/bash "$SCRIPT_DIR/nvidia-setup.sh"
fi
