"""jsonix — klasyfikacja i ekstrakcja danych z dokumentów spraw KIO."""

import os

# Przed pierwszym importem numpy: OpenBLAS z domyślną liczbą wątków (= liczba rdzeni logicznych) rezerwuje
# przy imporcie ok. 490 MB na 16 wątkach (zmierzone; z 1 wątkiem ok. 10 MB), a przy braku pamięci przerywa
# cały interpreter ("OpenBLAS error: Memory allocation still failed"). Obliczenia OCR liczy onnxruntime,
# numpy służy tylko do konwersji obrazów. Wartość ustawioną przez użytkownika zostawiamy.
# Decyzja: docs/decyzje/E2b-ocr-wydajnosc.md, „Stabilność pod obciążeniem”.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

__version__ = "0.1.0"
