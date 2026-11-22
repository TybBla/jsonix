## Czas „jak u jury” na v0.4.0 (plan do v1.0, pkt 11)

Tylko dokumentacja: nowa sekcja w `docs/decyzje/E11-wydajnosc.md`.

- Pełny wsad CLI w Dockerze (8 CPU, 16 GB, zimny cache, bez LLM) na 226 PDF z `data/train`: 213 s, 0 błędów.
- Sprawa z tekstem ok. 0,1 s; sprawa z samych skanów ok. 18–24 s; skany odwołań to 74% czasu.
- OCR ok. ×1,5 wolniej niż 21.11, ale A/B (`main` vs kod sprzed `248de2a`) pokazuje, że to maszyna, nie kod.
- Decyzja: nie przyspieszamy OCR przed v1.0; ryzyko limitu czasu pokrywa PR #13 (pliki `{}` od startu, zapis od razu, PDF-y z tekstem przed skanami).

### Bramka
Zmiany tylko w `docs/`. `ruff`: czysto.
