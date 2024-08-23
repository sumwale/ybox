#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/entrypoint-common.sh"

current_user="$(id -un)"
user_home="$(eval echo "~$current_user")"
# set gpg keyserver to an available one
mkdir -p "$user_home/.gnupg"
echo "keyserver $DEFAULT_GPG_KEY_SERVER" > "$user_home/.gnupg/dirmngr.conf"
rm -f "$user_home"/.gnupg/*/*.lock
