#!/usr/bin/env bash
# Wdrożenie jsonix na VM jury (Azure, Ubuntu 24.04) - uruchamiać NA VM, jako zwykły użytkownik z sudo/docker.
#
#   bash scripts/deploy-vm.sh                 # klon/aktualizacja repo, docker build, kopia RUN.md
#   bash scripts/deploy-vm.sh --self-test     # test na PDF-ach z data/train w katalogach tymczasowych
#   bash scripts/deploy-vm.sh --check-real    # RUN.md na tym, co leży w /opt/solution/input (jak u jury)
#   bash scripts/deploy-vm.sh --deploy --self-test   # kilka akcji naraz (bez flag = tylko --deploy)
#
# Opcje: --repo URL (albo REPO_URL), --branch NAZWA (albo BRANCH, domyślnie main),
#        SOLUTION_DIR (domyślnie /opt/solution). Skrypt NIE usuwa i NIE czyści input/ ani output/.
set -euo pipefail

SOLUTION_DIR="${SOLUTION_DIR:-/opt/solution}"
REPO_URL="${REPO_URL:-https://github.com/TybBla/HackNation-Project.git}"
BRANCH="${BRANCH:-main}"
IMAGE="jsonix:latest"
REPO_DIR="$SOLUTION_DIR/repo"

do_deploy=0 do_self=0 do_real=0
while [ $# -gt 0 ]; do
    case "$1" in
        --deploy) do_deploy=1 ;;
        --self-test) do_self=1 ;;
        --check-real) do_real=1 ;;
        --repo) REPO_URL="${2:?--repo wymaga adresu}"; shift ;;
        --branch) BRANCH="${2:?--branch wymaga nazwy}"; shift ;;
        -h | --help) sed -n '2,11p' "$0"; exit 0 ;;
        *) echo "Nieznana opcja: $1" >&2; exit 2 ;;
    esac
    shift
done
if [ $((do_deploy + do_self + do_real)) -eq 0 ]; then do_deploy=1; fi

# jury uruchamia komendę z sudo, więc testy też (docker bywa dostępny tylko przez sudo)
SUDO=""
if [ "$(id -u)" -ne 0 ]; then SUDO="sudo"; fi

say() { printf '\n== %s\n' "$*"; }
die() { echo "BŁĄD: $*" >&2; exit 1; }

command -v docker >/dev/null || die "brak docker"
command -v git >/dev/null || die "brak git"
PY=""
for cand in python3 python; do
    if "$cand" -c 'import json' >/dev/null 2>&1; then PY="$cand"; break; fi
done

# Pierwsza komenda z bloku kodu na górze RUN.md (jedna linia).
run_command() {
    awk '/^```/ { if (inblock) exit; inblock = 1; next } inblock { print; exit }' "$1"
}

run_timed() { # run_timed <komenda> -> wypisuje czas, zwraca kod wyjścia komendy
    local cmd="$1" t0 t1 rc=0
    t0=$(date +%s)
    # shellcheck disable=SC2086
    $SUDO bash -c "$cmd" || rc=$?
    t1=$(date +%s)
    echo "Kod wyjścia: $rc, czas: $((t1 - t0)) s"
    return "$rc"
}

deploy() {
    say "Repo: $REPO_URL ($BRANCH) -> $REPO_DIR"
    $SUDO mkdir -p "$SOLUTION_DIR"
    if [ -d "$REPO_DIR/.git" ]; then
        $SUDO git -C "$REPO_DIR" fetch --prune origin
        $SUDO git -C "$REPO_DIR" checkout "$BRANCH"
        $SUDO git -C "$REPO_DIR" reset --hard "origin/$BRANCH"
    else
        $SUDO git clone --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
    fi
    $SUDO git -C "$REPO_DIR" log --oneline -1

    say "docker build -t $IMAGE"
    $SUDO docker build -t "$IMAGE" "$REPO_DIR"

    say "RUN.md -> $SOLUTION_DIR/RUN.md"
    $SUDO cp "$REPO_DIR/RUN.md" "$SOLUTION_DIR/RUN.md"
    $SUDO mkdir -p "$SOLUTION_DIR/input" "$SOLUTION_DIR/output"  # nic nie kasujemy
    echo "Komenda jury: $(run_command "$SOLUTION_DIR/RUN.md")"
}

