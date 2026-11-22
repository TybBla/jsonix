"""Sektor B: ekstrakcja pól wg konfiguracji typu dokumentu (sekcje ``fields``/``lists`` w YAML).

Silnik i rejestry: ``odw2json.extract.engine``. Ten moduł re-eksportuje publiczne API.
"""

from __future__ import annotations

from odw2json.extract import engine
from odw2json.extract.engine import (
    EXTRACTORS,
    NORMALIZERS,
    VALIDATORS,
    apply_derived,
    extract,
    get_path,
    register_extractor,
    register_normalizer,
    register_validator,
    set_path,
)

__all__ = [
    "EXTRACTORS",
    "NORMALIZERS",
    "VALIDATORS",
    "apply_derived",
    "engine",
    "extract",
    "get_path",
    "register_extractor",
    "register_normalizer",
    "register_validator",
    "set_path",
]
