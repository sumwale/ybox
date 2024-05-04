#!/bin/bash

PYLINT=
if [ "$1" = "-l" ]; then
  echo -e '\033[35mWill also run pylint on the code\033[00m'
  echo
  PYLINT=1
fi

export MYPYPATH=./src
for f in src/ybox/*.py src/ybox/pkg/*.py src/ybox/run/*.py; do
  echo -------------------------------------------
  echo Output of mypy on $f
  echo -------------------------------------------
  mypy --check-untyped-defs $f
done
for f in src/ybox/conf/distros/*/*.py; do
  echo -------------------------------------------
  echo Output of mypy on $f
  echo -------------------------------------------
  ( cd $(dirname "$f") && mypy --check-untyped-defs $(basename "$f") )
done


if [ -n "$PYLINT" ]; then
  export PYTHONPATH=./src
  for f in src/ybox/*.py src/ybox/pkg/*.py; do
    echo -------------------------------------------
    echo -------------------------------------------
    echo
    echo Output of pylint on $f
    echo
    echo -------------------------------------------
    echo -------------------------------------------
    pylint $f
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
  done
fi
