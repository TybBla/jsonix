# Kryteria i ustalenia UZP — jedno źródło prawdy

Zebrane z: regulaminu zadania „Odwołania2json” (HackNation 2026), pełnej treści zadania, prezentacji wyzwania, FAQ v1.0, README repozytorium organizatora (https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026) oraz odpowiedzi UZP na Discordzie (21.11.2026). W razie sprzeczności obowiązuje **najnowsze ustalenie** (Discord / README), a te nadpisują wcześniejsze punkty.

## 1. Zadanie
- Wejście: dokumenty PDF sprawy odwoławczej KIO. Rozwiązanie **rozpoznaje typ** (klasyfikacja po **treści**, nie po nazwie pliku) i **wyodrębnia dane** do JSON zgodnego ze schematem UZP (`data/oczekiwane-json/*.json`).
- Typy: **odwołanie**, **pełnomocnictwo**, **potwierdzenie przelewu**.
- Dokument spoza tych typów: **plik `<nazwa_pdf>.json` z zawartością dokładnie `{}`** (UZP, Discord 13:50).
- Brak informacji w dokumencie → `null`; nie zmyślać danych.
- JSON **ściśle zgodny z formatem** (bez dodatkowych pól).
- Dane testowe: syntetyczne, oparte na realnych sprawach; **zawierają też skany bez warstwy tekstowej** (UZP dodało `dane/skany/` — OCR obowiązkowy).

## 2. Wymagania techniczne i formalne
- **Python 3.13+**, `requirements.txt`, uruchomienie z **CLI** / wrappera (`start.bat`).
- Foldery **`input/`** i **`output/`** w katalogu głównym; wynik `output/<sprawa>/<nazwa_jak_pdf>.json`.
- Wyłącznie komponenty **open source**; laptop testowy: i7, 16 GB RAM, **bez GPU**, z internetem, bez limitu czasu.
- LLM (opcjonalny): **open source**, przez API **firmy z serwerami w UE/EOG**, która ma **Politykę Prywatności określającą zakres i miejsce przetwarzania danych**; dostarczamy klucz API. **Hosting przez osobę prywatną (własny komputer/serwer) wykluczony.**
- Zgłoszenie: tytuł projektu + link do GitHub z działającym prototypem (wgranie dokumentów i odczyt wyników). Dodatkowo: dokumentacja techniczna (w tym opis użytego LLM), wyniki testów jakości.
- Warunek wypłaty nagrody (regulamin §3.5): kod źródłowy, instrukcja uruchomienia, **Docker Compose**, dokumentacja: **opis architektury, konfiguracja ekstrakcji danej klasy dokumentów, dodawanie nowej klasy dokumentów**.
- Regulamin §4: uczestnik oświadcza, że jest twórcą rozwiązania; rozwiązania zewnętrzne trzeba wskazać w prezentacji. **W repo nie umieszczamy atrybucji narzędzi AI w commitach/PR** (decyzja zespołu).

## 3. Ocena
- **Etap 1 (preselekcja): 100% F1** na ukrytym zbiorze (≥ 10 spraw).
- **Etap 2 (finał, max 3 zespoły): 50% F1 + 50% elastyczność**, w tym:
  - 1–20 pkt za **moc modelu LLM** wg **średniej liczby parametrów wszystkich użytych modeli** (przy MoE liczą się parametry ogółem, nie aktywne): **≤ 8B = 20**, >8–14B = 18, >14–32B = 12, >32–70B = 8, >70–150B = 4, >150B = 0. Bez LLM = maksimum (UZP Discord 13:52). Przykład UZP: modele 3B i 32B → średnia 17,5B → 12 pkt. **Wniosek: każdy model ≤ 8B nie kosztuje punktów; nie mieszamy z większymi.**
  - 1–20 pkt za **łatwość dodawania nowych typów dokumentów i pól bez przebudowy** (konfiguracja zamiast kodu),
  - 1–10 pkt za **inne funkcje** (np. GUI).
- GUI nie jest wymagane, ale punktowane; idealnie: wgranie PDF, uruchomienie analizy, **podgląd dokumentu obok wyodrębnionych danych**.
- Premiowane: konfiguracja nowych klas bez zmian kodu, **transparentność ekstrakcji**.

## 4. Jak liczone jest F1 (UZP)
- TP: wartość w JSON zgodna z GT; TN: brak w JSON i w GT; FP: wartość tylko w JSON albo niezgodna; FN: brak w JSON, jest w GT.
- **Długie stringi z progiem podobieństwa 80%** (UZP, Discord 13:26): nazwa firmy pełnomocnika, tytuł przelewu, nazwa Odwołującego/Zamawiającego, tytuł zamówienia. **Wszystko inne dokładnie** (KRS, NIP, daty, kwoty, imiona, opis czynności…).
- Listy dopasowywane **po treści** (nie po kolejności).

## 5. Ustalenia szczegółowe (Discord UZP, 21.11.2026)
- 60 przykładów treningowych (prezentacja mówiła o 39 — nieaktualne); `ground_truth.yaml` usunięty (to były scalone JSON-y).
- `czynnosc_powod_id` 1–12, słownik `data/oczekiwane-json/czynnosc_powod_id_dict.md`; 12 = „Projektowane postanowienia umowy”; 6 = „Odpowiedzi/wyjaśnienia do SWZ” (**ze skośnikiem**). `czynnosc_opis` ustalany wyłącznie z **pierwszego zarzutu**.
- Sumy kontrolne NIP/REGON/PESEL w danych demo są celowo błędne — **nie walidujemy sum**, tylko format.
- **Imiona i nazwiska w mianowniku** (np. „Mateusz Szymański”, nie „Mateusza Szymańskiego”).
- Maszyna oceniająca ma internet; brak limitu czasu.

## 6. Gdzie to jest w projekcie
- Architektura i decyzje: `docs/superpowers/specs/2026-11-21-odwolania2json-design.md`, `docs/decyzje/`.
- Roadmapa i zakres v1.0: `docs/superpowers/plans/2026-11-21-roadmap-produkcyjna.md` (sekcja „Aktualizacja zakresu”).
- Ewaluacja (F1 wg reguł z pkt 4): `eval/score.py`, bramka `python -m eval.gate`.
