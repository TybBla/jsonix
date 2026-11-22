#!/usr/bin/env bash
# Smoke: swiezy venv + requirements.txt (bez dev) + start.sh na malym wejsciu.
# Dotyczy Linux/macOS (na Windows uzyj scripts/smoke.ps1).
# Uzycie: bash scripts/smoke.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail() { echo "SMOKE FAIL: $*" >&2; exit 1; }

PYBIN="${PYTHON:-python3}"
"$PYBIN" -m venv "$TMP/venv"
VBIN="$TMP/venv/bin"
[ -x "$VBIN/python" ] || VBIN="$TMP/venv/Scripts"
"$VBIN/python" -m pip install --quiet --disable-pip-version-check -r "$REPO/requirements.txt" -c "$REPO/requirements-lock.txt"

IN="$TMP/in"
OUT="$TMP/out"
mkdir -p "$IN/case1" "$OUT"
for n in odwolanie pelnomocnictwo potwierdzenie_przelewu; do
  cp "$REPO/data/train/przyklad_01/$n.pdf" "$IN/case1/$n.pdf"
done
cp "$REPO/data/train/negatywne/KIO_KIO 2617-21.pdf" "$IN/case1/KIO_KIO 2617-21.pdf"

# start.sh robi cd do swojego katalogu -> sciezki musza byc ABSOLUTNE.
# Wywolanie przez `sh`, bo bit wykonywalny moze nie byc ustawiony.
PATH="$VBIN:$PATH" LLM_MODE="${LLM_MODE:-replay}" sh "$REPO/start.sh" "$IN" "$OUT" || fail "start.sh zwrocil blad"

"$VBIN/python" - "$OUT/case1" <<'PY' || fail "asercje wyniku"
import json
import sys
from pathlib import Path

d = Path(sys.argv[1])
files = sorted(d.glob("*.json"))
assert len(files) == 4, f"oczekiwano 4 plikow JSON, jest {len(files)}: {[f.name for f in files]}"
neg = d / "KIO_KIO 2617-21.json"
assert neg.is_file(), "brak JSON dla negatywu"
assert json.loads(neg.read_text(encoding="utf-8")) == {}, "negatyw nie jest {}"
for name, key in [
    ("odwolanie", "OdwolanieKIO"),
    ("pelnomocnictwo", "mocodawca"),
    ("potwierdzenie_przelewu", "przelew_bankowy"),
]:
    data = json.loads((d / f"{name}.json").read_text(encoding="utf-8"))
    assert key in data, f"{name}.json bez klucza {key}"
PY

echo "SMOKE PASS"
