#!/bin/bash

set -e

# sudo is not present in the upstream archlinux image
pacman -Sy
pacman -S --noconfirm --needed sudo
yes | pacman -Scc 2>/dev/null >/dev/null
