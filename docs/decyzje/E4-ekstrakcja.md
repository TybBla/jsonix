# E4 — decyzje: ekstrakcja pól

## odwołanie (E4-T4)

Reguły: `config/doctypes/odwolanie.yaml` (sekcje `fields`, `lists`), słownik fraz powodu
`config/lookups/czynnosc_powod_frazy.yaml`, testy `tests/test_extract_odwolanie.py`. Strojenie tylko na `dev`;
holdout uruchomiony raz, na końcu.

### Układy dokumentów w danych
- **A (warstwa tekstu, przykład 01–39 i 42–60):** bloki `Odwołujący:` / `Zamawiający:` w dowolnej kolejności
  (nazwa w następnej linii), `dotyczy: … pn. "TYTUŁ", nr referencyjny: X, BZP/TED`, tytuł `ODWOŁANIE`, potem
  zdanie **„Zamawiający w dniu D <czynność>.”**, dalej zarzuty. Dłuższe wersje (42+): konsorcjum
  (`1) Lider Konsorcjum:`), CEIDG (`… pod firmą` + nazwa), wielu zamawiających
  (`1) Zamawiający – Lider, prowadzący postępowanie:`), `Wykonawca wybrany …` po stronach.
- **B (skany, OCR):** `Odwołujący: Nazwa` w jednej linii, `reprezentowany przez pełnomocnika:` + lista, lista
  czynności `wnoszę odwołanie wobec: 1. <czynność> … w dniu D; 2. …`. OCR gubi cudzysłów otwierający tytułu,
  przestawia kolumny (data czynności trafia za `2.`), myli `0`/`o` w numerach i `Ł`/`L`.

### Kluczowe decyzje
- **`czynnosc_powod_id`** = klasyfikacja **pierwszej** zaskarżonej czynności słownikiem fraz (konfiguracja, nie
  kod). Kolejność wpisów = priorytet: zaniechania (`nie odrzucił`, `zaniechał wykluczenia`, `zaniechawszy
  unieważnienia`) przed czynnościami (odrzucenie, wykluczenie, wybór), a dokumenty szczegółowe (odpowiedzi /
  modyfikacja SWZ, OPZ, PPU) przed samą publikacją SWZ. Okna (kolejne wpisy `phrase_lookup` z `within`):
  1) zdanie „Zamawiający w dniu …” do `Uprzednio/Wcześniej/Następnie` (dalej są inne, wcześniejsze czynności);
  2) punkt `1.` listy „wnoszę odwołanie wobec:” / „polegających na: 1)” (do `2.`); 3) tytuł `Zarzut nr 1`.
  W danych tytuł pierwszego zarzutu bywa niezwiązany z GT (np. „zaniechania wezwania do wyjaśnień” przy
  publikacji SWZ), dlatego zarzut jest dopiero trzecim źródłem.
- **`czynnosc_dzien`**: data po „Zamawiający w dniu”, inaczej najbliższa data po `1.` listy czynności (okno 400
  znaków, bo OCR przestawia kolumny). Brak — `null`.
- **`data`/`miejscowosc`**: tylko linia `Miejscowość, (dnia) DATA` (przecinek opcjonalny dla OCR). Brak linii →
  `null` (w 1/4 GT puste; innych dat nie zgadujemy).
- **Odwołujący**: lista z 1 elementem (schemat UZP: konsorcjum → Lider). Nazwa: `Lider Konsorcjum:` / `1) X
  (Lider Konsorcjum)` / linia po `pod firmą` / reszta linii albo następna linia po `Odwołujący:`.
  `przez-pelnomocnika`: `flag` na „reprezentowany przez”/„pełnomocnik”, inaczej 0. Pełnomocnik: pierwsza osoba
  po „reprezentowany przez” (tytuły pomija wzorzec wielkiej litery, mianownik przez `name`), firma = początek
  „adresu do korespondencji” (do przecinka; adres `ul. …` odrzucany walidatorem, wtedy fragment z „Kancelaria”),
  e-mail najbliższy po „reprezentowany przez”.
