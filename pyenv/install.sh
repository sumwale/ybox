#!/usr/bin/env bash

set -e

# install system packages
# (see https://github.com/pyenv/pyenv/wiki#suggested-build-environment)
if type apt 2>/dev/null >/dev/null; then
  sudo apt update
  sudo apt install build-essential curl git xz-utils
  sudo apt install --mark-auto libssl-dev zlib1g-dev libbz2-dev libreadline-dev tk-dev \
    libsqlite3-dev libncursesw5-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev
elif type dnf 2>/dev/null >/dev/null; then
  dnf install make gcc patch zlib-devel bzip2 bzip2-devel readline-devel sqlite \
    sqlite-devel openssl-devel tk-devel libffi-devel xz-devel libuuid-devel gdbm-libs libnsl2
elif type pacman 2>/dev/null >/dev/null; then
  sudo pacman -S --needed base-devel openssl zlib bzip2 xz readline tk sqlite libxml2 pyenv
  exit $?
elif type zypper 2>/dev/null >/dev/null; then
  sudo zypper install gcc automake bzip2 libbz2-devel xz xz-devel openssl-devel ncurses-devel \
    readline-devel zlib-devel tk-devel libffi-devel sqlite3-devel gdbm-devel make findutils patch
elif type brew 2>/dev/null >/dev/null; then
  brew install openssl readline sqlite3 xz zlib tcl-tk@8 pyenv
  exit $?
fi

rm -rf "$HOME/.pyenv"
curl -fsSL https://pyenv.run | bash
