## Pomiar czasu na dokument i sprawę (limit czasu UZP)

Gałąź `etap/E11-wydajnosc` → `main`. UZP ogranicza czas na rozwiązanie (kryteria, pkt 5a), więc zmierzyłem, gdzie idzie czas.

### Co się zmienia
- **`scripts/bench_cases.py`**: czas etapów (ingest, classify, extract) na dokument i na sprawę przy **zimnym cache OCR**, ze statystykami mediana/p95/max i listą najwolniejszych plików. Opcja `--workers N` mierzy czas całości przy N równoległych procesach (osobne procesy `spawn`, bez zmian w potoku).
- **`docs/decyzje/E11-wydajnosc.md`**: wyniki i decyzje.

### Wyniki
Docker, Python 3.13, limit 8 CPU i 16 GB jak laptop jury; gałąź E4; 90 spraw, 214 PDF.
- Dokument z tekstem: **0,01 s**. Skan (OCR): **średnio 3,95 s, max 12,6 s** (wielostronicowe odwołania, ok. 2 s na stronę).
- **99% czasu to ingest (OCR)**. Klasyfikacja i ekstrakcja są pomijalne.
- Równolegle: **2 procesy ×1,42, 4 procesy ×0,95**, bo procesy OCR (po 4 wątki każdy) konkurują o 8 rdzeni.

### Decyzja
Nie zmieniam potoku: poza OCR nie ma czego przyspieszać, a równoległość daje mało, kosztem zmian w `pipeline.run` i bramce. Rekomendacje dla właściciela OCR (równoległe strony jednego skanu, DPI) są w dokumencie decyzji. Mierzyć tym samym skryptem.
