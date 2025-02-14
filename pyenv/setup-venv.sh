#!/usr/bin/env bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/.."

source "$SCRIPT_DIR/activate.bash"

(
  cd "$SRC_DIR"
  # skip system python version
  if [ -x "/usr/bin/python3" ]; then
    PYTHON3="/usr/bin/python3"
  elif [ -x "/usr/local/bin/python3" ]; then
    PYTHON3="/usr/local/bin/python3"
  fi
  if [ -n "$PYTHON3" ]; then
    #system_version="$($PYTHON3 --version | sed 's/[^0-9]*\([0-9]*\.[0-9]*\).*/\1/')"
    :
  fi
  all_versions="3.9 3.10 3.11 3.12 3.13"
  req_versions="$(echo "$all_versions" | sed "s/\<$system_version\>//")"
  pyenv install $req_versions || /bin/true
  pyenv local $req_versions || /bin/true
)

rm -rf "$SRC_DIR/.venv"
python3 -m pip install --upgrade pip
python3 -m venv "$SRC_DIR/.venv"
source "$SRC_DIR/.venv/bin/activate"

pip3 install --upgrade pip
pip3 install --upgrade -r "$SRC_DIR/requirements.txt"
pip3 install --upgrade tox
pip3 cache purge
