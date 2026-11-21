#!/usr/bin/env sh
cd "$(dirname "$0")"
python3 -m odw2json run "$@"
