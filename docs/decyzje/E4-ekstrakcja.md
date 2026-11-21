# E4 — decyzje: ekstrakcja pól

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
