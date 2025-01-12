#!/bin/bash

set -e

# disable the sandbox in the newer pacman versions that does not work in container
sed -i 's/^#[ ]*DisableSandbox/DisableSandbox/' /etc/pacman.conf
# sudo is not present in the upstream archlinux image
pacman -Sy
pacman -S --noconfirm --needed sudo
yes | pacman -Scc 2>/dev/null >/dev/null
