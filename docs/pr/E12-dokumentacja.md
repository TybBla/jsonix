## E12: dokumentacja wymagana do nagrody

Gałąź `etap/E12-dokumentacja` → `main`. Zmiany wyłącznie w dokumentacji, bez kodu.

### Co się zmienia
- **`docs/architektura.md`** (nowy plik). Spełnia wymóg nagrody §3.5 „opis architektury” i opisuje:
  - przepływ danych na diagramie Mermaid;
  - etapy potoku (ingest, classify, extract, zapis) z konfiguracją każdego z nich;
  - kontrakty i trace;
  - tabelę plików `config/`;
  - LLM (domyślnie wyłączony, kryteria modelu wg UZP);
  - API i GUI, jakość (F1 wg UZP, bramka, CI), uruchomienie i mapę repo.

  Ekstrakcję opisuję ogólnie i odsyłam do `nowy-typ-dokumentu.md` i `docs/decyzje/E4-ekstrakcja.md`, bo to obszar etapu E4.
- **`docs/zgloszenie.md`** (nowy plik). Checklista zgodności z regulaminem i README UZP:
  - wymagania techniczne, formularz zgłoszenia, §3.5 i §4;
  - stany ✅/🟡/⬜ z dowodami;
  - **lista komponentów open source z licencjami** do pokazania w prezentacji; wersje i licencje odczytałem z obrazu Dockera;
  - kroki przed wysłaniem.
- **README**: sekcja „Architektura” była nieaktualna, bo opisywała „LLM fallback” w klasyfikacji i „regex + LLM” w ekstrakcji. Teraz opisuje stan po E3 (domyślnie bez LLM) i linkuje do pełnego opisu.

### Zależności
- `docs/zgloszenie.md` i `docs/architektura.md` wspominają `scripts/smoke_docker.py` z PR `etap/E11-docker`, więc najlepiej scalić najpierw E11.
- Link `docs/decyzje/E4-ekstrakcja.md` zacznie działać po scaleniu E4.

### Bramka
- `ruff`: czysto.
- `eval.gate --split dev --source tekst`: exit 0.
- `pytest` (lokalnie Python 3.15): exit 1 wyłącznie przez 5 testów OCR, jak na `main`. Te same testy przechodzą na Pythonie 3.13 w kontenerze (178 passed w `test_gate`, `test_ingest_coverage`, `test_classify`, `test_ocr`).

### Do sprawdzenia przez recenzenta
- [ ] Opis klasyfikacji i ekstrakcji zgadza się z intencją autorów E3 i E4.
- [ ] Tytuł projektu i dostępność repo dla jury (pozycje ⬜ w `docs/zgloszenie.md`).
