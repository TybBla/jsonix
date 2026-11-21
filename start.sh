#!/usr/bin/env sh
# jsonix - wsad: python -m odw2json run [input] [output]. Linux/macOS (na Windows: start.bat).
# Wybiera Pythona 3.13+ (najpierw 3.13 i 3.14, dla ktorych sa paczki OCR); zmienna PYTHON wymusza interpreter.
cd "$(dirname "$0")" || exit 1

ok() { "$1" -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 13) else 1)" >/dev/null 2>&1; }

PY=""
for cand in ${PYTHON:-} python3.13 python3.14 python3 python; do
  command -v "$cand" >/dev/null 2>&1 || continue
  # python3 bywa atrapa (np. stub Microsoft Store na Windows) - ok() sprawdza, czy naprawde dziala.
  if ok "$cand"; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  echo "start.sh: nie znaleziono Pythona 3.13 lub nowszego (zainstaluj 3.13 albo 3.14)" >&2
  exit 1
fi
if ! "$PY" -c "import sys; sys.exit(0 if sys.version_info[:2] < (3, 15) else 1)" >/dev/null 2>&1; then
  echo "start.sh: UWAGA - Python nowszy niz 3.14: OCR skanow niedostepny (brak paczek onnxruntime)" >&2
fi
"$PY" -m odw2json run "$@"
