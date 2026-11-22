## GUI: czytelne „Dlaczego ten typ?” i kontrast podświetleń w PDF

Gałąź `etap/E9-dlaczego-typ` → `main`. Zmiany tylko w `web/`, testach i `docs/gui.md`.

### Co się zmienia
- **„Dlaczego ten typ?” po ludzku.** Po E3 tabela wyników pokazywała surowe cechy klasyfikatora, np. `strong: 'odwolanie' (+2)`. Nowy moduł `web/static/js/evidence.js` (czysta funkcja, testy w Node) zamienia je na zdania:
  - „Tytuł w nagłówku dokumentu: „odwolanie”.”;
  - „Słowa kluczowe tego typu: …”, „Słowa pomocnicze: …”, „Pasujące wzorce tekstu: 2.”;
  - „Słowa typowe dla innego dokumentu (obniżają wynik): …”, „Nagłówek innego rodzaju pisma (obniża wynik): …”;
  - powody odrzucenia: „Za mało cech, żeby rozpoznać typ. Najbliżej było: Pełnomocnictwo.”, „Dokument pasuje do kilku typów podobnie…” oraz „Brak cechy wymaganej dla typów: …”;
  - przy dokumencie nieznanym cechy są nazwane wprost jako cechy najbliższego typu („Słowa kluczowe typu Pełnomocnictwo: …”).

  Surowe cechy zostają pod rozwijanymi „Szczegółami technicznymi”, dla transparentności. Nieznany format cechy jest pokazywany bez zmian, więc nowe cechy klasyfikatora nie znikną z GUI.
- **Poprawka dostępności: kontrast podświetleń w trybie wysokiego kontrastu.** Strona PDF zostaje biała, a obramowania fragmentów brały kolor z motywu: `--blue-dark` zmienia się w kontraście na `#ff0`, więc żółte obramowanie na bieli miało kontrast około 1,1:1. Teraz kolory w PDF są stałe (`#0052a5`, 7,8:1), a w trybie kontrastu czarne (21:1). Dotyczyło to obramowań z PR #4 i podglądu z PR #6. Test pilnuje, żeby reguły `.hl-box` nie używały kolorów motywu.

![Dlaczego ten typ?](https://github.com/TybBla/HackNation-Project/blob/etap/E9-dlaczego-typ/docs/img/gui-dlaczego-ten-typ.jpg?raw=true)

### Ręczna checklista z PR #6 (dokończona)
Sprawdzałem w przeglądarce Chromium w aplikacji, na prawdziwej klasyfikacji E3 i wzorcowej ekstrakcji z `tests/fixtures/gui`.
- [x] Podgląd przy najechaniu na **pełnomocnictwie** i **potwierdzeniu przelewu**: wszystkie 6 + 6 pól ze źródłem. Rubryka → fragment, fragment → rubryka, zejście czyści podgląd.
- [x] **Wąski ekran** (800 px): przełącznik „Pola / Dokument”; najechanie na fragment w widoku „Dokument” wyróżnia pole bez przewijania strony i bez błędów w konsoli.
- [x] **Wysoki kontrast**: rubryka z podglądem ma żółte przerywane obramowanie na czarnym tle, a fragment w PDF czarne obramowanie na bieli (po poprawce wyżej).
- [x] **Klawiatura na etykiecie fragmentu w PDF**: fokus na etykiecie wyróżnia rubrykę, a blur czyści podgląd. Sprawdziłem logikę zdarzeniem `focus`, bo okno podglądu w aplikacji nie miało fokusu systemowego. Fizycznego Tab w osobnej przeglądarce nie sprawdzałem.
- [x] „Dlaczego ten typ?” / „Dlaczego nie rozpoznano?” na 3 dokumentach z `przyklad_01` i ogłoszeniu z `data/train/negatywne`.
- [ ] Chrome i Edge poza aplikacją.

### Bramka
- `ruff`: czysto. `smoke_gui.py`: exit 0. `eval.gate --split dev --source tekst`: exit 0.
- `pytest` (lokalnie Python 3.15): exit 1 wyłącznie przez 5 testów OCR, jak na `main`. Na Pythonie 3.13 w kontenerze te testy przechodzą. Pozostałe: 721 passed.
