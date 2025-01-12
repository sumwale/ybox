#!/bin/bash

# this script fetches a GPG/PGP key and writes it to an output file given the key ID and key server

set -e

# Check if all arguments are provided
if [ $# -ne 3 ]; then
  echo "Usage: $0 <key ID> <key server> <output key file>"
  exit 1
fi

# ensure that only system paths are searched for all the system utilities
export PATH="/usr/sbin:/usr/bin:/sbin:/bin"

current_user="$(id -un)"
export HOME="$(getent passwd "$current_user" | cut -d: -f6)"
mkdir -p "$HOME/.gnupg"
chmod 0700 "$HOME/.gnupg"

temp_keyring="$(mktemp /tmp/gpg-keyring-XXXXXXXXXX)"

trap "rm -f $temp_keyring ${temp_keyring}~" 0 1 2 3 13 15

# fetch the key from the key server and export to given output key file
GPG_CMD="gpg --no-default-keyring --keyring $temp_keyring"
$GPG_CMD --keyserver "$2" --recv-key "$1"
$GPG_CMD --export --output "$3"

exit 0
