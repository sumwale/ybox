#!/bin/bash

# this script fetches a GPG/PGP key file from a URL and adds the key to pacman

set -e

# Check if all arguments are provided
if [ $# -ne 1 ]; then
  echo "Usage: $0 <url>"
  exit 1
fi

# ensure that only system paths are searched for all the system utilities
export PATH="/usr/sbin:/usr/bin:/sbin:/bin"

file="$(mktemp /tmp/gpg-key-XXXXXXXXXX)"

trap "rm -f $file" 0 1 2 3 15

curl -sSL "$1" -o "$file"
KEYIDS="$(gpg --show-keys --with-colons "$file" | sed -n 's/^fpr:*\([^:]*\).*/\1/p' | tr '\n' ' ')"
sudo pacman-key --add "$file"

for keyid in $KEYIDS; do
  sudo pacman-key --lsign-key $keyid
done
echo "KEYID=$KEYIDS"

exit 0
