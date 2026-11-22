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

## Stabilność pod obciążeniem (E4, 2026-11-22)

**Objaw.** Pierwszy, „zimny” przebieg `python -m eval.gate --split dev --source skan` uruchomiony równolegle z
`pytest` dawał 3-9 błędów klasyfikacji na skanach (za każdym razem inne dokumenty). Kolejne przebiegi: 0 błędów.

**Przyczyna (z dowodem): brak pamięci systemowej (limitu commit), nie niedeterminizm modelu i nie cache.**
- Determinizm: ta sama strona 3x w jednym procesie bez cache (plus ponowny render) daje identyczny tekst
  (sha1 równe) dla odwolania/0009, 0010, potwierdzenia/0001, pelnomocnictwa/0003. Hipoteza (d) odrzucona.
- Pamięć: jeden proces OCR utrzymuje ok. 600 MB commit, szczyt ok. 990 MB (pomiar `GetProcessMemoryInfo`).
  Na maszynie (15,3 GB RAM, plik stronicowania ok. 2 GB) przy pracy innych agentów wolny commit wynosił
  0,6-2,7 GB (zmienny w czasie), więc 3 równoległe procesy OCR + pytest wyczerpują go w szczytach.
- **Z tych 600 MB aż ok. 480 MB to bufory OpenBLAS** rezerwowane przy samym `import numpy` (16 wątków
  logicznych): `import numpy` = +492 MB commit, z `OPENBLAS_NUM_THREADS=1` = +10 MB. Przy braku pamięci
  OpenBLAS przerywa cały interpreter (`OpenBLAS error: Memory allocation still failed after 10 retries,
  giving up`) bez wyjątku Pythona; tak padły bramka i skrypt w 3. przebiegu, a w 2. przebiegu
  `pytest -m "not slow"` skończył się bez podsumowania (exit 1, ucięty na 67%). To ten sam objaw, który inny
  agent zgłosił przy `test_engine_params_passed_to_rapidocr`: test używa podmienionego `RapidOCR`, ale
  `_rapidocr_run` importuje numpy, więc to pierwszy import numpy w szybkich testach wywracał proces.
- Reprodukcja przed poprawką (zimny cache, 4 równoległe procesy: bramka, 2x skrypt ingest+klasyfikacja na
  30 skanach, z cache i bez, plus `pytest -m "not slow"`): bramka **17 błędów klasyfikacji (exit 1)**;
  skrypty: 25/30 i 24/30 dokumentów źle (typ `None`), po 55 nieudanych stron. Komunikaty:
  `onnxruntime ... Fail: [ONNXRuntimeError] : 1 : FAIL : bad allocation` (17 i 24 razy) oraz
  `MemoryError: Unable to allocate 25.1 MiB for an array with shape (1760, 1248, 3)` (38 i 31 razy);
  raz nawet pypdfium2/pypdf nie wczytały PDF-a (`MemoryError`). Hipoteza (a) potwierdzona.
- Mechanizm: `_apply_ocr` łapał wyjątek i zostawiał stronę pustą z ostrzeżeniem, więc dokument bez tekstu
  stawał się „nieznany”. Hipoteza (b) odrzucona: nieudany OCR nie trafiał do cache (wyjątek przed zapisem),
  a pusty plik cache i tak był traktowany jak brak; stąd kolejne przebiegi były zielone (brakujące strony
  liczone od nowa, gdy pamięci już nie brakowało). Hipoteza (c) odrzucona: zapis cache jest atomowy
  (`os.replace`, plik tymczasowy z PID), a uszkodzonych wpisów nie zaobserwowano.

**Poprawka:**
- `odw2json/__init__.py`: `os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")` przed pierwszym importem numpy
  (wartość użytkownika wygrywa). Proces OCR: commit stały 600 -> 120 MB, szczyt 990 -> 510 MB. Czas 7 stron
  (odwolania/0006, bez cache): 36 s przy 16 wątkach BLAS, 32 s przy 1, 30 s przy 4, czyli w granicach szumu,
  bo obliczenia liczy onnxruntime, a numpy tylko konwertuje obrazy.
- `ingest.ocr.max_concurrent_processes: 1` (`config/app.yaml`): slot międzyprocesowy, czyli blokada pliku
  `slot-K.lock` w `%TEMP%/odw2json-ocr-slots` (`msvcrt.locking` / `fcntl.flock`), trzymana na czas jednej
  strony. Szczyty kilku procesów (bramka, pytest, GUI, inne worktree) już się nie nakładają. System zwalnia
  blokadę także po awarii procesu. Po `slot_timeout_s: 900` czekania OCR rusza mimo wszystko (log). 0 albo
  brak klucza = bez limitu (tak działają testy z podmienionym silnikiem). Na tej maszynie równoległość OCR i
  tak nie przyspieszała (tabela wariantów wyżej), więc limit 1 nie kosztuje przepustowości.
