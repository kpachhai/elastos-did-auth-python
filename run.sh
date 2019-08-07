#!/bin/sh

HERE="$(readlink -f $(dirname $0))"
export PYTHONPATH="${HERE}/vendorlib:${PYTHONPATH}"

exec python -m didauth -- "$@"