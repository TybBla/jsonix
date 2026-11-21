# E2b-T3: OCR obowiązkowy i szybszy

Data: 2026-11-21. Maszyna pomiarów: Windows 11, Python 3.14, AMD Ryzen 7 7730U (8 rdzeni / 16 wątków, laptop),
15 GB RAM, bez GPU. Pomiary na maszynie współdzielonej z innymi agentami (obciążenie tła), więc bezwzględne czasy
mają ok. +/-20% szumu; porównania wariantów robiono kolejno, w tych samych warunkach.

## Decyzja

| Parametr (`config/app.yaml` -> `ingest.ocr`) | Wartość | Uzasadnienie |
|---|---|---|
| `dpi` | **150** (było 200) | pokrycie nie spada (53/56 vs 51/56 na próbce), mniej pikseli dla detektora |
| `engine_params."Global.use_cls"` | **false** | skany nie są obrócone; klasyfikator kąta kosztował ok. połowy czasu |
| `engine_params."Rec.rec_batch_num"` | **1** | wsad 6 dopełniał krótkie wiersze do szerokości najdłuższego: rozpoznawanie ok. 1,5x szybsze |
| `engine_params."EngineConfig.onnxruntime.intra_op_num_threads"` | **4** | domyślne `-1` było wolniejsze (nadsubskrypcja); 8 nie daje zysku |
| równoległość po stronach | **brak** | zmierzona, nie przyspiesza (patrz niżej) |

Wynik na wszystkich 72 stronach (bez cache, zimno, 30 dokumentów): **2,99 s/stronę średnio** (p95 strony 4,86 s),
215 s razem (3 min 35 s), start silnika 4,4 s. Poprzednio: ok. 12 s/stronę (ok. 14 min). **Cel <= 3 s/stronę osiągnięty.**

`OCR_CACHE_VERSION` podbity do `"2"`; klucz cache (plik i pamięć procesu) zawiera teraz DPI i skrót
`engine_params`, więc zmiana któregokolwiek parametru unieważnia cache (i przyszłe kasety T4). Parametry
walidowane w `validate_ingest_cfg` (`ocr.engine_params`: słownik kluczy `Sekcja.parametr` z wartościami skalarnymi).

## Tabela wariantów

Próbka (siatka): 8 dokumentów (co 4. skan: 3 odwołania, 2 pełnomocnictwa, 3 potwierdzenia), 21 stron, pokrycie
GT = 56 wartości (dokładne; rozmyte 0). Czas = przepustowość s/stronę (czas ścienny / strony), latencja p95 strony.

| Wariant | DPI | Równoległość | s/str | p95 str. | razem (21 str.) | pokrycie |
|---|---|---|---|---|---|---|
| baseline E2 (cls włączone, domyślne wątki) | 200 | brak | 12,3 | 19,7 | 258 s | 51/56 |
| bez cls | 200 | brak | 6,0 | 8,5 | 126 s | 52/56 |
| bez cls | 150 | brak | 5,7 | 11,3 | 120 s | 53/56 |
| bez cls, 4 wątki ORT | 200 | brak | 4,7 | 6,9 | 100 s | 52/56 |
| bez cls, 8 wątków ORT | 200 | brak | 5,0 | 7,6 | 105 s | 52/56 |
| bez cls, 4x4 wątki | 200 | wątki x4 | 6,3 | 35,5 | 132 s | 52/56 |
| bez cls, 4 proc. x 4 wątki | 200 | procesy x4 | 5,8 | 35,3 | 122 s | 52/56 |
| bez cls, 2 proc. x 8 wątków | 200 | procesy x2 | 6,6 | 19,3 | 138 s | 52/56 |
| bez cls, batch rec = 1, 4 wątki | 200 | brak | 3,5 | 5,0 | 74 s | 54/56 |
| **bez cls, batch rec = 1, 4 wątki** | **150** | **brak** | **2,8** | **4,0** | **58 s** | **53/56** |
| bez cls, batch rec = 1, 2 wątki x 4 proc. | 150 | procesy x4 | 3,3 | 19,0 | 70 s (+23 s startu) | 53/56 |

Różnice pokrycia 51-54 z 56 to różnice pojedynczych wartości (szum modelu na brzegowych wierszach),
a nie systematyczny wpływ parametrów; żaden wariant nie obniżył pokrycia względem baseline.

Wnioski:
- Koszt jest w rozpoznawaniu (`rec`, ok. 80-90% czasu strony), nie w detekcji i nie w renderze. DPI niemal nie
  zmienia czasu, bo rozpoznawanie skaluje każdy wiersz do wysokości 48 px niezależnie od DPI.
- Największe zyski: wyłączenie `cls` (ok. 2x) i `rec_batch_num=1` (ok. 1,5x; wsad 6 posortowany po proporcjach
  i tak miesza wiersze o różnej szerokości, a padding jest liczony).
