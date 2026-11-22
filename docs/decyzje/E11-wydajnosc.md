# E11 — czas przetwarzania (pomiar 21.11.2026)

**Kontekst.** UZP ogranicza czas na rozwiązanie (kryteria, pkt 5a; wartość nieznana). Liczy się pierwsze
uruchomienie na nowych dokumentach: pusty cache OCR, bez LLM.

**Pomiar:** `python scripts/bench_cases.py --workers 2,4`
- Warunki: obraz Dockera (Python 3.13, OCR) ograniczony do 8 CPU i 16 GB, tak jak laptop jury (i7, 16 GB, bez GPU).
- Kod: gałąź E4 (ekstrakcja), wszystkie sprawy z `data/train` (dev i holdout), czyli 90 spraw i 214 PDF.

| | n | średnio | mediana | p95 | max |
|---|---|---|---|---|---|
| dokument z warstwą tekstu | 184 | 0,01 s | 0,01 s | 0,04 s | 0,11 s |
| skan (OCR) | 30 | 3,95 s | 1,19 s | 12,31 s | 12,65 s |
| sprawa (suma jej dokumentów) | 90 | 1,34 s | 0,05 s | 8,81 s | 12,65 s |

- Udział etapów w czasie: **ingest (tekst z PDF i OCR) 99%**, klasyfikacja 1%, ekstrakcja poniżej 1%.
- Całość sekwencyjnie: **126,5 s**.
- Najwolniejsze są wielostronicowe skany odwołań (5–7 stron, 9–13 s), czyli ok. 2 s na stronę OCR.
- Równolegle (osobne procesy, świeży cache): **2 procesy 89,2 s (×1,42)**, **4 procesy 133,8 s (×0,95)**. Każdy proces OCR ma 4 wątki onnxruntime (`intra_op_num_threads: 4`), więc przy 4 procesach wątki konkurują o 8 rdzeni.

## Decyzje
- **Bez zmian w potoku.** Poza OCR nie ma czego przyspieszać: klasyfikacja i ekstrakcja to ok. 1% czasu.
- **Bez przetwarzania równoległego.** Daje najwyżej ×1,4 i to tylko przy 2 procesach. Kosztowałoby zmianę `pipeline.run`: procesy, kolejność logów, a bramka F1 podmienia `ingest.load` w procesie. Dla zbioru oceniającego (≥ 10 spraw, część to skany) sekwencyjnie wychodzi rzędu kilkudziesięciu sekund.
- Do rozważenia przez właściciela OCR (E2b), z pomiarem tym samym skryptem:
  - OCR stron jednego skanu równolegle (np. 2 strony naraz po 2 wątki zamiast 1 strony na 4 wątkach);
  - niższe DPI dla stron z dużym, wyraźnym drukiem.

  Obecne ustawienia: `docs/decyzje/E2b-ocr-wydajnosc.md`.
- `scripts/quality_report.py` podaje czas na dokument per zbiór, więc wzrost czasu będzie widoczny przy każdym raporcie.
