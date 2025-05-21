#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/entrypoint-common.sh"

current_user="$(id -un)"
user_home="$(getent passwd "$current_user" | cut -d: -f6)"
# set gpg keyserver to an available one
mkdir -p "$user_home/.gnupg" && chmod 0700 "$user_home/.gnupg"
echo "keyserver $DEFAULT_GPG_KEY_SERVER" > "$user_home/.gnupg/dirmngr.conf" || /bin/true
rm -f "$user_home"/.gnupg/*/*.lock

if [ ! -e "$user_home/.config/pip/pip.conf" ]; then
  echo_color "$fg_cyan" "Enabling python pip installation for $current_user" >> $status_file
  mkdir -p "$user_home/.config/pip"
  cat > "$user_home/.config/pip/pip.conf" << EOF
[global]
break-system-packages = true
EOF
fi
