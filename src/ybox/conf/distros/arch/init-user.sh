#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/entrypoint-common.sh"

current_user="$(id -un)"
# install AUR helper yay (original preference was paru whose development is sporadic)
YAY="yay --noconfirm"
echo_color "$fg_cyan" "Installing AUR helper 'yay'" >> $status_file
export HOME=$(getent passwd "$current_user" | cut -d: -f6)
cd "$HOME"
rm -rf yay
git clone https://aur.archlinux.org/yay.git
cd yay
makepkg --noconfirm -si
cd ..
if [ -n "$EXTRA_PKGS" ]; then
  echo_color "$fg_cyan" "Installing $EXTRA_PKGS" >> $status_file
  $YAY -S --needed $EXTRA_PKGS
fi
orphans=$($YAY -Qdtq)
if [ -n "$orphans" ]; then
  $YAY -Rn $orphans
fi
echo_color "$fg_cyan" "Clearing package cache and updating packages" >> $status_file
yes | yay -Sccd
$YAY -Syu
rm -rf yay "$HOME/.cache/go-build" "$HOME/.config/go"

# add current user to realtime group (if present)
# (does not work with rootless docker and is likely ineffective even if it does seem to work)
#if getent group realtime 2>/dev/null >/dev/null; then
#  echo_color "$fg_cyan" "Adding '$current_user' and root to realtime group" >> $status_file
#  sudo usermod -aG realtime $current_user
#  sudo usermod -aG realtime root
#fi
