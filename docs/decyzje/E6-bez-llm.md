# E6 — decyzja: rozwiązanie oddajemy **bez LLM**

**Status:** przyjęte 22.11.2026. Wyniki: v0.4.0 (`main` po scaleniu E4, `eval/baseline.json`); pełny raport per pole
i czas: `python scripts/quality_report.py`.

## Kryterium (roadmapa, sekcja E6)
Zostajemy bez LLM, jeśli strata F1 jest mniejsza niż wartość punktów za rozmiar modelu. Bramka etapu: F1 globalne
≥ 0,95 na dev i różnica dev–holdout ≤ 0,03.

## Fakty
- **Punktacja UZP** ([kryteria-uzp.md](../kryteria-uzp.md), pkt 3): moc modelu daje 1–20 pkt w finale. **Bez LLM =
  maksimum (20 pkt)**, ale model ≤ 8B **też** daje 20 pkt. Punkty za model nie rozstrzygają więc sprawy — decyzja
  wynika z **F1 reguł** (czy LLM ma co poprawić) i z **czasu przetwarzania** (limit czasu UZP).
- **Same reguły z konfiguracji** (bez LLM), F1 wg `eval/score.py`, v0.4.0:

| Zbiór | Dokumenty z tekstem | Skany razem | Skany: odwołanie | Skany: pełnomocnictwo | Skany: przelew |
|---|---|---|---|---|---|
| dev | **0,999** | **0,977** | 0,997 | 0,980 | 0,882 |
| holdout | **0,997** | **0,912** | 1,000 | 0,833 (3 dok.) | 0,933 |

  Klasyfikacja: 0 błędów; dokumenty spoza typów 15/15 (dev) i 13/13 (holdout). Bramka etapu jest spełniona
  z zapasem: F1 dev ≥ 0,95, różnica dev–holdout na tekście 0,002.
- **Gdzie zostaje luka:** przelewy ze skanów (dev 0,882) i pojedyncze pola pełnomocnictw na skanach z holdoutu (3 dokumenty). Przyczyną są
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
„Bez LLM z wyboru”: 20/20 pkt za rozmiar modelu, F1 z reguł 0,999 / 0,997 (dokumenty z tekstem), brak kosztów, brak wysyłania
danych poza komputer, brak zmyślania wartości (gdy dokument czegoś nie podaje, jest `null`), stały czas
przetwarzania bez limitów API.
