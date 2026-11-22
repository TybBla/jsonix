```bash
docker run --rm -e JSONIX_APP_CONFIG=config/app.jury.yaml -v /opt/solution/input:/app/input -v /opt/solution/output:/app/output jsonix:latest python -m odw2json run input output
```

# jsonix - uruchomienie rozwiązania (wzorzec `/opt/solution/RUN.md`)

Komenda powyżej uruchamia się w `/opt/solution` z `sudo`, bez interakcji, i sama się kończy po przetworzeniu
wszystkich plików. Obraz `jsonix:latest` jest zbudowany wcześniej na tej VM
(`bash scripts/deploy-vm.sh`, patrz `docs/vm-jury.md`); komenda niczego nie pobiera ani nie buduje.

## Co robi
- Czyta wszystkie PDF-y z `/opt/solution/input` (także z podfolderów = spraw), rozpoznaje typ dokumentu
  **z treści** (odwołanie / pełnomocnictwo / potwierdzenie przelewu / nieznany) i zapisuje JSON wg schematu UZP.
- Wynik: `/opt/solution/output/<sprawa>/<nazwa_jak_pdf>.json`; dokument nieznany = plik z `{}`.
  W `output/` nie ma nic poza tymi plikami (trace, logi i cache OCR są poza `output/`, profil `config/app.jury.yaml`).
- Bez LLM i bez kluczy API (plik `/opt/solution/.env` nie jest potrzebny), bez usług w tle, bez portów.

## Czas
- Najpierw `{}` dla każdego PDF (żeby przerwanie nie zostawiło brakujących plików), potem przetwarzanie:
  najpierw dokumenty z warstwą tekstową (ok. 0,01 s na dokument), na końcu skany (OCR na CPU: kilka sekund na stronę;
  VM ma 2 vCPU, profil jury ustawia 2 wątki onnxruntime).
- Kod wyjścia 0 także wtedy, gdy część plików się nie przetworzyła (wynik `{}` zostaje); 1 tylko gdy nie przetworzono żadnego.
