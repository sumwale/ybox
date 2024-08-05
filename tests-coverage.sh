#!/usr/bin/env bash

set -e

COV_OPTIONS="--cov=ybox --cov-report=xml:coverage.xml"

rm -f .coverage
if [ "$1" = "-f" ]; then
  shift
  pytest $COV_OPTIONS "$@"
else
  pytest $COV_OPTIONS "$@" tests/unit
fi

coverage report -m | tee coverage-report.txt
