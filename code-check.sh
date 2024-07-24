#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYLINT=
if [ "$1" = "-l" ]; then
  echo -e '\033[35mWill also run pylint on the code\033[00m'
  echo
  PYLINT=1
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
  export PYTHONPATH=./src
  for f in src/ybox/*.py src/ybox/pkg/*.py tests/**/*.py; do
    echo -------------------------------------------
    echo -------------------------------------------
    echo
    echo Output of pylint on $f
    echo
    echo -------------------------------------------
    echo -------------------------------------------
    pylint $f
    exit_code=$?
    if [ $exit_code -ne 0 ]; then
      PYLINT_FAILED=1
    fi
  done
  for f in src/ybox/run/*.py src/ybox/conf/distros/*/*.py; do
    echo -------------------------------------------
    echo -------------------------------------------
    echo
    echo Output of pylint on $f
    echo
    echo -------------------------------------------
    echo -------------------------------------------
    pylint --module-rgx='[a-z][a-z0-9\-]*[a-z0-9]' $f
    exit_code=$?
    if [ $exit_code -ne 0 ]; then
      PYLINT_FAILED=1
    fi
  done
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
