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

## Pomiar „jak u jury” (22.11.2026, plan do v1.0, pkt 11)

**Warunki.** Kod `main` v0.4.0 (E4+E5 ekstrakcja). Pełny wsad CLI `python -m odw2json run input output`, tak jak
`start.bat`, w obrazie Dockera (Python 3.13, OCR) z `--cpus=8 --memory=16g`. Zimny cache OCR, `LLM_MODE=replay`
(bez LLM). Wejście: wszystkie sprawy z `data/train` (`przyklad_*`), negatywy i 30 skanów, razem **226 PDF**.

**Wynik całości:** exit 0, **213 s** (3 min 33 s), 0 błędów; typy: 70 odwołań, 70 pełnomocnictw, 70 przelewów,
16 nieznanych. Pliki są przetwarzane po kolei, więc czas całości to suma czasów plików.

| Grupa | n | suma | mediana | max |
|---|---|---|---|---|
| sprawy `przyklad_*` (tekst), na sprawę | 60 | 6,1 s | 0,09 s | 0,21 s |
| negatywy | 12 | 15,7 s | 0,09 s | 8,8 s (pierwszy plik: start silnika OCR) |
| skany odwołań (5–7 stron) | 10 | 157,9 s | 14,3 s | 20,0 s |
| skany pełnomocnictw | 10 | 18,2 s | 1,8 s | 2,0 s |
| skany potwierdzeń przelewu | 10 | 15,3 s | 1,5 s | 1,9 s |

- **Sprawa z warstwą tekstu: ok. 0,1 s.** Sprawa złożona z samych skanów (odwołanie + pełnomocnictwo + przelew):
  ok. 18–24 s. Skany odwołań to 74% czasu całego wsadu.
- Kontrolnie `scripts/bench_cases.py` w tych samych warunkach (90 spraw, 214 PDF): skan średnio 5,98 s
  (mediana 1,76 s, max 18,8 s), całość 192 s.

**Wolniej niż 21.11 (ok. ×1,5), ale nie przez kod.** Skany odwołań: 9–13 s wtedy, 14–20 s teraz. Porównanie A/B na
10 skanach odwołań w tym samym kontenerze: `main` 144 s i 151 s, kod sprzed `248de2a` (stabilność OCR) 140 s,
czyli różnica w granicach szumu. Spowolnienie pochodzi z maszyny pomiarowej (laptop, obciążenie, zasilanie), więc
liczby bezwzględne mają co najmniej ±30% niepewności. Laptop jury (i7, 16 GB) może być szybszy albo wolniejszy.

**Zbiór oceniający (≥ 10 spraw).** Przy tych czasach: 10 spraw z tekstem to ok. 1 s; 10 spraw z samych skanów
to ok. 3–4 min; typowy miks (część skanów) to ok. 1 min. Do tego jednorazowa instalacja paczek przy pierwszym
`start.bat` (ok. 2 min, `docs/test-jury.md`).

### Decyzja (pkt 11)
- **Nie przyspieszamy OCR przed v1.0.** Warianty tańsze w OCR były już zmierzone w E2b (DPI, wątki, równoległość
  po stronach i procesach) i obecne ustawienia są najszybsze z tych, które nie obniżają pokrycia. Dalsze zejście
  (niższe DPI, mniejszy model) grozi spadkiem F1 na skanach, a F1 waży w ocenie więcej niż czas.
- **Ryzyko nieznanego limitu czasu ograniczają zmiany z `etap/E11-limit-czasu` (PR #13):** pliki zastępcze `{}`
  od startu, zapis każdego wyniku od razu i atomowo, oraz **PDF-y z tekstem przed skanami**. Przy przerwaniu
  przepadają najwyżej najwolniejsze skany, a nie dokumenty, które liczą się w sekundach.
- Do rozważenia tylko jeśli UZP poda limit krótszy niż kilka minut na cały zbiór: OCR dwóch skanów naraz w osobnych
  procesach (×1,4 przy 2 procesach, pomiar 21.11) albo niższe DPI tylko dla stron z dużym drukiem.
