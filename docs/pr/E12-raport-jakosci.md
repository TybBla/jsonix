## Raport jakości do zgłoszenia (F1 per zbiór, typ i pole + czas na dokument)

Gałąź `etap/E12-raport-jakosci` → `main`. Zgłoszenie wymaga „wyników testów jakości”, a UZP ogranicza czas na rozwiązanie.

### Co się zmienia
- **`scripts/quality_report.py`** liczy to samo co bramka (`eval.gate.run_gate`, F1 z `eval/score.py`) dla **dev/holdout × tekst/skan**. Nie porównuje wyniku z baseline i nic nie zapisuje w `eval/`.
  - **Wynik:** `docs/raport-jakosci.md` oraz surowe metryki w `.json` obok.
  - **Tabele:** podsumowanie (F1, precyzja, pełność, dokumenty, negatywy, błędy klasyfikacji, czas na dokument), F1 per typ i F1 per pole. Pola z F1 < 0,85 są pogrubione (próg z roadmapy E7).
  - **Kontekst:** środowisko (commit, Python, CPU) i stan cache OCR.
- Testy: renderowanie tabel i przebieg na prawdziwej bramce (dev/tekst).
- README: jedna linia w sekcji „Ewaluacja”.

### Podgląd na gałęzi E4 (jeszcze nie na `main`)
Pomiar w Dockerze (Python 3.13, OCR, zimny cache):

| Zbiór | Źródło | F1 | Dokumenty | Czas / dok. |
|---|---|---|---|---|
| dev | tekst | 99,9% | 162 | 0,02 s |
| dev | skan | 97,5% | 29 | 4,00 s |
| holdout | tekst | 99,7% | 62 | 0,02 s |
| holdout | skan | 90,3% | 13 | 1,48 s |

Najsłabsze pola są na skanach z holdoutu (np. `Zamawiajacy[].krs`, `mocodawca[].data.imie_nazwisko`, `przelew_bankowy.tytul`): to pojedyncze dokumenty, więc jedno pudło daje 0%. Do wglądu dla właściciela E4.

### Po scaleniu E4
Wygeneruj `docs/raport-jakosci.md` na maszynie z OCR (Python 3.13/3.14 albo `docker compose run --rm app python scripts/quality_report.py`) i wpisz liczby do `docs/demo.md` / `docs/prezentacja.html`.
