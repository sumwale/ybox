#!/usr/bin/env bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/.."

# install system packages
# (see https://github.com/pyenv/pyenv/wiki#suggested-build-environment)
if type apt 2>/dev/null >/dev/null; then
  sudo apt update
  sudo apt install build-essential curl git
  sudo apt install --mark-auto xz-utils libssl-dev zlib1g-dev libbz2-dev libreadline-dev tk-dev \
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

resp=y
if [ -x "$HOME/.pyenv/bin/pyenv" ]; then
  echo -n "Overwrite existing pyenv? (y/N) "
  read resp
fi
if [ "$resp" = "y" -o "$resp" = "Y" ]; then
  rm -rf "$HOME/.pyenv"
  curl -fsSL https://pyenv.run | bash
fi

source "$SCRIPT_DIR/activate.bash"

(
  cd "$SRC_DIR"
  # skip system python version if required
  if [ -x "/usr/bin/python3" ]; then
    PYTHON3="/usr/bin/python3"
  elif [ -x "/usr/local/bin/python3" ]; then
    PYTHON3="/usr/local/bin/python3"
  fi
  if [ -n "$PYTHON3" ]; then
    system_version="$($PYTHON3 --version | sed 's/[^0-9]*\([0-9]*\.[0-9]*\).*/\1/')"
    echo -n "Skip installation of system python version $system_version? (Y/n) "
    read resp
    if [ "$resp" = "n" -o "$resp" = "N" ]; then
      system_version=
    fi
  fi
  all_versions="3.9 3.10 3.11 3.12 3.13"
  req_versions="$(echo "$all_versions" | sed "s/\<$system_version\>//")"
  pyenv install $req_versions || /bin/true
  pyenv local $req_versions || /bin/true
)
