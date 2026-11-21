# Jak dodać nowy typ dokumentu (bez zmian w kodzie)

1. Szablon wyniku: `config/schemas/<typ>.json` — dokładny kształt JSON, wszystkie wartości `null`.
2. Opis typu: `config/doctypes/<typ>.yaml`:
   ```yaml
   id: <typ>
   title: Czytelna nazwa
   output_template: schemas/<typ>.json
   classify:
     strong: ["fraza charakterystyczna", ...]   # +2 pkt (porównanie bez polskich znaków, małe litery)
     weak: [...]                                # +1 pkt
     negative: [...]                            # -3 pkt
     min_score: 3.0
   fields: {}        # reguły pól (format ustala sektor B)
   llm:
     prompt: prompts/<typ>.md
   ```
3. (opcjonalnie) prompt `config/prompts/<typ>.md`, słowniki `config/lookups/*.yaml`.
4. Sprawdź: `python -m odw2json doctypes` — nowy typ jest na liście; `python -m odw2json run`.

Kod (`odw2json/`) ładuje wszystkie typy z `config/doctypes/` automatycznie.

## Sekcja `classify:` — wszystkie pola

Typ dokumentu jest rozpoznawany **wyłącznie z treści** (nigdy z nazwy pliku). Wszystkie dopasowania działają
na tekście znormalizowanym (małe litery, bez polskich znaków), więc frazy i regexy piszemy małymi literami
bez ogonków (`odwolujacy:`, nie `Odwołujący:`). Poza `strong/weak/negative/min_score` pola są opcjonalne,
a literówka w nazwie pola lub niepoprawny regex kończy się czytelnym błędem walidacji przy starcie.

| Pole | Domyślnie | Znaczenie |
|---|---|---|
| `strong`, `weak`, `negative` | `[]` | frazy; każda obecna w tekście daje `weights.strong/weak/negative` punktów (raz) |
| `title` | `[]` | frazy szukane w **nagłówku** (pierwsze `header_chars` znaków); trafienie daje `weights.title` punktów (raz, niezależnie od liczby pasujących fraz); rozstrzelone litery (`P E Ł N O M O C N I C T W O`, ciągi >= 5 pojedynczych liter) są przed dopasowaniem zwijane |
| `header_chars` | `600` | długość nagłówka w znakach (tytuł stojący po blokach adresowych wymaga większej wartości) |
| `patterns` | `[]` | lista `{regex, weight}` — cechy strukturalne (np. numer rachunku przy kwocie, `zarzut nr 1`); regex na tekście znormalizowanym, trafienie liczy się raz |
| `required_any` | `[]` | frazy lub regexy z prefiksem `re:`; **bez trafienia żadnej typ odpada** (np. potwierdzenie przelewu bez numeru rachunku) |
| `min_score` | `3.0` | minimalny wynik zwycięzcy; poniżej dokument jest nieznany |
| `min_margin` | `0.0` | minimalna przewaga nad drugim typem; poniżej dokument jest nieznany |
| `weights` | `strong: 2, weak: 1, negative: -3, title: 4` | wagi cech (można nadpisać wybrane klucze) |

Wynik klasyfikacji (`Classification`) zawiera `scores` (punkty każdego typu), `confidence` w [0, 1]
(`margines * nasycenie`, wzór w docstringu `odw2json/classify/__init__.py`) oraz `evidence` — listę trafionych
cech zwycięzcy (przy odrzuceniu: powód i cechy najlepszego kandydata). `evidence` trafia do trace
(`output/.trace/.../*.trace.json`, klucz `classification`), więc GUI może pokazać „dlaczego ten typ”.

Przykład (skrót z `config/doctypes/przelew.yaml`):

```yaml
classify:
  title: [potwierdzenie przelewu, potwierdzenie transakcji, polecenie przelewu]
  header_chars: 600
  strong: ["przelew", "beneficjent"]
  weak: ["kwota", "rachunek", "pln"]        # ogólne słowa - tylko +1
  negative: ["zarzut nr", "ogloszenie o zamowieniu"]
  patterns:
    - regex: '(?<!\d)\d{2}(?: ?\d{4}){6}(?!\d).{0,800}kwot[aye][^0-9]{0,40}\d+[,.]\d{2}'
      weight: 4
  required_any:
    - 're:(?<!\d)\d{2}(?: ?\d{4}){6}(?!\d)'   # numer rachunku (26 cyfr)
  min_score: 6.0
  min_margin: 2.0
```

Wskazówki: wyniki ogólnych słów trzymaj nisko (`weak`), a typ opieraj na tytule i wzorcach strukturalnych;
dokumenty spoza puli (ogłoszenia BZP/TED, wyroki KIO, broszury) mają dawać `None`, więc ustaw `min_score`
powyżej tego, co zdobywa pojedyncze trafienie słów domenowych. Strojenie rób na splicie `dev`
(`python -m eval.gate --split dev --source tekst`), `holdout` tylko do końcowej kontroli.