- **Zamawiający**: elementy od `N)` w bloku; `prowadzacy_postepowanie` = 1 dla elementu z „prowadzący/lider”
  (w nagłówku elementu albo linia „– Zamawiający prowadzący postępowanie”), 0 dla pozostałych numerowanych,
  `null` gdy zamawiający jest jeden (brak numeracji).
- **Zamówienie**: tylko nagłówek (zakres do „Działając w imieniu”/„Zarzut”/„Uzasadnienie”) — w uzasadnieniach
  są numery BZP/TED innych postępowań. Numer postępowania: token z cyfrą po etykiecie, z wykluczeniem wzorców
  TED (`NNNNNN-RRRR`) i BZP; TED po etykiecie (TED / Dz. Urz. UE), postać `RRRR/S NNN-NNNNNN` gdziekolwiek
  w nagłówku, a dla OCR także `NNNNNN-RRRR` przed etykietą. BZP z normalizacją OCR `o`→`0`.

### Rozszerzenia silnika (`odw2json/extract/engine.py`, przez rejestr; opis w `docs/nowy-typ-dokumentu.md`)
- ekstraktor `flag` — wartość (domyślnie 1), gdy w zakresie jest fraza (z `- const: 0` jako „inaczej”);
- ekstraktor `phrase_lookup` — klasyfikacja zakresu słownikiem `config/lookups/<nazwa>.yaml`
  (lista `{id, phrases}`, kolejność = priorytet);
- wspólna opcja **`within`** dla wszystkich ekstraktorów — okno `{after, before, max_chars}` albo lista okien
  zawężanych kolejno (wcześniej zakres był tylko per pole: `scope`); walidacja kluczy przy ładowaniu;
- normalizator `ocr_digits` (`o`/`O` w ciągu cyfr → `0`);
- `Ctx.config_dir` — ekstraktory czytają lookupy z katalogu konfiguracji typu (testy z `tmp_path`).

### Wyniki (F1 per pole, `python -m eval.gate`)

| Pole | dev tekst (29+17 PDF) | dev skan (9 OCR) | holdout tekst |
|---|---|---|---|
| **typ odwolanie** | **0,9984** | **0,9968** | **0,9965** |
| OdwolanieKIO.data | 1,0000 | 1,0000 | 1,0000 |
| OdwolanieKIO.czynnosc_dzien | 1,0000 | 1,0000 | 0,9630 |
| OdwolanieKIO.czynnosc_powod_id | 1,0000 | 1,0000 | 1,0000 |
| OdwolanieKIO.czynnosc_opis | 0,9663 | 1,0000 | 0,9630 |
| OdwolanieKIO.miejscowosc | 1,0000 | 0,9412 | 1,0000 |
| Odwolujacy[].* (krs, nazwa, nip, regon, przez-pelnomocnika, pelnomocnik.*) | 1,0000 | 1,0000 | 1,0000 |
| Zamawiajacy[].* (krs, nazwa, nip, regon, prowadzacy_postepowanie) | 1,0000 | 1,0000¹ | 1,0000 |
| ZamowieniePubliczne.* (numer_bzp, numer_postepowania, numer_ted, tytul) | 1,0000 | 1,0000 | 1,0000 |

¹ Na skanach dev `Zamawiajacy[].krs` ma w GT same `null` (wszystkie TN — F1 nieokreślone, gate pokazuje 0).

Pól z F1 < 0,8 brak. Uwagi do pól < 1:
- `czynnosc_opis` (dev tekst): GT niespójne — 4 pliki mają „Odpowiedzi i wyjaśnienia do SWZ”, 1 „Odpowiedzi/
  wyjaśnienia do SWZ”. Zgodnie z ustaleniem UZP (Discord 21.11 13:43) zostawiamy wersję ze skośnikiem
  (`config/lookups/czynnosc_powod.yaml`); `czynnosc_powod_id` jest w 100% poprawne.
