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
| `title_mode` | `anywhere` | `anywhere` - fraza gdziekolwiek w nagłówku (stare zachowanie); `line` - fraza musi być **tytułem**: linią (bez interpunkcji przy brzegach) o długości <= `title_line_max_chars`, której fraza zajmuje >= `title_line_min_cover`; fraza wielowyrazowa pasuje też bez spacji (`Potwierdzenieprzelewu`). Zalecane `line` - zdanie „wnosimy odwołanie…” w piśmie nie jest tytułem |
| `title_line_max_chars` | `60` | tylko `title_mode: line`: najdłuższa linia uznawana za tytuł (po normalizacji) |
| `title_line_min_cover` | `0.6` | tylko `title_mode: line`: jaką część linii musi zajmować fraza (np. `PEŁNOMOCNICTWO PROCESOWE` = 0,58; `Bank X potwierdzenie przelewu` wymaga niższego progu i dłuższej linii) |
| `header_chars` | `600` | długość nagłówka w znakach (tytuł stojący po blokach adresowych wymaga większej wartości) |
| `patterns` | `[]` | lista `{regex, weight}` — cechy strukturalne (np. numer rachunku przy kwocie, `zarzut nr 1`); regex na tekście znormalizowanym, trafienie liczy się raz |
| `required_any` | `[]` | lista wpisów; **bez trafienia żadnego typ odpada**. Wpis to fraza, regex z prefiksem `re:` albo grupa `{all_of: [...]}` (spełniona, gdy trafią **wszystkie** jej wpisy). Specjalny wpis `@title` = trafiła cecha `title` tego typu. Np. przelew: IBAN **i** (tytuł **lub** etykiety nadawca + odbiorca) |
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
  title_mode: line                          # tytul = osobna linia (nie zdanie w tresci)
  title_line_max_chars: 80
  title_line_min_cover: 0.4
  header_chars: 600
  strong: ["przelew", "beneficjent"]
  weak: ["kwota", "rachunek", "pln"]        # ogólne słowa - tylko +1
  negative: ["zarzut nr", "ogloszenie o zamowieniu"]
  patterns:
    - regex: '(?<!\d)\d{2}(?: ?\d{4}){6}(?!\d).{0,800}kwot[aye][^0-9]{0,40}\d+[,.]\d{2}'
      weight: 4
  required_any:                                    # IBAN (26 cyfr) ORAZ tytul albo etykiety slipu
    - all_of: ['re:(?<!\d)\d{2}(?: ?\d{4}){6}(?!\d)', "@title"]
    - all_of:
        - 're:(?<!\d)\d{2}(?: ?\d{4}){6}(?!\d)'
        - 're:(rachunek nadawcy|zleceniodawc|numer transakcji)'
        - 're:(beneficjent|odbiorc)'
  min_score: 6.0
  min_margin: 2.0
```

### Globalne `config/classify.yaml` — nagłówki dokumentów obcych

```yaml
foreign_titles:
  weight: -10          # kara dla WSZYSTKICH typów (raz), musi być <= 0
  header_chars: 600    # tylko te pierwsze znaki
  phrases: [wyrok, postanowienie, sygn. akt, ogloszenie o, zawiadomienie, faktura, wezwanie, specyfikacja, umowa, protokol]
```

Fraza liczy się, gdy któraś **linia** nagłówka **zaczyna się** od niej (granica słowa; małe litery, bez polskich
znaków, rozstrzelone litery zwinięte). Dzięki temu wyrok KIO, faktura czy wezwanie, które zawierają mnóstwo słów
domenowych („odwołanie”, „przelew”, „zarzut”), nie są mylone z typami z puli. Nowy typ nie wymaga zmian tego
pliku; dopisz fraze tylko wtedy, gdy nowy rodzaj dokumentu obcego wpada do któregoś typu. Brak pliku = brak kar.
Kara jest miękka (−10): bardzo bogaty w cechy dokument nadal może przejść, dlatego frazy dobieraj ostrożnie.
Sprawdź na `dev`, że żaden pozytyw nie zaczyna linii nagłówka od dodawanej frazy.

Wskazówki: wyniki ogólnych słów trzymaj nisko (`weak`), a typ opieraj na tytule i wzorcach strukturalnych;
dokumenty spoza puli (ogłoszenia BZP/TED, wyroki KIO, broszury) mają dawać `None`, więc ustaw `min_score`
powyżej tego, co zdobywa pojedyncze trafienie słów domenowych. Strojenie rób na splicie `dev`
(`python -m eval.gate --split dev --source tekst`), `holdout` tylko do końcowej kontroli.
