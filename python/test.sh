#!/usr/bin/env sh

ARGS="$@"

[ -z "$ARGS" ] && ARGS="discover"

python -m unittest "$ARGS"
