#!/bin/bash -e

# sudo is not present in the upstream archlinux image
pacman -Sy
pacman -S --noconfirm --needed sudo
yes | pacman -Scc >/dev/null 2>/dev/null
