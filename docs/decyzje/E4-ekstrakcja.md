# E4: ekstrakcja pól (reguły YAML)

## Odwołanie (E4-T4)

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