- `miejscowosc` (skan): OCR czyta „Łódź” jako „Lódź” — wartość błędna (FP); bez słownika miejscowości nie do
  odróżnienia od prawdziwej nazwy.
- `czynnosc_dzien` (holdout, 1 dokument): nie strojone (holdout tylko do kontroli).

### Znane ryzyka
- Nazwa zamawiającego zawinięta na 2 linie jest doklejana, dopóki następna linia nie zawiera cyfry ani nie
  zaczyna się od `ul./KRS/NIP/e-mail/…`; nazwa zawierająca cyfrę w 2. linii zostanie ucięta (próg 80% zwykle
  wystarcza).
- `przez-pelnomocnika` = 0 przy braku frazy o reprezentacji — w danych dev zawsze 1 (brak przykładów 0).
- Pierwszy przebieg `--source skan` na zimno (OCR bez cache, równolegle z `pytest`) dał 3 błędy klasyfikacji
  (dwa odwołania, jedno potwierdzenie przelewu, w tym typ nietknięty w T4); ponowny przebieg: 0 błędów.
  Wygląda na niedeterminizm OCR pod obciążeniem — do zbadania w E2b/T6.

### Odporność — odwołanie
Recenzja odporności (warianty tekstu dev w pamięci, F1 wg reguł UZP) wykazała, że reguły trzymały się dosłownych
etykiet i układu linii z danych. Poprawki są wyłącznie w `config/doctypes/odwolanie.yaml` (sekcja `classify` bez
zmian); testy: `tests/test_extract_robustness_odwolanie.py` (warianty na 46 dev PDF-ach z warstwą tekstu, próg F1 ≥ 0,97,
`MIN_DOCS` = 10) oraz `test_party_label_synonyms_and_name_boundaries` w `tests/test_extract_odwolanie.py`.

| Wariant (dev, odwołania) | n | F1 przed | F1 po |
|---|---|---|---|
| `Odwołujący:` → `Wykonawca wnoszący odwołanie:` | 46 | 0,726 | 0,998 |
| `Zamawiający:` → `Instytucja zamawiająca:` | 45 | 0,888 | 0,998 |
| zamiana kolejności stron (Zamawiający przed Odwołującym) | 46 | 0,998 | 0,998 |
| zawinięcie całego tekstu do 55 znaków (nazwa kancelarii) | 46 | 0,985 | 0,998 |
| odwinięcie linii (adres „doklejony” do nazwy) | 46 | 0,993 | 0,998 |

Holdout (kontrola, bez strojenia): te same warianty 0,996–0,997 (= bazowy F1 typu).

- **Etykiety stron — synonimy:** `Odwołujący się`, `Wykonawca wnoszący odwołanie`, `Wykonawca (Odwołujący)`;
  `Instytucja/Strona/Podmiot zamawiająca/-y`, `Zamawiający – nazwa`. Obsługa w `lists.*.split.start/end`
  (początek bloku jednej strony = koniec bloku drugiej, w dowolnej kolejności — wcześniej blok Zamawiającego po
  zamianie „połykał” dane Odwołującego, bo nie widział własnego końca) oraz w etykietach `nazwa`.
- **Nazwa strony ucinana przed dopiskami w tej samej linii:** przecinek, ` ul.`/` al.`/` pl.`/` os.`,
  `reprezentowan…`, `KRS/NIP/REGON/tel./e-mail/adres`, kod pocztowy `\d\d-\d\d\d` (wzorzec wartości `&name_line`,
  współdzielony przez Lidera konsorcjum, „pod firmą” i etykietę Odwołującego; dla Zamawiającego dodatkowo jedna
  zawinięta linia).
