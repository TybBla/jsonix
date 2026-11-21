#!/usr/bin/env sh
cd "$(dirname "$0")" || exit 1
PY=$(command -v python3 || command -v python) || {
  echo "start.sh: nie znaleziono python3 ani python" >&2
  exit 1
}
# python3 bywa atrapa (np. stub Microsoft Store na Windows) - sprawdz, czy dziala.
if ! "$PY" -c "import sys" >/dev/null 2>&1; then
  PY=$(command -v python) || {
    echo "start.sh: python3 nie dziala, a python nie istnieje" >&2
    exit 1
  }
fi
"$PY" -m odw2json run "$@"
