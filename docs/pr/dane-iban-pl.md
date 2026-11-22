## Dane wzorcowe: numer rachunku z „PL”, gdy ma go dokument

Gałąź `etap/dane-iban-pl` → `main`. ⚠️ **Dla właściciela E4 (ekstrakcja i bramka F1) — przeczytaj przed scaleniem.**

### Dlaczego
UZP na Discordzie, 21.11, 21:17 (zapisane w `docs/kryteria-uzp.md`, pkt 5a): numer rachunku w potwierdzeniu przelewu ma być **taki, jak w dokumencie**. Brak „PL” w części wzorcowych JSON-ów to **błąd**, którego **nie będzie w zbiorze oceniającym**.

### Co się zmienia
- **`scripts/fix_gold_iban.py`** (z testami). Dla każdego PDF-a z GT przelewu szuka numeru w tekście dokumentu (warstwa tekstu albo OCR przez `odw2json.ingest`) i dopisuje „PL” tylko wtedy, gdy stoi ono przed numerem w dokumencie. Domyślnie tylko pokazuje podgląd; zapis dopiero z `--apply`. Uruchomiony ponownie niczego nie zmienia.
- **`data/train`**: **96 pól w 48 plikach** `przyklad_*/przelew.json`, na przykład `68438223…` → `PL68438223…`. Każda zmiana to wyłącznie prefiks: 2 linie na plik, formatowanie i kolejność kluczy bez zmian.
- **Skany** (`data/train/skany/potwierdzenia`) zostają bez zmian, bo ich GT już zgadza się z dokumentem (OCR to potwierdził): „PL” jest tam, gdzie skan je ma.
- Skrypt uruchomiłem w obrazie Dockera (Python 3.13 z OCR): `zmian: 96, nie znaleziono: 0`.

### Wpływ na E4 (do zrobienia przez właściciela E4)
- Normalizator `iban` w `odw2json/extract/normalize.py` (gałąź E4) **usuwa „PL”**. Po scaleniu tego PR bramka F1 pokaże spadek na polach `przelew_bankowy.na_rachunek` i `z_rachunku`. Trzeba zmienić normalizator na wersję, która zachowuje „PL”, gdy jest w dokumencie, i zaktualizować `eval/baseline.json` (z uzasadnieniem). Najwygodniej scalić ten PR razem z E4 albo tuż po nim.
- **Spacje:** GT nie ma spacji (np. `PL68438223…`), choć w 71 PDF-ach numer jest zapisany ze spacjami. UZP nie odpowiedziało na to wprost, więc wysłaliśmy pytanie na Discordzie. Do czasu odpowiedzi zostajemy przy wersji bez spacji.
- Na `main` (ekstrakcja zwraca jeszcze `null`) bramka się nie zmienia: `eval.gate --split dev --source tekst` i `--split holdout --source tekst` kończą się exit 0.

### Bramka
`ruff`: czysto. Testy skryptu: zielone. `pytest` (lokalnie Python 3.15): tylko 5 testów OCR, jak na `main`.
