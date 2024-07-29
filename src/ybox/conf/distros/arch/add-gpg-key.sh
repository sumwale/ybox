#!/bin/bash

# this script adds a GPG/PGP key to pacman which can be either a key ID
# or a URL having the key file

set -e

# ensure that system path is always searched first for all the system utilities
export PATH="/usr/sbin:/usr/bin:/sbin:/bin:$PATH"

KEY="$1"
KEY_SERVER="$2"

if [[ "$KEY" == *"://"* ]]; then
  # key is a URL
  key_file="$(mktemp /tmp/gpg-key-XXXXXXXXXX)"
  wget "$KEY" -O "$key_file"
  KEYIDS="$(gpg --show-keys --with-colons "$key_file" | sed -n 's/^fpr:*\([^:]*\).*/\1/p')"
  sudo pacman-key --add "$key_file"
  rm -f "$key_file"
else
  KEYIDS="$KEY"
  if [ -z "$KEY_SERVER" ]; then
    sudo pacman-key --recv-keys $KEYIDS
  else
    sudo pacman-key --keyserver "$KEY_SERVER" --recv-keys $KEYIDS
  fi
fi

for keyid in $KEYIDS; do
  sudo pacman-key --lsign-key $keyid
done
echo "KEYID=$KEYIDS"

exit 0
