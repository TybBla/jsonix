## E11: Docker Compose działający za pierwszym razem

Gałąź `etap/E11-docker` → `main`. Wymóg nagrody (regulamin §3.5: Docker Compose).

### Co się zmienia
- `docker-compose.yml`:
  - `.env` jest **opcjonalny** (`env_file: required: false`). Wcześniej Compose wywracał się bez tego pliku, choć domyślny tryb bez LLM nie potrzebuje klucza.
  - Healthcheck na `/api/health`.
  - Port ustawiany przez `JSONIX_PORT` (domyślnie 8000), nasłuch tylko na `127.0.0.1`.
  - `restart: unless-stopped`, nazwa obrazu `jsonix:latest`.
- `Dockerfile`:
  - `HEALTHCHECK`, więc działa też przy samym `docker run`.
  - Zmienne `PYTHONDONTWRITEBYTECODE`/`PYTHONUNBUFFERED`.
  - Katalogi `input/` i `output/` istnieją w obrazie.
- `.dockerignore`: bez `.venv` (venv z Windows nie działa w Linuksie, a był kopiowany do obrazu), `data/`, `tests/`, `.github`, `.claude`, `docs/img/`.
- `scripts/smoke_docker.py` (kod wyjścia 0/1, 2 = brak Dockera) robi kolejno:
  1. `up --build` w osobnym projekcie `jsonix-smoke`, bez `.env`;
  2. czeka na stan `healthy`;
  3. wykonuje te same sprawdzenia GUI/API co `smoke_gui.py`;
  4. uruchamia wsad `python -m odw2json run` **w kontenerze** na `przyklad_01` i jednym skanie, żeby sprawdzić OCR w obrazie;
  5. porównuje JSON-y z wsadu w kontenerze z CLI na hoście;
  6. sprząta (`down`).
- `tests/test_docker_config.py` (w CI): `.env` opcjonalny, healthcheck, wolumeny, Python 3.13, wpisy `.dockerignore`.
- README:
  - nowa sekcja „Docker”;
  - poprawka nieaktualnego akapitu „OCR (opcjonalny)… obraz Dockera go nie zawiera”, bo OCR jest od E2b w `requirements.txt` i działa w obrazie;
  - `.env` opisany jako opcjonalny.

### Wyniki
- `python scripts/smoke_docker.py`: **exit 0**, „SMOKE DOCKER OK: healthy, GUI/API, wsad w kontenerze (w tym skan OCR) = CLI na hoście”.
- Skan `skany/potwierdzenia/0007` w kontenerze: `przelew`, `ocr_used=True`, backend `pypdfium2+ocr:rapidocr`.
- `ruff`: czysto. `smoke_gui.py`: exit 0. `eval.gate --split dev --source tekst`: exit 0.
- `pytest -q` (Windows, Python 3.15): exit 1, wyłącznie przez 5 testów OCR, które padają tak samo na `main`, bo dla Pythona 3.15 nie ma paczek OCR. Pozostałe: 722 passed.

### Nie zmieniałem
`odw2json/`, `extract/`, `ingest/`, `config/`, `eval/`. Zmiany obejmują tylko pakowanie, skrypt, test i README.

### Do sprawdzenia przez recenzenta
- [ ] `docker compose up --build` na czystym klonie bez `.env`, potem http://127.0.0.1:8000 i `docker compose ps` → `healthy`.
- [ ] `python scripts/smoke_docker.py` → exit 0.
