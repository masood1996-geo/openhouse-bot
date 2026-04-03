#!/bin/bash

set -u

pip install -e . || true
pip install pylint

pylint openhouse/
pylint_runner_exit_code=$?

if [ $(( $pylint_runner_exit_code & 32 )) != 0 ] || # usage error
   [ $(( $pylint_runner_exit_code & 2 )) != 0 ] ||  # error message issued
   [ $(( $pylint_runner_exit_code & 1 )) != 0 ]     # fatal message issued
then
  echo "Failed because of exit code $pylint_runner_exit_code"
  echo "(See https://pylint.pycqa.org/en/latest/user_guide/usage/run.html#exit-codes)"
  exit $pylint_runner_exit_code
fi

echo "Ran successfully (exit code was $pylint_runner_exit_code)"
exit 0
