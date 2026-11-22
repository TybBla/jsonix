# LLM za darmo czy bez LLM: pomiar wariantu hybrydowego (reguły + LLM dla pól null)

**Status:** pomiar wykonany 22.11.2026 na dev (skany w całości, dokumenty z tekstem częściowo, patrz niżej).
Decyzja z [E6-bez-llm.md](E6-bez-llm.md) **zostaje**: oddajemy bez LLM (`config/app.yaml: llm_enabled: false`).
Holdoutu nie użyto (ani do strojenia, ani do oceny), bo pomiar na dev nie dał powodu, by LLM włączać.

## Co zmierzyliśmy
Wariant hybrydowy (`odw2json/llm_fill.py`, włączany nakładką `config/app.llm.yaml`):
1. reguły z `config/doctypes` dają wynik jak zwykle,
2. LLM dostaje **tylko pola, w których reguły dały `null`**, i tylko te, dla których w tekście jest fraza z nagłówka
   promptu (`config/prompts/<typ>.md`, sekcja `pola`),
3. model widzi **wycinek**: początek dokumentu + okna wokół trafień fraz (limit 6000 znaków; na dev średnio
   ok. 1/6 dokumentu z tekstem i 1/8 skanu),
4. odpowiedź przechodzi normalizatory i walidatory pola z YAML oraz kontrolę „jest w tekście” (data i kwota muszą
   być jedną z dat / kwot wycinka, numery jednym ciągiem cyfr, e-mail dokładnie, imiona z odmianą),
5. błąd LLM nie psuje dokumentu: zostaje wynik reguł.

Pomiar: `scripts/bench_hybryda.py` uruchamia bramkę F1 (`eval.gate`, ta sama ocena co `eval/score.py`) bez LLM
i z LLM, a każde pole uzupełnione przez model porównuje z GT: poprawne (FN → TP), błędne (FN → FP), zmyślone
(TN → FP, w GT jest `null`).

**Model:** Olala-v1.0-mini-7A1B (MoE, 7B łącznie, Apache 2.0, czyli ≤ 8B) na OVHcloud AI Endpoints (Francja),
dostęp anonimowy bez klucza, limit 2 zapytania/min na IP. Ustawienia: temperatura 0,6, `reasoning_effort: low`,
`max_tokens: 4000`, odstęp 31 s. Przy temperaturze 0 model zapętlał rozumowanie i nie dawał odpowiedzi przed
limitem tokenów (sprawdzone na przyklad_01).

## Wyniki (dev, w próbie)

WYNIKI_SKANY

**Dokumenty z tekstem (dev@tekst):** reguły F1 **0,9990** (TP 1547, TN 216, FP 3, **FN 0**). LLM byłby pytany
w 56 dokumentach o 77 pól. Przez limit 2 zapytania/min pełny przebieg to ok. 45 min, więc odpowiedzi mamy dla
7 dokumentów (przerwany przebieg): **0 uzupełnień** (model zwrócił `null` albo odpowiedzi odrzuciła kontrola),
F1 bez zmian. Kasety z odpowiedziami: `output/.cache/llm` (powtórka bez sieci: `LLM_MODE=replay`).

## Dlaczego hybryda nie ma tu czego poprawić
- Na dev reguły mają **FN = 0** zarówno na tekście, jak i na skanach. Wariant „LLM tylko dla pól null” może
  zamienić wyłącznie FN w TP. Gdy FN nie ma, każde uzupełnienie to w najlepszym razie nic, a w najgorszym
  zmyślona wartość (TN → FP). Wszystkie pozostałe błędy reguł (3 FP na tekście, 4 FP na skanach) to **złe
  wartości, nie braki**, więc hybryda ich nie dotyka.
- Koszt: dokument z tekstem to dziś ok. 0,01 s. Jedno zapytanie do Olala to 6-18 s, a przy darmowym limicie
  2 zapytania/min (OVH) lub 1/s (Mistral) narzut na same dev to ok. 40 min. Do tego sieć w dniu oceny.
- Ryzyko: kontrola „jest w tekście” odrzuca zmyślone numery, daty i e-maile, ale nazwę z nagłówka (np. adres
  KIO „Warszawa” jako miejscowość) przepuści. Bez FN do odzyskania to czysty koszt.

## Jak powtórzyć
```powershell
# .env: LLM_BASE_URL, LLM_MODEL, LLM_API_KEY (anonim = bez nagłówka Authorization, np. OVH)
$env:LLM_TEMPERATURE="0.6"; $env:LLM_EXTRA_BODY='{"reasoning_effort":"low"}'; $env:LLM_MIN_INTERVAL_S="31"
python scripts/bench_hybryda.py                      # dev: tekst i skany
python scripts/bench_hybryda.py --splits holdout     # ocena, tylko po zamrożeniu promptów
python scripts/bench_hybryda.py --dry                # bez sieci: liczba zapytań i rozmiar wycinków
```