- Wątki ORT: 1 -> 7,0 s, 2 -> 4,4 s, 4 -> 3,3 s, 8 -> bez zysku (próba pojedynczej gęstej strony).
- **Równoległość po stronach (wątki lub procesy) nie pomaga** na tej maszynie: 8 rdzeni fizycznych jest już zajętych
  przez 4 wątki ORT, a procesy dokładają start (ok. 20-40 s przy ładowaniu modeli) i zużycie RAM (przy 4 procesach
  zaobserwowano raz `bad allocation` w ORT przy 15 GB RAM i obciążeniu tła). Nie wdrażamy jej; nie ma kodu ani
  kluczy konfiguracji `workers`. Pełnomocnictwa i potwierdzenia mają 1 stronę, więc i tak by nie skorzystały.
- DPI 300 niezmierzone: `max_side_len=2000` i tak skaluje obraz w dół, więc wymagałoby podniesienia limitu i
  wydłużyłoby czas bez dowodu zysku (próbka 200 DPI daje 54/56, 150 DPI 53/56, różnica to 1 wartość).

Skrypt: `scripts/bench_ocr.py` (`--skany`, `--stride`, `--variants`, `--list`); wyniki w `bench_out/ocr/` (gitignored).

## Pokrycie na skanach (pełne 72 strony, wariant wybrany)

Pomiar `coverage_for_doc` (jak `eval.ingest_coverage`), tekst po kroku czyszczenia `ocr_artifacts`.

| | exact | fuzzy | razem | |
|---|---|---|---|---|
| **globalnie** | **202** | 0 | 214 | 94,4% |
| pola cyfrowe (NIP, KRS, REGON, PESEL, rachunki) | 80 | 0 | 80 | **100%** |
| pola dosłowne | 122 | 0 | 134 | 91,0% |
| odwołania | 109 | 0 | 113 | 96,5% |
| pełnomocnictwa | 66 | 0 | 67 | 98,5% |
| potwierdzenia przelewu | 27 | 0 | 34 | 79,4% |

Bramka E2b (cyfrowe >= 99%, dosłowne >= 97%): cyfrowe spełnione, **dosłowne poniżej progu (91,0%)**. To nie skutek
szybszej konfiguracji (na próbce baseline 200 DPI z `cls` miał 51/56, czyli nie lepiej), tylko ograniczeń modelu i
układu dokumentów; patrz „Braki”. Tekstowe: pokrycie `eval.ingest_coverage --split all` nadal 1460/1460.

## Artefakty OCR (obserwacje na 72 stronach, tekst przed czyszczeniem `ocr_artifacts`)

Znaki spoza ASCII i spoza polskich liter w wyniku OCR (liczba wystąpień). Pominięto znaki, które pochodzą z
oryginałów (`·` 69, `–` 53, `•` 2, `—` 2) i pojedyncze śmieci (`■`, `、`, `−`, `đ`, `ġ`).

| Znak | Ile | Interpretacja | Mapowanie w `ocr_artifacts` |
|---|---|---|---|
| `ņ` (n z cedillą) | 10 | zwykłe `n` (`rzetelņą`, `warunków`) | `n` |
| `ı` | 8 | `i` bez kropki | `i` |
| `š` | 7 | `ś` | `ś` |
| `ç` | 6 | zwykłe `c` (`przyjęçia`, `możliwośçi`) | `c` |
| `á` | 5 | zbędny akcent na `a` | `a` |
| `í` | 5 | zbędny akcent na `i` | `i` |
| `à` | 4 | zbędny akcent na `a` | `a` |
| `ċ` | 4 | zbędna kropka nad `c` | `c` |
| `Ñ` | 4 | `Ń` (GDAÑSK, ZAMÓWIEÑ) | `Ń` |
| `ș` | 3 | zwykłe `s` (`zașady`, `jeșt`) | `s` |
| `À`, `Á`, `ė`, `ý`, `é`, `ì`, `ž`, `è`, `č`, `ų`, `ê`, `ù`, `ú`, `å`, `ô`, `ò`, `Ž` | 1-2 | akcent lub haczyk | bazowa litera lub odpowiednik polski (`č`->`ć`, `ž`->`ż`) |
| `ö` | 1 | potencjalnie nazwisko obce | **celowo pominięte**, jak `ä ë ü` |

