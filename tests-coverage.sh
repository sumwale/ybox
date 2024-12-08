#!/usr/bin/env bash

set -e

COV_OPTIONS="--cov=ybox --cov-report=xml:coverage.xml"

rm -f .coverage converage.xml converage-report.txt
if [ "$1" = "-f" ]; then
  shift
  pytest $COV_OPTIONS --verbose "$@"
else
  pytest $COV_OPTIONS --verbose "$@" tests/unit
fi

coverage report -m | tee coverage-report.txt
