#!/bin/bash

set -e

tox -q -p -e flake8,pyright,pylint