- **Nazwa kancelarii pełnomocnika:** do przecinka lub ` ul.`, ale kontynuuje w następnych liniach (dowolne
  zawinięcie), dopóki linia nie zaczyna się od adresu (`ul./al./pl./os.`), cyfry, `tel.`/`e-mail`/`KRS`/`NIP`/`@`
  ani nagłówka kolejnej sekcji (`dotyczy`, `Zamawiający`, `Odwołujący`, …). Wcześniej linia wyłącznie do końca wiersza
  („Kancelaria Adwokacka Spółka z”).
- **Nazwisko pełnomocnika wersalikami:** wzorzec przyjmuje `Jan NOWAK` / `JAN NOWAK` (z pominięciem tytułów
  `ADWOKAT`, `RADCA PRAWNY`, …), pole ma jawne `normalize: [ws, name]`; zamiana na `Jan Nowak` należy do `names.py`
  (osobna zmiana). Test końcowy dopasowania `Jan Nowak` ma `xfail(strict=False)` do czasu jej scalenia.
- **Poza zakresem tej poprawki (zostaje):** `b12` (numer BZP z przyrostkiem `/01` wg GT bez przyrostka — zgodne
  z `bzp` w `normalize.py`), `d1` (brak numeru TED → pojedyncze FP przy innych liczbach), `d3` (brak linii
  „Miejscowość, data” → `null`; zamierzone).

## pełnomocnictwo (E4-T5)

Reguły: `config/doctypes/pelnomocnictwo.yaml`, testy: `tests/test_extract_pelnomocnictwo.py`.

**Układy w danych (dev).** `§ 1. Mocodawca / § 2. Pełnomocnik`; tabela „Mocodawca … / Pełnomocnicy … /
Zamawiający”; „Działając w imieniu X (dalej: …)”; nagłówek `MOCODAWCA` / `PEŁNOMOCNIK`; „X z siedzibą w …
udzielam pełnomocnictwa adw. …”; „Ja, niżej podpisany(a), … do reprezentacji X (KRS …)”; „X, ul. … (dalej:
"Mocodawca"), … udziela pełnomocnictwa: r. pr. …”; osoba fizyczna („Ja, niżej podpisany Jan Nowak, prowadzący
działalność gospodarczą pod firmą …”); konsorcjum („(Konsorcjum): 1) A …; 2) B … (dalej łącznie …”, podpisy
w blokach „W imieniu A:”). Skany (OCR): „reprezentowana przez: Jan Nowak - Prezes Zarządu (dalej …)”,
pełnomocnicy bez tytułów (każdy w linii, „1. Jan Nowak – adwokat”, „Jan Nowak (adwokat …) oraz …”).

**Decyzje.**
- Imię i nazwisko = dwa wyrazy z wielkiej litery (nazwisko może mieć człon po myślniku), regexy z `case: true`.
  Tytuły `adw.`, `r. pr.`, `radca prawny`, `adwokat` tylko wyznaczają początek elementu, nie wchodzą do wartości.
  W dokumentach imiona stoją już w mianowniku; normalizator `name` (T3) nie zmienia żadnego imienia z GT.
- **Mocodawca**: konsorcjum rozpoznajemy po słowie „konsorcj” (elementy = pozycje `1)`, `2)` po „Konsorcjum):”
  lub „;”); bez niego jeden element = cały dokument. Nazwa: kolejne ekstraktory od najpewniejszego (pod firmą /
  „Mocodawcą jest”, „w imieniu”, „do reprezentacji”, pozycja konsorcjum / „z siedzibą” / „Mocodawca X” /
  `MOCODAWCA` + linia / „X, ul.” / nagłówek). Nazwa oceniana **dokładnie** — wycinamy do przecinka przed adresem,
  `(` albo „z siedzibą”, bez rozwijania skrótów i bez obcinania kropek („S.A.”). `typ` = `osoba_fizyczna`, gdy
  w tekście mocodawcy jest „prowadzący(/a) działalność gospodarczą” / CEIDG, inaczej `osoba_prawna`;
  `imie_nazwisko` tylko dla osoby fizycznej („podpisany X, prowadzący”). NIP z myślnikami w dowolnym układzie
  (`999-99-29-154`), okno 160 znaków (OCR wstawia adres między etykietę i numer). KRS 10 cyfr, PESEL 11 cyfr
  jako **string**.