self_test() {
    local run_md="$REPO_DIR/RUN.md" train="$REPO_DIR/data/train"
    [ -f "$run_md" ] || die "brak $run_md (najpierw: bash scripts/deploy-vm.sh)"
    [ -d "$train" ] || die "brak $train"
    [ -n "$PY" ] || die "brak python3 do sprawdzenia JSON-ów"
    local tmp in out cmd
    tmp="$(mktemp -d)"
    in="$tmp/input"; out="$tmp/output"
    mkdir -p "$in" "$out"
    # dokumenty z warstwą tekstu (sprawa przyklad_01), negatyw i skan (OCR)
    mkdir -p "$in/przyklad_01" "$in/negatywne" "$in/skan_pelnomocnictwo"
    cp "$train"/przyklad_01/*.pdf "$in/przyklad_01/"
    cp "$(find "$train/negatywne" -maxdepth 1 -name '*.pdf' | sort | sed -n 1p)" "$in/negatywne/"
    local scan
    scan="$(find "$train/skany/pelnomocnictwa" -name '*.pdf' | sort | sed -n 1p)"
    [ -n "$scan" ] || die "brak skanu w $train/skany"
    cp "$scan" "$in/skan_pelnomocnictwo/"
    local n_pdf
    n_pdf="$(find "$in" -name '*.pdf' | wc -l)"
    echo "Wejście: $n_pdf PDF w $in"

    # DOKŁADNIE komenda z RUN.md, tylko ścieżki montowania podmienione na katalogi tymczasowe
    cmd="$(run_command "$run_md")"
    [ -n "$cmd" ] || die "nie znaleziono komendy w $run_md"
    cmd="${cmd//\/opt\/solution\/input/$in}"
    cmd="${cmd//\/opt\/solution\/output/$out}"
    say "Self-test: $cmd"
    local rc=0
    run_timed "$cmd" || rc=$?

    local fails=0
    [ "$rc" -eq 0 ] || { echo "FAIL: kod wyjścia $rc"; fails=1; }
    local n_json n_other
    n_json="$(find "$out" -type f -name '*.json' | wc -l)"
    n_other="$(find "$out" -mindepth 1 ! -type d ! -name '*.json' | wc -l)"
    [ "$n_json" -eq "$n_pdf" ] || { echo "FAIL: .json = $n_json, PDF = $n_pdf"; fails=1; }
    [ "$n_other" -eq 0 ] || { echo "FAIL: pliki inne niż .json:"; find "$out" -mindepth 1 ! -type d ! -name '*.json'; fails=1; }
    if find "$out" -mindepth 1 -name '.*' | grep -q .; then
        echo "FAIL: ukryte pliki/katalogi w output:"; find "$out" -mindepth 1 -name '.*'; fails=1
    fi
    while IFS= read -r f; do
        "$PY" -c 'import json,sys; json.load(open(sys.argv[1], encoding="utf-8"))' "$f" \
            || { echo "FAIL: niepoprawny JSON: $f"; fails=1; }
    done < <(find "$out" -type f -name '*.json')
    echo "Wynik:"; (cd "$out" && find . -type f | sort)

    $SUDO rm -rf "$tmp"
    if [ "$fails" -eq 0 ]; then echo "SELF-TEST OK"; else echo "SELF-TEST NIEUDANY"; return 1; fi
}

check_real() {
    local run_md="$SOLUTION_DIR/RUN.md" cmd
    [ -f "$run_md" ] || die "brak $run_md"
    cmd="$(run_command "$run_md")"
    [ -n "$cmd" ] || die "nie znaleziono komendy w $run_md"
    echo "input:  $(find "$SOLUTION_DIR/input" -type f -name '*.pdf' | wc -l) PDF"
    say "cd $SOLUTION_DIR && sudo $cmd"
    cd "$SOLUTION_DIR"
    local rc=0
    run_timed "$cmd" || rc=$?
    echo "output: $(find "$SOLUTION_DIR/output" -type f | wc -l) plików, w tym nie-.json: $(find "$SOLUTION_DIR/output" -type f ! -name '*.json' | wc -l)"
    echo "Posprzątaj po teście input/ i output/ (patrz docs/vm-jury.md)."
    return "$rc"
}

if [ "$do_deploy" -eq 1 ]; then deploy; fi
if [ "$do_self" -eq 1 ]; then self_test; fi
if [ "$do_real" -eq 1 ]; then check_real; fi
