#!/usr/bin/env bash

set -e

pip install .
if [ -z "$1" -o "$1" = "-u" ]; then
  python3 -m unittest discover -s tests/unit
fi
if [ -z "$1" -o "$1" = "-f" ]; then
  python3 -m unittest discover -s tests/functional
fi
