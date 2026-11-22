# VM jury (Azure) - wdrożenie i test krok po kroku

Fakty organizatora (VM.md, 22.11.2026) są w [kryteria-uzp.md](kryteria-uzp.md), pkt 5b. W skrócie: jury wgrywa tajny
zbiór do `/opt/solution/input`, w `/opt/solution` uruchamia z `sudo` **komendę z `/opt/solution/RUN.md`** i zabiera
`/opt/solution/output`. **Dostęp zespołów zostanie odcięty 22.11.2026 o 11:00** - obraz musi być zbudowany wcześniej.

Co jest w repo: [RUN.md](../RUN.md) (wzorzec pliku jury), `config/app.jury.yaml` (profil: w `output/` tylko wyniki),
`scripts/deploy-vm.sh` (wdrożenie i testy).

## Stan wdrożenia (22.11.2026, v1.0.1)
- Obraz `jsonix:latest` zbudowany na VM, `/opt/solution/RUN.md` skopiowany z repo (`/opt/solution/repo`).
- Test jak u jury (krok 4) z `sudo`, także po restarcie VM (krok 5): kod wyjścia 0, w `output/` wyłącznie pliki JSON.
- Pomiar: cały zbiór treningowy, 226 PDF (w tym 30 skanów), w 365 s; skan średnio ok. 12 s, dokument z tekstem
  < 0,1 s. Limit jury: 60 minut na 150 plików.
- Po teście `/opt/solution/input` i `/opt/solution/output` zostawione puste (krok 6).

## Profil jury: po co
W kontenerze `/app/output` to zamontowane `/opt/solution/output`. Domyślnie do `output/` trafiają też trace
(`.trace/`), logi i podsumowanie przebiegu (`.logs/`) oraz cache OCR (`.cache/`) - jury dostałoby nadmiarowe pliki JSON.
Zmienna `JSONIX_APP_CONFIG=config/app.jury.yaml` (ścieżka względna liczona od korzenia repo = `/app`) scala ten plik
na `config/app.yaml`: `write_trace: false`, `log_dir` i `ingest.ocr.cache_dir` w `/tmp` kontenera, 2 wątki onnxruntime
(VM ma 2 vCPU). Wyniki ekstrakcji się nie zmieniają. W `output/` zostaje wyłącznie `<sprawa>/<nazwa_jak_pdf>.json`.

## Kroki (członek zespołu, na VM)
1. Zaloguj się: `ssh <użytkownik>@<adres VM>`.
2. Pobierz repo i wdróż (klon do `/opt/solution/repo`, `docker build -t jsonix:latest`, kopia `RUN.md` do `/opt/solution/RUN.md`):
   ```bash
   git clone https://github.com/TybBla/jsonix.git ~/jsonix
   cd ~/jsonix
   bash scripts/deploy-vm.sh                 # inna gałąź: --branch NAZWA; inne źródło: --repo URL
   ```
   Repo jest publiczne. Skrypt klonuje `/opt/solution/repo` z lokalnego `~/jsonix` (bez `sudo`; `/opt/solution` należy
   do konta zespołu). Aktualizacja: `git -C ~/jsonix pull`, potem ponownie `bash scripts/deploy-vm.sh`.
   Build trwa kilka minut (pobiera obraz `python:3.13-slim` i zależności; VM ma internet). Skrypt **nie kasuje**
   `/opt/solution/input` ani `output`.
3. Self-test (katalogi tymczasowe, PDF-y z `data/train`: dokumenty z tekstem, negatyw i skan z OCR):
   ```bash
   bash scripts/deploy-vm.sh --self-test
   ```
   Uruchamia dokładnie komendę z `RUN.md` (podmieniając tylko ścieżki montowania), sprawdza: kod wyjścia 0, liczba `.json` =
   liczba PDF, w output nic poza `.json` (też ukryte katalogi), każdy plik to poprawny JSON; wypisuje czas. Oczekiwany
   koniec: `SELF-TEST OK`.
4. Test jak u jury:
   ```bash
   sudo cp -r <PDF-y_lub_katalogi_spraw> /opt/solution/input/        # np. fragment repo/data/train
   sudo rm -rf /opt/solution/output/*                                 # wyczyść output (jury też może)
   cd /opt/solution && sudo <komenda z /opt/solution/RUN.md>
   find /opt/solution/output -type f ! -name '*.json'                 # ma być puste
   ```
   Albo to samo skryptem: `bash scripts/deploy-vm.sh --check-real` (wypisuje czas i liczbę plików nie-`.json`).
5. `sudo reboot`, po powrocie VM powtórz krok 4 (obraz musi przetrwać restart; `docker images` pokazuje `jsonix:latest`).
6. **Sprzątanie po teście:** `sudo rm -rf /opt/solution/input/* /opt/solution/output/*` (jury i tak może je wyczyścić, ale nie zostawiamy
   własnych danych). Nie usuwaj `/opt/solution/repo` ani `/opt/solution/RUN.md` i nie kasuj obrazu (`docker rmi`/`docker system prune`).

## Ryzyka
- **2 vCPU i brak GPU:** OCR skanów jest wolniejszy niż na laptopach (kilka sekund na stronę, skan średnio ok. 12 s); limit jury to 60 minut
  na 150 plików, a nawet same skany zmieszczą się w ok. 30 min. Na wypadek przekroczenia `{}` dla każdego PDF powstaje przed przetwarzaniem, a skany idą na końcu (patrz `RUN.md`).
- **Obraz zbudowany przed 11:00:** po odcięciu dostępu nie da się nic poprawić ani zbudować; `RUN.md` nie robi `docker build`
  ani `pull`. Ostatnią zmianę wdrażaj z `--self-test` i `--check-real`.
- **Output tylko JSON-y:** każdy dodatkowy plik w `/opt/solution/output` to ryzyko złej oceny (patrz profil jury); self-test to sprawdza.
- **Python 3.12 na VM** jest za stary dla aplikacji (wymaga 3.13+) - dlatego wszystko działa w Dockerze, nie `python` na hoście.
- **Brak LLM i kluczy API:** `/opt/solution/.env` nie jest potrzebny i nie jest używany.
- Plik `RUN.md` na VM ma pierwszeństwo przed repo - po zmianie komendy w repo wdróż ponownie (krok 2), żeby skopiować go do `/opt/solution/RUN.md`.
