#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/entrypoint-common.sh"

current_user="$(id -un)"
# install binaries for paru from paru-bin (paru takes too long to compile)
PARU="paru --noconfirm"
echo_color "$fg_cyan" "Installing AUR helper 'paru'" >> $status_file
export HOME=$(getent passwd "$current_user" | cut -d: -f6)
cd "$HOME"
rm -rf paru-bin
git clone https://aur.archlinux.org/paru-bin.git
cd paru-bin
makepkg --noconfirm -si
cd ..
if [ -n "$EXTRA_PKGS" ]; then
  echo_color "$fg_cyan" "Installing $EXTRA_PKGS" >> $status_file
  $PARU -S --needed $EXTRA_PKGS
fi
echo_color "$fg_cyan" "Clearing package cache and updating packages" >> $status_file
yes | paru -Sccd
$PARU -Syu
rm -rf paru-bin

# add current user to realtime group (if present)
# (does not work with rootless docker and is likely ineffective even if it does seem to work)
#if getent group realtime 2>/dev/null >/dev/null; then
#  echo_color "$fg_cyan" "Adding '$current_user' and root to realtime group" >> $status_file
#  sudo usermod -aG realtime $current_user
#  sudo usermod -aG realtime root
#fi
