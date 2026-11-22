## E10: 4. typ dokumentu samą konfiguracją (orzeczenie KIO) + test „0 linii kodu”

Gałąź `etap/E10-nowy-typ` → `main`. E4 jest już w `main` (v0.4.0); gałąź zaktualizowana o `main`.

### Co się zmienia
- **`examples/nowy-typ/orzeczenie_kio/`** — wyłącznie konfiguracja:
  - YAML typu: rozpoznanie (tytuł wyrok/postanowienie, „orzeka”, sygnatura) i 8 pól: sygnatura, rodzaj, data, przewodniczący, odwołujący, zamawiający, rozstrzygnięcie, kwota wpisu;
  - szablon JSON;
  - słownik rozstrzygnięć (oddala, uwzględnia, odrzuca, umarza).
- **`tests/test_nowy_typ_konfiguracja.py`** — 6 testów, bez zmian w `odw2json/`:
  - przebieg potoku na prawdziwym PDF (`negatywne/KIO_KIO 2617-21.pdf`): wszystkie 8 pól poprawnie, a trace ma stronę i fragment, więc GUI podświetla źródło. Zamawiający jest w mianowniku („Gmina Cieszyn”) z uzasadnienia („(dalej: „Zamawiający”)”), a komparycja („prowadzonym przez Gminę…”) służy tylko jako zapas;
  - inne brzmienie (wyrok, inne strony, „oddala”, kwota „7 500,00 zł”): te same reguły działają;
  - **3 podstawowe typy dają identyczne wyniki** z dodanym typem i bez niego;
  - **nowe pole w istniejącym typie** (waluta przelewu) samą konfiguracją: klucz w szablonie i reguła w YAML;
  - katalog przykładu zawiera tylko YAML, JSON i MD;
  - **typ nie jest aktywny w `config/`**, bo według UZP orzeczenia KIO to dokumenty spoza typów i wynik ma być `{}` (pilnuje tego test).
- README przykładu z instrukcją pokazu i krokiem kontrolnym po pokazie (`doctypes` → 3 typy, bramka: negatywy 12/12) („skopiuj 3 pliki, uruchom”) i link w `docs/nowy-typ-dokumentu.md`.

### Bramka (na bazie E4)
- `ruff`: czysto.
- `eval.gate --split dev --source tekst`: exit 0 (F1 0,999, negatywy 12/12, bo typ nie jest aktywny).
- `pytest`: 5 testów OCR pada lokalnie na Pythonie 3.15, jak na `main`; reszta (1087) przechodzi.
