#!/usr/bin/env bash

set -e

export PYTHONPATH=./src

rm -f .coverage
if [ "$1" = "-f" ]; then
  coverage run -m unittest discover -s tests
else
  coverage run -m unittest discover -s tests/unit
fi

echo
echo "----------------------------------------------------------------------"
echo "                           COVERAGE REPORT"
echo "----------------------------------------------------------------------"
echo
echo "----------------------------------------------------"
coverage report -m | tee coverage-report.txt
