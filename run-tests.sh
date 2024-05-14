#!/usr/bin/env bash

set -e

pip install .
python3 -m unittest discover -s tests/unit
python3 -m unittest discover -s tests/functional
