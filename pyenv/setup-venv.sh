#!/usr/bin/env bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/.."

source "$SCRIPT_DIR/activate.bash"

rm -rf "$SRC_DIR/.venv"
python3 -m pip install --upgrade pip
python3 -m venv "$SRC_DIR/.venv"
source "$SRC_DIR/.venv/bin/activate"

pip3 install --upgrade pip
pip3 install --upgrade -r "$SRC_DIR/requirements.txt"
pip3 install --upgrade tox
pip3 cache purge
