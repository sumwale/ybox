#!/bin/bash

PYLINT=
if [ "$1" = "-l" ]; then
  echo -e '\033[35mWill also run pylint on the code\033[00m'
  echo
  PYLINT=1
fi

MYPY_FAILED=
PYLINT_FAILED=

export MYPYPATH=./src
for f in src/ybox/*.py src/ybox/pkg/*.py src/ybox/run/*.py tests/**/*.py; do
  echo -------------------------------------------
  echo Output of mypy on $f
  echo -------------------------------------------
  mypy --check-untyped-defs $f
  exit_code=$?
  if [ $exit_code -ne 0 ]; then
    MYPY_FAILED=1
  fi
done
for f in src/ybox/conf/distros/*/*.py; do
  echo -------------------------------------------
  echo Output of mypy on $f
  echo -------------------------------------------
  ( cd $(dirname "$f") && mypy --check-untyped-defs $(basename "$f") )
  exit_code=$?
  if [ $exit_code -ne 0 ]; then
    MYPY_FAILED=1
  fi
done


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
if [ -n "$MYPY_FAILED" ]; then
  echo
  echo -e '\033[31mFailure(s) in mypy run -- see the output above.'
  exit_code=1
fi
if [ -n "$PYLINT_FAILED" ]; then
  echo
  echo -e '\033[31mFailure(s) in pylint run -- see the output above.'
  exit_code=1
fi

exit $exit_code