`ocr_artifacts` stoi w `DEFAULT_ORDER` i w `config/app.yaml` przed `quotes`; to tylko `str.translate`
(idempotentne, bez dotykania cyfr, polskich liter, `\f`). Wpływ na pokrycie skanów: +1 wartość (201 -> 202,
`Gdańsk`). Ryzyko: nazwiska obce z akcentami (`José`, `Škoda`) w tekście z warstwą tekstową zostałyby uproszczone.
Krok nie zmienia żadnego dokumentu zbioru (1460/1460, ten sam wynik bramki), a `ä ë ö ü` zostawiono celowo.
Jeśli w danych jury pojawią się takie nazwiska, krok można wyłączyć w `ingest.clean` bez zmiany kodu.
Nie da się naprawić najczęstszych błędów OCR (niżej): utraty ogonków i kreski (`ł` -> `l`, `Ę` -> `E`) oraz `0`/`o`.

## Braki pokrycia (wejście do etapów ekstrakcji)

12 wartości z 214 nie występuje w tekście (po czyszczeniu):

| Dokument | Pole | Wartość GT | Co jest w OCR |
|---|---|---|---|
| odwolania/0003, 0008 | `Odwolujacy[].nazwa` | `... Sp. z o.o.` | `Sp. z 0.0.` (`o` czytane jako `0`) |
| odwolania/0003 | `Odwolujacy[].pelnomocnik.nazwa` | `... Kancelaria Radców Prawnych sp. p.` | nazwa łamana przez wiersze / brak diakrytyków |
| odwolania/0009 | `OdwolanieKIO.miejscowosc` | `Łódź` | `Lódź` (`Ł` -> `L`) |
| pelnomocnictwa/0004 | `mocodawca[].data.nazwa` | `Arkomed Serwis spółka akcyjna` | `Arkomed Serwis S.A.` (w dokumencie skrót, w GT rozwinięcie: sprawa ekstrakcji/normalizacji) |
| potwierdzenia/0004-0010 (7) | `przelew_bankowy.tytul` | np. `Wpis od odwołania, ZP/12/2026, REGIONALNE CENTRUM ZDROWIA PUBLICZNEGO W DĘBNICY GÓRNEJ` | tytuł łamany na 2 wiersze (`join_wrapped_lines` nie skleja wielkich liter), `ł` -> `l` (`odwolania`), `Ę` -> `E`, etykiety rozdzielone od wartości |

Najsłabsze pole: `przelew_bankowy.tytul` (3/10). Reszta pól >= 80%. Imiona i nazwiska (pola rozmyte): 17/17 oraz
14/14 trafień dokładnych. Wejście dla E4-E5: ekstrakcja tytułu przelewu i nazw spółek musi być odporna na utratę
polskich znaków diakrytycznych, łamanie wierszy i `0`/`o` w formach prawnych (`Sp. z 0.0.`), np. przez normalizację
porównawczą (bez diakrytyków) i słownik form prawnych.

## Wymiana pakietów i CI

- `requirements.txt` zawiera teraz `rapidocr>=3.10` i `onnxruntime>=1.20`; `requirements-ocr.txt` zostaje aliasem
  (`-r requirements.txt` z komentarzem), więc stare polecenie z README działa. Dockerfile bez zmian: wheele `cp313`
  manylinux nie wymagają bibliotek systemowych (opencv-python-headless).
- Wheele dla Pythona 3.13 sprawdzone `pip download --only-binary=:all: --no-deps` (bez kopii, katalog tymczasowy):

| Pakiet | win_amd64 | linux x86_64 |
|---|---|---|
| `onnxruntime` 1.32.0 | `cp313-cp313-win_amd64` (16,7 MB) | `cp313-cp313-manylinux_2_28_x86_64` (27,8 MB) |
| `opencv-python-headless` 5.1.0.95 | `cp37-abi3-win_amd64` | `cp37-abi3-manylinux_2_28_x86_64` (63,7 MB) |
| `rapidocr` 3.10.0 | `py3-none-any` | `py3-none-any` |
| `numpy` 2.5.5, `shapely` 2.2.0 | `cp313` win_amd64 | `cp313` manylinux |
| `pyclipper` 1.4.0 | `cp313-win_amd64` | `cp313-manylinux2014_x86_64.manylinux_2_17_x86_64` |

- Rozmiar instalacji: ok. 107 MB pobrania (opencv 48-64 MB, rapidocr 27 MB, onnxruntime 17-28 MB, numpy 13 MB); w CI
  `actions/setup-python` z `cache: pip` powinno zamortyzować (czas joba do zmierzenia w T4).
- CI i testy nie powinny OCR-ować skanów na żywo: ok. 3,6 min dla 72 stron na tej maszynie, wolniej na dwurdzeniowych
  runnerach GitHub (do zmierzenia). Rozwiązanie to kasety z T4; test `slow` z silnikiem uruchamia jedną stronę (ok. 5 s).
- Ryzyko: `intra_op_num_threads: 4` na maszynie z 2 rdzeniami bywa gorsze niż domyślne; wartość jest w konfiguracji.
