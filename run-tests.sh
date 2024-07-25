#!/usr/bin/env bash

set -e

pip install .
if [ "$1" = "-u" ]; then
  python3 -m unittest discover -s tests/unit
else
  python3 -m unittest discover -s tests
fi
