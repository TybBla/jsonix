"""Sektor A: rozpoznanie typu dokumentu na podstawie ``classify:`` z config/doctypes/*.yaml.

Punktacja typu (szczegóły: ``features.evaluate``): frazy ``strong``/``weak``/``negative`` (obecność),
``title`` (fraza w nagłówku, rozstrzelone litery zwinięte), ``patterns`` (regex z wagą). Typ z
niespełnionym ``required_any`` odpada. Wygrywa typ o najwyższym wyniku, o ile wynik >= ``min_score``
tego typu i przewaga nad drugim typem >= ``min_margin``; inaczej dokument jest nieznany (``None``).

``confidence`` (0 dla dokumentu nieznanego, w przeciwnym razie w [0, 1]) = ``margines * nasycenie``:
``margines = (best - max(second, 0)) / best``, ``nasycenie = min(1, best / (2 * min_score))``
(``features.confidence``). ``evidence`` = opisy trafionych cech zwycięzcy (przy odrzuceniu: powód
odrzucenia i cechy najlepszego kandydata). Typ wyłącznie z treści - nazwa pliku nie jest używana.
"""

from __future__ import annotations

from odw2json.classify import features
from odw2json.config_loader import DocTypeConfig
from odw2json.contracts import Classification, Document

METHOD = "keywords"


def classify(doc: Document, registry: dict[str, DocTypeConfig]) -> Classification:
    prepared = features.Prepared(doc.text)
    if not prepared.full:
        return Classification(doc_type=None, confidence=0.0, method="empty")
    results = {k: features.evaluate(prepared, cfg.classify) for k, cfg in registry.items()}
    scores = {k: r.score for k, r in results.items()}
    candidates = [k for k, r in results.items() if r.excluded is None]
    if not candidates:
        reasons = [f"{k}: {r.excluded}" for k, r in results.items()]
        return Classification(None, 0.0, METHOD, scores, ["odrzucono: " + "; ".join(reasons)])
    best = max(candidates, key=lambda k: scores[k])
    second = max((scores[k] for k in candidates if k != best), default=0.0)
    best_cfg = registry[best].classify
    margin = scores[best] - max(second, 0.0)
    evidence = list(results[best].evidence)
    if scores[best] < best_cfg.min_score:
        why = f"odrzucono: wynik {scores[best]:g} < min_score {best_cfg.min_score:g} (najlepszy: {best})"
        return Classification(None, 0.0, METHOD, scores, [why, *evidence])
    if margin < best_cfg.min_margin:
        why = f"odrzucono: margines {margin:g} < min_margin {best_cfg.min_margin:g} (najlepszy: {best})"
        return Classification(None, 0.0, METHOD, scores, [why, *evidence])
    conf = features.confidence(scores[best], second, best_cfg.min_score)
    return Classification(best, conf, METHOD, scores, evidence)
