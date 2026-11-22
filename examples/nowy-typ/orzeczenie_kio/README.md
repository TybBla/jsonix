# Przykład: 4. typ dokumentu samą konfiguracją — orzeczenie KIO

Ten katalog pokazuje, że **nowy typ dokumentu dodaje się bez zmian w kodzie**. Przykładem jest orzeczenie
Krajowej Izby Odwoławczej (wyrok albo postanowienie). Wszystko to pliki konfiguracji:

| Plik | Co robi |
|---|---|
| `config/doctypes/orzeczenie_kio.yaml` | reguły rozpoznania typu (`classify`) i ekstrakcji 8 pól (`fields`) |
| `config/schemas/orzeczenie_kio.json` | szablon wyniku: kolejność kluczy, `null` gdy brak |
| `config/lookups/rozstrzygniecie_kio.yaml` | słownik rozstrzygnięć z sentencji (oddala, uwzględnia, odrzuca, umarza) |

## Wypróbuj (ok. 1 minuty)

```powershell
copy examples\nowy-typ\orzeczenie_kio\config\doctypes\* config\doctypes\
copy examples\nowy-typ\orzeczenie_kio\config\schemas\* config\schemas\
copy examples\nowy-typ\orzeczenie_kio\config\lookups\* config\lookups\
python -m odw2json doctypes                 # na liście jest orzeczenie_kio
mkdir input\demo-kio
copy "data\train\negatywne\KIO_KIO 2617-21.pdf" input\demo-kio\
python -m odw2json run                      # output\demo-kio\KIO_KIO 2617-21.json
```

Wynik dla postanowienia KIO 2617/21:

```json
{
  "OrzeczenieKIO": {
    "sygnatura": "KIO 2617/21",
    "rodzaj": "postanowienie",
    "data": "2021-09-20",
    "przewodniczacy": "Ewa Kisiel",
    "odwolujacy": "TAMEXOBIEKTY SPORTOWE S.A.",
    "zamawiajacy": "Gmina Cieszyn",
    "rozstrzygniecie": "odrzuca",
    "kwota_wpisu": 10000.0
  }
}
```

Trace (`output\.trace\`) i GUI (podświetlenie źródła w PDF) działają dla nowego typu tak samo jak dla trzech
podstawowych, bo korzystają z tych samych danych. Zamawiający jest brany najpierw z uzasadnienia
(„Gmina Cieszyn z siedzibą w Cieszynie (dalej: „Zamawiający”)” — mianownik), a dopiero gdy go brak, z komparycji
(„prowadzonym przez …”), gdzie forma jest taka jak w dokumencie (zwykle biernik). Silnik nie odmienia nazw firm.

**Po pokazie usuń te trzy pliki z `config/`** i sprawdź: `python -m odw2json doctypes` pokazuje **3 typy**, a `python -m eval.gate --split dev --source tekst` ma negatywy **12/12** (exit 0). Według zadania UZP orzeczenia KIO są dokumentami spoza typów i
mają dawać `{}`. Pilnuje tego test `tests/test_nowy_typ_konfiguracja.py::test_new_type_is_not_active_in_delivered_config`.

## Jak to jest sprawdzane
`tests/test_nowy_typ_konfiguracja.py` (bez żadnej zmiany w `odw2json/`):
- typ z przykładu działa na prawdziwym PDF-ie i na innym brzmieniu (wyrok, inne strony i rozstrzygnięcie);
- wyniki trzech podstawowych typów są identyczne z typem dodanym i bez niego;
- **nowe pole** w istniejącym typie (waluta przelewu) też da się dodać samą konfiguracją: klucz w szablonie i
  reguła w YAML;
- katalog przykładu zawiera wyłącznie pliki YAML, JSON i Markdown.

Opis wszystkich opcji `classify`, `fields` i `lists`: [docs/nowy-typ-dokumentu.md](../../../docs/nowy-typ-dokumentu.md).
