#!/bin/bash -e

python3 -m unittest discover -s tests/unit
python3 -m unittest discover -s tests/functional