- Ponowienia (`odw2json/ingest/ocr.py`): render + silnik do `OCR_ATTEMPTS = 5` prób, z przerwą 2, 5, 10, 20 s
  (plus `gc.collect()`), razem maksymalnie 37 s na stronę. Każda nieudana próba trafia do logu. Przy 4 próbach
  (2/5/10 s) w 1. przebiegu po poprawce zostało po 1 stronie nieudanej na proces.
- Po wyczerpaniu prób: `OcrError`, a w `Document.warnings` wyraźnie
  `OCR nieudany – strona N (Typ: ostatni wiersz komunikatu)` (bez wielowierszowego tracebacku ORT).
- Pusty lub nieudany wynik **nigdy** nie trafia do cache na dysku ani do pamięci procesu (LRU), więc kolejne
  wywołanie znów próbuje silnika.
- Blokada `_ENGINE_LOCK` wokół render + silnik: w jednym procesie (API z pulą wątków) naraz OCR-uje jedna
  strona. Silnik sam wątkuje (`intra_op_num_threads: 4`), więc równoległe wywołania tylko mnożyły szczyt
  pamięci; RapidOCR nie deklaruje bezpieczeństwa wątkowego.
- **Bez** zmniejszania liczby wątków ORT przy ponowieniu: zmierzone, szczyt commit 990 MB przy 1 wątku i
  992 MB przy 4, a osobna instancja silnika dla innych parametrów kosztowałaby kolejne ~500 MB.
- Testy: szybki zestaw (`-m "not slow"`) nie importuje `onnxruntime` ani `rapidocr` (sprawdzone wtyczką
  pytest na końcu sesji). Testy z prawdziwym silnikiem mają `slow` + `ocr_live`. Nowe testy: silnik rzucający
  wyjątek co drugie wywołanie, brak cache dla pustych i nieudanych wyników, krótkie ostrzeżenie, blokada w
  procesie (6 wątków, szczyt 1), slot międzyprocesowy (wyłączność, czekanie, limit czasu, 0 = wyłączony),
  walidacja kluczy, `OPENBLAS_NUM_THREADS` w podprocesie.

**Reprodukcje** (zimny cache, 4 procesy naraz: bramka `--source skan`, skrypt ingest+klasyfikacja 30 skanów
z cache (A) i bez cache (B), `pytest -m "not slow"`):

| Przebieg | Kod | Bramka (błędy klas.) | A: źle / nieudane strony | B: źle / nieudane strony | pytest |
|---|---|---|---|---|---|
| przed | stary | 17 (exit 1) | 25/30 / 55 | 24/30 / 55 | exit 0 |
| po 1 | ponowienia 4x, cache, blokada | 0 (exit 0) | 0/30 / 1 | 0/30 / 1 | exit 0 |
| po 2 | ponowienia 5x | 1 (exit 1, potwierdzenia/0007) | 1/30 / 1 | 0/30 / 1 | exit 1 (crash OpenBLAS) |
| po 3 | + slot międzyprocesowy | crash OpenBLAS przy imporcie | 0/30 / 0 | crash OpenBLAS | exit 0 |
| po 4 (częściowy) | pełna poprawka (+ OpenBLAS 1 wątek) | przerwany (limit czasu) | 0/5 / 0 | 0/10 / 0 | exit 0 |

Przebieg „po 4” przerwano po ok. 6 min z powodu limitu czasu zadania: do tego momentu zero nieudanych prób
OCR (ani jednej linii „próba N/5 nieudana” w żadnym procesie). Z limitem 1 slotu trzy procesy OCR-ują
strony po kolei, więc pełny przebieg 3 x 72 stron trwa ok. 3x dłużej niż pojedynczy. **Do zrobienia:** pełny
przebieg po 4 i drugi przebieg (zimny cache + równoległe procesy) na pełnej poprawce, oba z wynikiem 0 błędów.

Wolny commit przed przebiegami „po 2” i „po 3”: 1,5-1,6 GB, w trakcie spadł do 0,64 GB (inne procesy na
maszynie), stąd awarie OpenBLAS przy imporcie, zanim jakikolwiek kod OCR ruszył.

## Ryzyka

- `Global.use_cls: false` (klasyfikator kąta wyłączony) przyspiesza OCR, ale strony obrócone o 90/180° w skanach
  od jury zostaną źle odczytane. Próbka UZP nie zawierała takich stron.
- Mitygacja, gdyby się pojawiły: ponownie włączyć `use_cls` w `config/app.yaml` (koszt ok. 2x czasu na stronę).
