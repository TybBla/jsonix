"""Sektor A: rozpoznanie typu dokumentu na podstawie config/doctypes/*.yaml.

Wersja bazowa: punktacja słów kluczowych (strong=+2, weak=+1, negative=-3, liczona obecność).
TODO(A): wagi pozycji (nagłówek), LLM fallback przy niskiej pewności, kalibracja na negatywach.
"""

from __future__ import annotations

from odw2json.config_loader import DocTypeConfig
from odw2json.contracts import Classification, Document
from odw2json.textnorm import fold

W_STRONG, W_WEAK, W_NEG = 2.0, 1.0, -3.0


def score(text_folded: str, cfg: DocTypeConfig) -> float:
    c = cfg.classify
    s = sum(W_STRONG for k in c.strong if fold(k) in text_folded)
    s += sum(W_WEAK for k in c.weak if fold(k) in text_folded)
    s += sum(W_NEG for k in c.negative if fold(k) in text_folded)
    return s


def classify(doc: Document, registry: dict[str, DocTypeConfig]) -> Classification:
    t = fold(doc.text)
    if not t:
        return Classification(doc_type=None, confidence=0.0, method="empty")
    scores = {k: score(t, cfg) for k, cfg in registry.items()}
    best = max(scores, key=scores.get)
    ok = scores[best] >= registry[best].classify.min_score
    top = sorted(scores.values(), reverse=True)
    margin = top[0] - (top[1] if len(top) > 1 else 0.0)
    conf = 0.0 if not ok else min(1.0, margin / max(top[0], 1e-9))
    return Classification(doc_type=best if ok else None, confidence=conf, method="keywords", scores=scores)
