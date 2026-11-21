# E2-T5: OCR dla stron bez warstwy tekstowej

Data: 2026-11-21. Środowisko pomiarów: Windows 11, Python 3.14.0, CPU 16 wątków, bez GPU.

## Decyzja

Silnik: **RapidOCR 3.10 (`rapidocr` + `onnxruntime`)**, model PP-OCRv6 "multi" dołączony do paczki.
Pakiety instaluje `requirements-ocr.txt`, a OCR pozostaje opcjonalny: bez pakietów `load` dodaje
ostrzeżenie `OCR niedostępny – strona N bez tekstu` i nie rzuca wyjątku. CI instaluje tylko
`requirements.txt`, więc hook jest tam nieaktywny.

## Wyniki researchu

| Pytanie | Odpowiedź |
|---|---|
| Polskie znaki (ą ę ł ś ż ź ć ń ó)? | **Tak.** Domyślny model rozpoznawania `PP-OCRv6_rec_small` ("multi") ma `pl` na liście obsługiwanych języków (`default_models.yaml`). Na 3 skanach z `data/train/negatywne/` rozpoznał wszystkie 9 polskich liter, wielkie `Ó` i `Ę` także. |
| Skąd modele? | **Dołączone do wheela** `rapidocr` (27 MB): `PP-OCRv6_det_small.onnx` (10 MB), `PP-OCRv6_rec_small.onnx` (21 MB), `ch_ppocr_mobile_v2.0_cls_mobile.onnx` (0,6 MB). **Nie ma pobierania w czasie działania**, więc laptop jury nie potrzebuje sieci. Pobierane (z modelscope.cn przy pierwszym użyciu) są dopiero modele opcjonalne, np. `latin_PP-OCRv5_rec_mobile`; nie są nam potrzebne i świadomie ich nie używamy. |
| Rozmiar instalacji | `rapidocr` 27 MB, `onnxruntime` 17 MB, `opencv-python-headless` 48 MB, `numpy` 13 MB, `shapely` 2 MB, reszta < 1 MB. Razem ok. 107 MB pobrania, instalacja w 42 s przy łączu o ok. 1 MB/s. |
| Python 3.13/3.14 na Windows | Są wheele: `onnxruntime 1.32.0` (`cp314-win_amd64`), `numpy 2.5.5`, `shapely 2.2.0`, `pyclipper 1.4.0` (`cp314`), `opencv-python-headless` (`abi3`), `rapidocr` (`py3-none-any`). Zainstalowane z `--only-binary=:all:` bez kompilacji. |
| Czas na stronę A4 (CPU) | 2,5–4,5 s na stronę (200 DPI lub 130 DPI, bez różnicy: RapidOCR i tak skaluje obraz do `max_side_len=2000`). Koszt rozpoznawania dominuje nad detekcją. Pierwsza strona dokłada ok. 1 s na ładowanie modeli. |
| Licencja | `rapidocr`: Apache-2.0; `onnxruntime`: MIT; modele PaddleOCR: Apache-2.0 (`MODEL_LICENSES.md` w paczce). Zgodne z ograniczeniem E2. |

### Jakość (skany z `negatywne/`, 7 stron)
Rozpoznany jest cały tekst główny wraz z polskimi znakami (np. „Kodeksu postępowania administracyjnego”).
Błędy dotyczą pieczątek, podpisów i stempli (`NrΛ∧/DP/2021`, `196o r.`), a także pojedynczych liter
(„Zwiazku”, „odstapion”). Do klasyfikacji „to nie jest jeden z 3 naszych typów” to wystarcza, ale wyciąganie
pól ze skanów wymagałoby weryfikacji (OCR nie daje 100% dokładności dla numerów).

## Alternatywy rozważone

