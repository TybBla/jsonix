# Jak dodać nowy typ dokumentu (bez zmian w kodzie)

1. Szablon wyniku: `config/schemas/<typ>.json` — dokładny kształt JSON, wszystkie wartości `null`.
2. Opis typu: `config/doctypes/<typ>.yaml`:
   ```yaml
   id: <typ>
   title: Czytelna nazwa
   output_template: schemas/<typ>.json
   classify:
     strong: ["fraza charakterystyczna", ...]   # +2 pkt (porównanie bez polskich znaków, małe litery)
     weak: [...]                                # +1 pkt
     negative: [...]                            # -3 pkt
     min_score: 3.0
   fields: {}        # reguły pól (format ustala sektor B)
   llm:
     prompt: prompts/<typ>.md
   ```
3. (opcjonalnie) prompt `config/prompts/<typ>.md`, słowniki `config/lookups/*.yaml`.
4. Sprawdź: `python -m odw2json doctypes` — nowy typ jest na liście; `python -m odw2json run`.

Kod (`odw2json/`) ładuje wszystkie typy z `config/doctypes/` automatycznie.
