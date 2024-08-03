#!/bin/bash

if [ "$1" = "-l" ]; then
  tox -q -p -e flake8,pyright,pylint
else
  tox -q -p -e flake8,pyright
fi
