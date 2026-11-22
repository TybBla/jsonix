---
# Pola, które LLM może uzupełnić, gdy reguły dały null (wariant hybrydowy, odw2json/llm_fill.py).
# Format jak w prompts/odwolanie.md.
pola:
  mocodawca[].data.imie_nazwisko:
    opis: 'Imię i nazwisko mocodawcy (udzielającego pełnomocnictwa), tylko gdy jest osobą fizyczną; przy firmie null.'
    szukaj: ['re:mocodaw\w*', 're:nizej\s+podpisan\w*', 're:udzielam\w*']
  mocodawca[].data.krs:
    opis: 'Numer KRS mocodawcy (10 cyfr).'
    szukaj: ['re:krs']
  mocodawca[].data.nazwa:
    opis: 'Pełna nazwa mocodawcy (firmy udzielającej pełnomocnictwa).'
    szukaj: ['re:mocodaw\w*', 're:udziela\w*', 're:\bsp\.\s*z', 're:\bs\.\s?a\.']
  mocodawca[].data.nip:
    opis: 'NIP mocodawcy.'
    szukaj: ['re:nip']
  mocodawca[].data.typ:
    opis: 'Typ mocodawcy: dokładnie "osoba_prawna" (spółka, firma, instytucja) albo "osoba_fizyczna".'
    szukaj: []
    wartosci: [osoba_prawna, osoba_fizyczna]
  mocodawca[].podpisujacy[].imie_nazwisko:
    opis: 'Imię i nazwisko osoby podpisującej pełnomocnictwo w imieniu mocodawcy (np. prezes zarządu, prokurent), mianownik.'
    szukaj: ['re:podpis\w*', 're:prezes\w*', 're:czlon\w*\s+zarzadu', 're:prokurent\w*', 're:w\s+imieniu']
  pelnomocnicy[].imie_nazwisko:
    opis: 'Imię i nazwisko osoby, która otrzymuje pełnomocnictwo (pełnomocnika), mianownik, bez tytułu.'
    szukaj: ['re:upowazni\w*', 're:pelnomocni\w*', 're:\badw\.', 're:\bradc\w*', 're:adwokat\w*']
  pelnomocnicy[].pesel:
    opis: 'PESEL pełnomocnika (11 cyfr), tylko jeśli podany.'
    szukaj: ['re:pesel']
---
Dokument to pełnomocnictwo do reprezentowania wykonawcy w postępowaniu przed Krajową Izbą Odwoławczą. Mocodawca udziela pełnomocnictwa; pełnomocnicy je otrzymują; podpisujący podpisują dokument w imieniu mocodawcy. Nie myl pełnomocnika z osobą podpisującą.
