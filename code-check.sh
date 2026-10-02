#!/bin/sh

set -e

tox -q -p -e flake8,pyright,pylint
