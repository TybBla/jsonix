## E7: pełnomocnictwa ze skanów — dwa podpisy w jednej linii, konsorcjum po przecinku (plan v1.0, pkt 10)

Gałąź `etap/E7-pelnomocnictwa` → `main`. Niezależna od `etap/E7-skany` (przelewy).

### Diagnoza (holdout skanów, 3 dokumenty, F1 0,833)
- **0006, 0004 — reguła.** OCR skleja dwie kolumny podpisów w jedną linię („Dorota Szulc - Prezes Zarządu Monika Kaczmarek - Prezes Zarządu”), a reguła brała tylko pierwszą osobę. W 0006 OCR przekręcił też „reprezentowana” → „reprenentowana”, więc nazwiska nie trafiały do bloku podpisujących ze zdania wstępnego.
- **0007 — reguła.** Pozycje konsorcjum rozdzielone „,⏎2)” zamiast „;”, więc drugi mocodawca (KRS, NIP, nazwa, podpisujący) w ogóle nie był wyodrębniany.
- **0004 — OCR.** „spółkaakcyjna” bez spacji. Tego nie poprawiam, bo to błąd rozpoznania tekstu.

### Zmiany (`config/doctypes/pelnomocnictwo.yaml`, tylko reguły)
- Podpisujący: nazwisko może też zaczynać się po „Zarządu ” (sklejone kolumny). Start bloku toleruje „repre?entowan…”.
- Konsorcjum: separator pozycji „;” albo „,” na końcu linii, ale tylko przed pozycją „N) … z siedzibą”. Bez tego zawężenia psuła się numerowana lista uprawnień w zwykłym pełnomocnictwie (`przyklad_05`, złapane przez test GT).
- Testy: `tests/test_extract_pelnomocnictwo_warianty.py` (syntetyczne warianty, nie teksty z holdoutu): sklejone podpisy (także przy przekręconym „reprezentowana”), podpisy w osobnych liniach bez zmian, konsorcjum po przecinku.

### Wyniki (Docker, Python 3.13, OCR)
| Sekcja | przed | po |
|---|---|---|
| holdout@skan, pełnomocnictwo | 0,833 | **0,943** |
| holdout@skan, F1 | 0,912 | **0,958** |
| dev@skan, F1 | 0,977 | 0,977 (bez zmian) |
| dev@tekst / holdout@tekst | 0,999 / 0,997 | bez zmian |

Uwaga o metodzie: błędy znalazłem na holdoucie, bo plan kazał je zbadać. Poprawki są jednak ogólne (warianty układu, nie konkretne nazwiska) i sprawdzone na syntetycznych tekstach oraz na wszystkich pełnomocnictwach dev (testy GT i odporności, 51 passed).

### Do zrobienia przez właściciela
`--update-baseline` dla sekcji skanów (zablokowane dla mnie uprawnieniami), po scaleniu razem z `etap/E7-skany`.

### Bramka
`ruff`: czysto. `pytest -m "not slow"`: 1195 passed; pada tylko `test_ingest_coverage` (OCR, lokalnie Python 3.15, tak samo na `main`). Bramki tekst dev/holdout i skan dev/holdout: exit 0.