| Silnik | Wniosek |
|---|---|
| `rapidocr-onnxruntime` 1.x (Apache-2.0) | Starsza linia (PP-OCRv4 ch/en w paczce), utrzymanie przeniesione do `rapidocr` 3.x. Domyślny model znaków łacińskich z polskimi diakrytykami wymaga ręcznego podmieniania modeli. Odrzucony na rzecz 3.x (nieinstalowany ani niemierzony). |
| `rapidocr` + `latin_PP-OCRv5_rec_mobile` | Też obsługuje polski, ale model jest pobierany z internetu przy pierwszym uruchomieniu: ryzyko na laptopie jury. Zbędny, bo model "multi" jest w paczce. |
| `easyocr` (Apache-2.0) | Wymaga PyTorch (setki MB) i pobiera modele w czasie działania. Odrzucony (wymóg: lekki, CPU, bez pobierania). |
| `doctr` / `onnxtr` (Apache-2.0) | Brak gotowego modelu z polskimi znakami; PyTorch/TF lub dodatkowe modele do pobrania. Odrzucony. |
| `pytesseract`, `ocrmypdf`, `tesserocr` | Wymagają binarki Tesseracta. Wykluczone przez ograniczenia E2. |
| `surya-ocr`, `marker`, `paddleocr` (pełny) | Surya jest na licencji GPL/modelach z ograniczeniami, a pełny PaddleOCR wymaga ciężkiego frameworka. Odrzucone. |

## Zachowanie w kodzie

- `odw2json/ingest/ocr.py`: `ocr_available(engine=None)`, `ocr_page(path, page_index, cfg)`, `render_page` (pypdfium2, 200 DPI, domyślnie), rejestr `OCR_ENGINES` (nowy silnik = jeden wpis z `available` i `run`), leniwe importy. Fragmenty z RapidOCR są składane w wiersze od góry do dołu i od lewej do prawej.
- `load`: OCR dotyczy tylko stron z mniej niż `min_chars_per_page` znaków (po `strip`). Rozpoznany tekst zastępuje stronę tylko wtedy, gdy jest dłuższy od istniejącego; potem normalnie działa czyszczenie. Wynik: `ocr_used=True`, `backend="<backend>+ocr:rapidocr"`, ostrzeżenie `OCR strony N`. Błąd OCR jednej strony kończy się ostrzeżeniem, nie wyjątkiem.
- Dla 196 PDF-ów zbioru OCR wywołuje się dokładnie dla 7 stron (3 pliki skanów); żadna strona z tekstem nie trafia do OCR.

## Wpływ na czas bramki (`python -m eval.gate --split all`)

| Konfiguracja | Czas |
|---|---|
| OCR wyłączony (stan wyjściowy) | 17,4 s |
| OCR włączony, zimny start | ok. 46–48 s (7 stron × ok. 3,5 s + bramka liczy `dev` i `holdout` osobno; pamięć procesu kluczowana hashem pliku liczy każdą stronę raz) |
| OCR włączony + `cache_dir`, drugie uruchomienie | 16,5 s (bez wzrostu) |

Bramka kończy się kodem 0 w każdej konfiguracji (`neg=11/13`, `klasyfikacja=2`, jak w baseline), więc skany
nadal są klasyfikowane jako nieznane. Pierwsze uruchomienie z OCR wzrasta o 7 stron OCR: tego kosztu nie da się
uniknąć bez pamięci podręcznej. Dlatego `ocr_page` ma opcjonalny `cache_dir` (wyniki w plikach
`<sha1>.<strona>.<silnik>.<dpi>.txt`). Rekomendacja dla orkiestratora: dopisać do `config/app.yaml`
w `ingest.ocr` linię `cache_dir: output/.cache/ocr` (katalog `output/*` jest w `.gitignore`); w T5 nie
zmieniamy `config/app.yaml`, bo nie ma go na liście plików zadania.

## Ryzyka i uwagi

- Pierwsze wywołanie ładuje modele (ok. 1 s) i drukuje logi RapidOCR na stderr; to nie wpływa na wynik.
- Bez GPU: ok. 3,5 s na stronę; skan 30-stronicowy to ok. 2 minuty. Przy dużych wsadach warto włączyć `cache_dir`.
- Strony prawie puste (np. kartka z numerem, < 30 znaków) w dokumencie tekstowym też przejdą przez OCR, ale ich
  tekst zostanie zastąpiony tylko wtedy, gdy OCR rozpozna więcej znaków niż było. W zbiorze treningowym takich
  stron nie ma.
