# E6 — decyzja: rozwiązanie oddajemy **bez LLM**

**Status:** przyjęte 22.11.2026. Wyniki: pomiar 21.11.2026 na gałęzi E4 (ekstrakcja); po scaleniu E4 liczby trzeba
potwierdzić raportem `python scripts/quality_report.py`.

## Kryterium (roadmapa, sekcja E6)
Zostajemy bez LLM, jeśli strata F1 jest mniejsza niż wartość punktów za rozmiar modelu. Bramka etapu: F1 globalne
≥ 0,95 na dev i różnica dev–holdout ≤ 0,03.

## Fakty
- **Punktacja UZP** ([kryteria-uzp.md](../kryteria-uzp.md), pkt 3): moc modelu daje 1–20 pkt w finale. **Bez LLM =
  maksimum (20 pkt)**, tyle samo co model ≤ 8B. LLM nie może więc dodać punktów w tej kategorii, może je tylko
  odebrać, jeśli model będzie większy.
- **Same reguły z konfiguracji** (bez LLM), F1 wg `eval/score.py`; Docker, Python 3.13, OCR, zimny cache:

| Zbiór | Tekst | Skany |
|---|---|---|
| dev | **99,9%** (162 dok.) | **97,5%** (29 dok.) |
| holdout | **99,7%** (62 dok.) | **90,3%** (13 dok.) |

  Klasyfikacja: 0 błędów, dokumenty spoza typów 12/12 (dev) i 10/10 (holdout). Bramka etapu jest spełniona
  z zapasem: F1 dev ≥ 0,95, różnica dev–holdout na tekście 0,002.
- **Gdzie zostaje luka:** pojedyncze pola na skanach z holdoutu (np. nazwa mocodawcy, tytuł przelewu). Przyczyną są
  błędy OCR (zamienione litery, przestawione kolumny), a nie brak „rozumienia” tekstu. LLM dostałby ten sam
  błędny tekst z OCR, więc nie naprawi literówki w nazwie firmy ani w numerze.
- **Czas** (UZP ogranicza czas na rozwiązanie, kryteria pkt 5a): dziś 99% czasu to OCR skanów, a dokument
  z tekstem zajmuje 0,01 s ([E11-wydajnosc.md](E11-wydajnosc.md)). Każde zapytanie do LLM to sekundy, do tego
  limity API (rate limit) i ponowienia, które zjadają ten sam budżet czasu.
- **Wymogi formalne LLM:** model open source, dostawca z serwerami w UE/EOG i polityką prywatności określającą
  zakres i miejsce przetwarzania, klucz API dostarczony organizatorowi. Bez LLM nie ma żadnego z tych ryzyk ani
  zależności od sieci w dniu oceny.

## Decyzja
- W konfiguracji oddawanej UZP: `config/app.yaml: llm_enabled: false` (stan obecny). README i
  [architektura.md](../architektura.md) opisują rozwiązanie jako „bez LLM”.
- **Pomiaru „reguły + LLM” nie robimy przed zgłoszeniem.** Reguły spełniają bramkę etapu, a LLM nie może dodać
  punktów za moc modelu. Ewentualny zysk F1 ograniczałby się do kilku pól na skanach, kosztem czasu i ryzyka.
- Warstwa LLM zostaje w kodzie jako **opcja** (`odw2json/llm.py`, `config/llm.yaml`, kasety w testach): klient
  zgodny z OpenAI, temperatura 0, `.env` opcjonalny. Gdyby ktoś ją włączył, obowiązują wymogi UZP: wyłącznie
  model ≤ 8B (np. Ministral 8B/3B od Mistral AI z endpointem w UE), z cytatem polityki prywatności dostawcy
  w tym katalogu.

## Do prezentacji
„Bez LLM z wyboru”: 20/20 pkt za rozmiar modelu, F1 z reguł ⟨99,9% / 99,7% po E4⟩, brak kosztów, brak wysyłania
danych poza komputer, brak zmyślania wartości (gdy dokument czegoś nie podaje, jest `null`), stały czas
przetwarzania bez limitów API.
