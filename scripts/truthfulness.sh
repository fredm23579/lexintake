#!/usr/bin/env sh
set -eu
python3 scripts/check_truthfulness.py
python3 -m pytest
