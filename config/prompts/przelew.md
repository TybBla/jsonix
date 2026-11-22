---
# Pola, które LLM może uzupełnić, gdy reguły dały null (wariant hybrydowy, odw2json/llm_fill.py).
# Format jak w prompts/odwolanie.md. Frazy wzorowane na etykietach z config/doctypes/przelew.yaml.
pola:
  przelew_bankowy.data_operacji:
    opis: 'Data wykonania (operacji, księgowania) przelewu, RRRR-MM-DD.'
    szukaj: ['re:data\w*', 're:\bdni[au]\b']
  przelew_bankowy.kwota:
    opis: 'Kwota przelewu jako liczba (np. 10000.00).'
    szukaj: ['kwota', 're:\bpln\b', 're:\bzl\b']
  przelew_bankowy.z_rachunku:
    opis: 'Numer rachunku nadawcy (z którego wysłano przelew), same cyfry.'
    szukaj: ['re:z\s+rachunku', 're:nadawc\w*', 're:zleceniodawc\w*', 're:platnik\w*', 're:rachun\w*']
  przelew_bankowy.na_rachunek:
    opis: 'Numer rachunku odbiorcy (na który wysłano przelew), same cyfry.'
    szukaj: ['re:na\s+rachunek', 're:odbiorc\w*', 're:beneficjent\w*', 're:adresat\w*', 're:kontrahent\w*', 're:rachun\w*']
  przelew_bankowy.numer_transakcji:
    opis: 'Numer (identyfikator, referencja) transakcji nadany przez bank, przepisany dokładnie.'
    szukaj: ['re:transakcj\w*', 're:identyfikator\w*', 're:referency\w*', 're:referencj\w*', 're:\bnr\.?\s*ref']
  przelew_bankowy.tytul:
    opis: 'Tytuł przelewu w pełnym brzmieniu.'
    szukaj: ['re:tytul\w*', 're:\bopis\b', 'szczegoly platnosci', 'cel platnosci', 're:\btresc\b']
---
Dokument to potwierdzenie przelewu bankowego (zwykle wpis od odwołania na rachunek Urzędu Zamówień Publicznych). Nadawca to wykonawca, odbiorca to zwykle Urząd Zamówień Publicznych.