- **Podpisujący**: blok od pierwszej linii kropek / „reprezentowana przez:” / „podpisany przez” / „Za Mocodawcę”
  do „Pełnomocnictwo przyjmuję” albo „(dalej”; osoba = linia z samym imieniem i nazwiskiem (pomijamy linie
  funkcji „Prezes Zarządu”, „Za X sp. z o.o.”) albo nazwisko po „przez:”/przecinku przed „- funkcja”.
  Konsorcjum: `i`-ty blok „W imieniu X:” należy do `i`-tego mocodawcy (rozszerzenie `groups`). Powtórzenia
  (ta sama osoba w treści i pod podpisem) usuwa `unique`.
- **Pełnomocnicy**: blok od „udzielam/udziela pełnomocnictwa”, „ustanawiam pełnomocnikiem”, „upoważniam”,
  „Pełnomocnik(cy)” do „do reprezentowania” / „Zamawiający” / „Pełnomocnictwo udzielone” / „§ 3” / „Niniejszym” /
  tytułu dokumentu — dzięki temu podpisy „Pełnomocnictwo przyjmuję” na końcu nie dublują osób.

**Rozszerzenia silnika (generyczne, opis w `docs/nowy-typ-dokumentu.md`).**
`split.item_regex` (elementy od trafień regexu na oryginale z rozróżnianiem wielkości liter — tekst złożony
jest małymi literami, więc nie odróżnia nazwiska od zwykłych słów), `lists.<L>.groups` (lista zagnieżdżona
szukana w `i`-tym bloku całego dokumentu), `lists.<L>.unique` (bez pustych elementów i duplikatów, trace
z kolejnymi indeksami), ekstraktor `if_match` (stała, gdy fraza występuje). Zmiany: `odw2json/extract/engine.py`,
`odw2json/config_loader.py` (`SplitSpec.item_regex`, `ListSpec.groups`, `ListSpec.unique`).

**Wyniki (F1 typu pelnomocnictwo, `python -m eval.gate --source …`).**

| pole | dev tekst | dev skan | holdout tekst |
|---|---|---|---|
| `mocodawca[].data.imie_nazwisko` | 1,000 | 1,000 | 1,000 |
| `mocodawca[].data.krs` | 1,000 | 1,000 | 1,000 |
| `mocodawca[].data.nazwa` | 1,000 | 0,923 | 1,000 |
| `mocodawca[].data.nip` | 1,000 | 1,000 | 1,000 |
| `mocodawca[].data.typ` | 1,000 | 1,000 | 1,000 |
| `mocodawca[].podpisujacy[].imie_nazwisko` | 1,000 | 0,933 | 1,000 |
| `pelnomocnicy[].imie_nazwisko` | 1,000 | 1,000 | 1,000 |
| `pelnomocnicy[].pesel` | 1,000 | 1,000 | (tylko TN) |
| **typ pelnomocnictwo** | **1,000** | **0,980** | **1,000** |

**Znane problemy.**
- Skan `skany/pelnomocnictwa/0010`: GT ma `nazwa: null`, choć dokument podaje „pod firmą Paweł Brzozowski …”
  — zwracamy nazwę (FP); reguły nie da się uzasadnić bez zgadywania.
- Skan `0008`: OCR „Zawadżki” w „reprezentowana przez:” — podpisujący ze złą literą (FP + FN).
- Nazwisko jednoczłonowe z małą literą po myślniku, imiona trzyczłonowe i nazwiska z apostrofem nie są
  rozpoznawane (brak w danych).

### Odporność — pełnomocnictwo

Testy: `tests/test_extract_robustness_pelnomocnictwo.py` (warianty prawdziwych tekstów dev w pamięci, każdy na
≥ 10 dokumentach, próg F1 ≥ 0,97). Wyniki F1 typu (46 dokumentów dev z warstwą tekstową):

| wariant | n | przed | po |
|---|---|---|---|
| bez zmian | 46 | 1,000 | 1,000 |
| wstęp: „umocowuję” | 40 | 0,901 | 1,000 |
| wstęp: „udzielam umocowania” | 25 | 0,873 | 1,000 |
| wstęp: „ustanawiam pełnomocnikami” | 25 | 1,000 | 1,000 |
| wstęp: „upoważniam do reprezentowania” | 25 | 0,886 | 1,000 |
| wstęp: „niniejszym umocowujemy” | 25 | 0,870 | 1,000 |
| nazwiska WIELKIMI (całe imię i nazwisko) | 46 | 0,736 | 1,000 |
| nazwiska WIELKIMI (samo nazwisko) | 46 | 0,736 | 1,000 |
| etykieta „MOCODAWCA” wersalikami | 21 | 0,983 | 1,000 |
| puste linie podwojone | 46 | 0,978 | 1,000 |

**Decyzje.**
- **Wersaliki.** `normalize_name` zamienia człon zapisany w całości wielkimi literami (≥ 2 litery) na postać
  tytułową („JAN NOWAK-JEZIORAŃSKI” → „Jan Nowak-Jeziorański”) **przed** odmianą; GT UZP ma zawsze postać
  tytułową, więc dawny wynik „JAN KOWALSKI” dla „JANA KOWALSKIEGO” był błędny (test zmieniony świadomie).
  Wzorce imion w YAML dopuszczają człon tytułowy albo wersalikowy; linie funkcji („PREZES ZARZĄDU”) odrzuca
  lookahead bez rozróżniania wielkości liter. Wersalikowy człon musi zaczynać się na granicy wyrazu
  (inaczej `[A-Z]{2,}` zaczynałby w środku „NOWAK”).
- **Wstęp pełnomocników.** Zapowiedź: „udziel* pełnomocnictw*/umocowan*”, „ustanawia* pełnomocnik*”,
  „upoważniam/-my/-ją/-a” (bez „upoważniona do reprezentacji”) z opcjonalnym „do reprezentowania (mnie|nas|…)”
  zjadanym w całości, „umocowuj*”, „niniejszym …”. Koniec bloku „do reprezentowania” nie ucina po
  „upoważniam”, „niniejszym” nie ucina przed czasownikiem nadania, a goła linia „Mocodawca:” (blok podpisu)
  kończy listę pełnomocników.
- **Mocodawca.** Etykieta „Mocodawca/MOCODAWCA” w dowolnej wielkości liter nie wchodzi do `nazwa`
  (opcjonalna etykieta przed wartością we wzorcach „X z siedzibą”, „X, ul.”, „X⏎ul.”); adres w następnej linii
  i nazwa zawinięta na 2 linie tolerują puste linie (`\n{1,2}`, `(?:[ \t]*\n)*`).
- **`typ`.** `const: osoba_prawna` zastąpiony `if_match` na frazach opisujących stronę (NIP/KRS/REGON,
  „siedzib”, „mocodawc”, forma prawna, gmina/powiat); pusty lub bezładny tekst daje `null`. DSL nie ma
  warunku „wypełnij tylko, gdy inne pole mocodawcy niepuste” (ekstraktory nie widzą wartości innych pól),
  więc to przybliżenie; ścisły warunek wymagałby zmiany silnika (`engine.py`) — poza zakresem tego zadania.

**Ograniczenia.** Imię i nazwisko z członem jednoliterowym wersalikiem („J. KOWALSKI”) nie jest wzorcem
imienia; warianty „Mocodawca”/„MOCODAWCA” jako goły nagłówek nad nazwą rozpoznaje tylko forma wersalikowa.
