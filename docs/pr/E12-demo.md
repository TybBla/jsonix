## Materiały na finał: scenariusz demo, plan slajdów, pytania jury

Gałąź `etap/E12-demo` → `main`. Wyłącznie dokumentacja i zrzuty ekranu.

### Co się zmienia
- **`docs/demo.md`**:
  - przygotowanie przed pokazem: Docker albo `start-gui.bat`, zestaw 5 plików (3 typy, skan, dokument spoza typów), rozgrzanie cache OCR;
  - scenariusz w 9 krokach (~7 min) z czasem i treścią do powiedzenia, ułożony pod punkty finału: F1, transparentność, bez LLM, nowy typ bez kodu, GUI;
  - plan B (bez Dockera, bez GUI, bez sieci);
  - plan 10 slajdów;
  - przygotowane odpowiedzi na pytania jury.
- **`docs/prezentacja.html`**: gotowa prezentacja, 10 slajdów według planu. Działa offline z repo (fonty i zrzuty lokalne). Sterowanie: ← → slajdy, F pełny ekran, Ctrl+P zapis do PDF (jeden slajd na stronę). Miejsca do uzupełnienia (liczby F1, demo E10, skład zespołu) są na czerwono.
- **Zrzuty** w `docs/img/`: `gui-dodaj-pliki.jpg` (lista 4 plików) i `gui-zaznaczenie-podpis.jpg` (zaznaczone imię i nazwisko podpisującego w pełnomocnictwie, z podświetleniem w PDF).

### Do uzupełnienia przez zespół
Miejsca ⟨…⟩ w `docs/demo.md`: liczby F1 po scaleniu E4, wynik testu odporności z review E4, ewentualnie demo 4. typu (E10).

### Bramka
Zmiany tylko w dokumentacji. `ruff`: czysto. Testy GUI i `test_tooling`: zielone.
