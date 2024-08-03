#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYLINT=
if [ "$1" = "-l" ]; then
  echo Will also run pylint on the code
  echo
  PYLINT="pylint -j8"
fi

PYRIGHT_FAILED=
FLAKE8_FAILED=
PYLINT_FAILED=

echo -------------------------------------------
echo Output of pyright
echo -------------------------------------------
pyright
exit_code=$?
if [ $exit_code -ne 0 ]; then
  PYRIGHT_FAILED=1
fi

echo -------------------------------------------
echo Output of flake8
echo -------------------------------------------
flake8 src tests
exit_code=$?
if [ $exit_code -ne 0 ]; then
  FLAKE8_FAILED=1
fi

if [ -n "$PYLINT" ]; then
  echo -------------------------------------------
  echo Output of pylint
  echo -------------------------------------------
  export PYTHONPATH=./src:./tests
  $PYLINT src/ybox tests
  exit_code=$?
  if [ $exit_code -ne 0 ]; then
    PYLINT_FAILED=1
  fi
  $PYLINT src/ybox/conf/distros/*/*.py
  exit_code=$?
  if [ $exit_code -ne 0 ]; then
    PYLINT_FAILED=1
  fi
fi

exit_code=0
if [ -n "$PYRIGHT_FAILED" ]; then
  echo
  echo -e '\033[31mFailure(s) in pyright run -- see the output above.'
  exit_code=1
fi
if [ -n "$FLAKE8_FAILED" ]; then
  echo
  echo -e '\033[31mFailure(s) in flake8 run -- see the output above.'
  exit_code=1
fi
if [ -n "$PYLINT_FAILED" ]; then
  echo
  echo -e '\033[31mFailure(s) in pylint run -- see the output above.'
  exit_code=1
fi

exit $exit_code
