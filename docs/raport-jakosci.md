# Raport jakości jsonix

F1 liczone wg reguł UZP (`eval/score.py`: długie teksty z progiem podobieństwa 80%, reszta dokładnie, listy po treści) na danych treningowych z podziałem `data/splits.yaml`. Holdout jest odłożony od strojenia reguł z jednym wyjątkiem: błędy pełnomocnictw na skanach (E7) diagnozowano na holdoucie, więc holdout@skan dla pełnomocnictw nie jest niezależną oceną. Wygenerowano: `python scripts/quality_report.py`.

## Środowisko

- data: 2026-11-22 06:35 UTC
- commit: 7b45456
- python: 3.14.0
- system: Windows 11
- procesor: AMD64 Family 25 Model 80 Stepping 0, AuthenticAMD
- rdzenie: 16
- cache OCR na starcie: zimny (pusty katalog tymczasowy, `JSONIX_APP_CONFIG` z osobnym `cache_dir`)

## Podsumowanie

| Zbiór | Źródło | F1 | Precyzja | Pełność | Dokumenty | Negatywy | Błędy klasyfikacji | Czas / dokument | Bramka (kod) |
|---|---|---|---|---|---|---|---|---|---|
| dev | tekst | **99.9%** | 99.8% | 100.0% | 162 | 12/12 | 0 | 0.04 s | 0 |
| dev | skan | **99.2%** | 98.4% | 100.0% | 29 | 3/3 | 0 | 7.59 s | 0 |
| holdout | tekst | **99.7%** | 99.4% | 100.0% | 62 | 10/10 | 0 | 0.05 s | 0 |
| holdout | skan | **96.7%** | 96.7% | 96.7% | 13 | 3/3 | 0 | 3.04 s | 0 |

## F1 per typ dokumentu

| Typ | dev tekst | dev skan | holdout tekst | holdout skan |
|---|---|---|---|---|
| odwolanie | 99.8% | 99.7% | 99.7% | 100.0% |
| pelnomocnictwo | 100.0% | 98.0% | 100.0% | 94.3% |
| przelew | 100.0% | 98.7% | 99.4% | 96.8% |

## F1 per pole

Pola z F1 < 0.85 w którymkolwiek zbiorze są pogrubione — wymagają opisu przyczyny. „—” = w tym zbiorze same TN (pola nie ma w dokumentach i wynik poprawnie ma `null`), więc F1 jest niezdefiniowane.

| Pole | dev tekst | dev skan | holdout tekst | holdout skan |
|---|---|---|---|---|
| OdwolanieKIO.czynnosc_dzien | 100.0% | 100.0% | 96.3% | 100.0% |
| OdwolanieKIO.czynnosc_opis | 96.6% | 100.0% | 96.3% | 100.0% |
| OdwolanieKIO.czynnosc_powod_id | 100.0% | 100.0% | 100.0% | 100.0% |
| OdwolanieKIO.data | 100.0% | 100.0% | 100.0% | 100.0% |
| OdwolanieKIO.miejscowosc | 100.0% | 94.1% | 100.0% | 100.0% |
| Odwolujacy[].krs | 100.0% | 100.0% | 100.0% | — |
| Odwolujacy[].nazwa | 100.0% | 100.0% | 100.0% | 100.0% |
| Odwolujacy[].nip | 100.0% | 100.0% | 100.0% | 100.0% |
| Odwolujacy[].pelnomocnik.imie_nazwisko | 100.0% | 100.0% | 100.0% | 100.0% |
| Odwolujacy[].pelnomocnik.mail | 100.0% | 100.0% | 100.0% | 100.0% |
| Odwolujacy[].pelnomocnik.nazwa | 100.0% | 100.0% | 100.0% | 100.0% |
| Odwolujacy[].przez-pelnomocnika | 100.0% | 100.0% | 100.0% | 100.0% |
| Odwolujacy[].regon | 100.0% | 100.0% | 100.0% | 100.0% |
| Zamawiajacy[].krs | 100.0% | — | 100.0% | — |
| Zamawiajacy[].nazwa | 100.0% | 100.0% | 100.0% | 100.0% |
| Zamawiajacy[].nip | 100.0% | 100.0% | 100.0% | 100.0% |
| Zamawiajacy[].prowadzacy_postepowanie | 100.0% | 100.0% | 100.0% | — |
| Zamawiajacy[].regon | 100.0% | 100.0% | 100.0% | — |
| ZamowieniePubliczne.numer_bzp | 100.0% | 100.0% | 100.0% | 100.0% |
| ZamowieniePubliczne.numer_postepowania | 100.0% | 100.0% | 100.0% | 100.0% |
| ZamowieniePubliczne.numer_ted | 100.0% | 100.0% | 100.0% | 100.0% |
| ZamowieniePubliczne.tytul | 100.0% | 100.0% | 100.0% | 100.0% |
| mocodawca[].data.imie_nazwisko | 100.0% | 100.0% | 100.0% | — |
| mocodawca[].data.krs | 100.0% | 100.0% | 100.0% | 100.0% |
| mocodawca[].data.nazwa | 100.0% | 92.3% | 100.0% | 85.7% |
| mocodawca[].data.nip | 100.0% | 100.0% | 100.0% | 100.0% |
| mocodawca[].data.typ | 100.0% | 100.0% | 100.0% | 100.0% |
| **mocodawca[].podpisujacy[].imie_nazwisko** | 100.0% | 93.3% | 100.0% | 80.0% |
| pelnomocnicy[].imie_nazwisko | 100.0% | 100.0% | 100.0% | 100.0% |
| pelnomocnicy[].pesel | 100.0% | 100.0% | — | 100.0% |
| przelew_bankowy.data_operacji | 100.0% | 100.0% | 100.0% | 100.0% |
| przelew_bankowy.kwota | 100.0% | 100.0% | 100.0% | 100.0% |
| przelew_bankowy.na_rachunek | 100.0% | 100.0% | 100.0% | 100.0% |
| przelew_bankowy.numer_transakcji | 100.0% | 100.0% | 96.3% | 100.0% |
| **przelew_bankowy.tytul** | 100.0% | 92.3% | 100.0% | 80.0% |
| przelew_bankowy.z_rachunku | 100.0% | 100.0% | 100.0% | 100.0% |

## Jak czytać czas

Czas / dokument = czas ścienny przebiegu potoku (wczytanie, OCR, klasyfikacja, ekstrakcja, zapis) podzielony przez liczbę dokumentów w zbiorze, na maszynie z sekcji „Środowisko”. UZP ogranicza czas na rozwiązanie (kryteria, pkt 5a), więc najważniejszy jest czas skanów przy zimnym cache OCR.
