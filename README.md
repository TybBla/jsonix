# jsonix

> **Built at HackNation 2026 in Bydgoszcz** — a hackathon project for the UZP (Public Procurement Office) task.

jsonix reads PDF documents from a KIO appeal case (Poland's National Appeals Chamber for public procurement) and turns them into JSON in the UZP format. It recognises on its own whether a document is an appeal, a power of attorney or a payment confirmation, and extracts the fields from it. For every value it records the page and the text fragment it came from. A document of any other kind gets an empty `{}`. Scanned PDFs without a text layer are read by a local OCR engine — no GPU, and no data leaves the machine. **No LLM is used.**

![jsonix — GUI demo](docs/img/demo-gui.gif)

Version **v1.0.1** · F1 by UZP rules: **0.998** (dev) / **0.994** (holdout) · [quality report](docs/raport-jakosci.md)

## Features

- **Document classification** — appeal, power of attorney, payment confirmation; anything else maps to `{}` (28/28 out-of-scope documents handled correctly on dev and holdout).
- **Field extraction** — rule-based, driven by YAML config, output validated against the UZP JSON schema.
- **Source traceability** — each value carries its page and source text fragment; the GUI shows it in a tooltip and highlights it in the PDF.
- **Local OCR for scans** — RapidOCR (PP-OCRv6 models bundled in the wheel), CPU only, fully offline at runtime.
- **Web GUI** — upload PDFs, check the detected type with a "Why this type?" explanation, review and correct values next to the document preview, download JSON or ZIP.
- **Batch mode** — one command processes a whole `input/<case>/*.pdf` tree into `output/<case>/*.json`.
- **Config instead of code** — a new document type is a single `config/doctypes/<type>.yaml` file.

## Results

F1 computed by UZP rules on the training data (dev / holdout split):

| Split | Overall | Text documents | Scans (OCR) |
|---|---|---|---|
| dev | 0.998 | 0.999 | 0.992 |
| holdout | 0.994 | 0.997 | 0.967 |

Classification makes no errors. Per-type and per-field results and timings are in the [quality report](docs/raport-jakosci.md); regenerate it with `python scripts/quality_report.py`.

Timing (2 vCPU): a text document takes a fraction of a second, a scan about 12 s on average; 226 PDFs (30 of them scans) take 6 minutes.

## How it works

```
PDF → text layer or OCR → document type recognition → field extraction → UZP JSON (+ source of every value)
```

- **Config over code.** Each document type lives in `config/doctypes/<type>.yaml`: how to recognise it and where its fields come from. Adding a type needs configuration only ([guide](docs/nowy-typ-dokumentu.md), [example: KIO ruling](examples/nowy-typ/orzeczenie_kio/README.md)).
- **Transparency.** Every value stores its page and the text it was taken from.
- **Why no LLM.** Rules reach F1 0.999 on text documents, cost nothing, run locally and are reproducible. Rationale: [decision E6](docs/decyzje/E6-bez-llm.md). An optional LLM layer can be enabled in `config/app.yaml`, restricted to models up to 8B from an EU provider.

Full description: [docs/architektura.md](docs/architektura.md).

## Quick start

### Windows

Requires Python 3.13 or 3.14 from [python.org](https://www.python.org/downloads/) with "Add python.exe to PATH" ticked.

```powershell
.\start-gui.bat     # web app: http://127.0.0.1:8000
.\start.bat         # batch: PDFs from input\<case>\ → results in output\<case>\
```

The first run creates a virtual environment and installs dependencies (a few minutes, internet required). After that everything works offline.

### Docker (any OS)

```bash
docker compose up --build                            # web app: http://127.0.0.1:8000
docker compose run --rm app python -m odw2json run   # batch: input/ → output/
```

### Linux / macOS

```bash
pip install -r requirements.txt
sh start.sh                  # batch
python -m odw2json serve     # web app
```

### Using the web app

Upload the case PDFs and click "Analizuj" (Analyze). Check the detected type, browse the extracted data next to the document preview, hover a field to highlight it in the PDF, click the "i" icon to see its source page and fragment, correct values if needed, and download the result as JSON or ZIP. More: [docs/gui.md](docs/gui.md).

## Documentation

| Document | Contents |
|---|---|
| [docs/architektura.md](docs/architektura.md) | architecture: stages, data contracts, configuration, API and GUI |
| [docs/nowy-typ-dokumentu.md](docs/nowy-typ-dokumentu.md) | extraction config and adding a new document class |
| [docs/gui.md](docs/gui.md) | the browser application |
| [docs/raport-jakosci.md](docs/raport-jakosci.md) | quality test results |
| [docs/decyzje/E6-bez-llm.md](docs/decyzje/E6-bez-llm.md) | why no LLM |
| [docs/zgloszenie.md](docs/zgloszenie.md) | compliance with the rules, open-source components and licences |
| [docs/kryteria-uzp.md](docs/kryteria-uzp.md) | judging criteria and organiser clarifications |
| [CHANGELOG.md](CHANGELOG.md) | version history |

> Most of the documentation is written in Polish.

## For developers

```bash
pip install -r requirements-dev.txt
python -m pytest -q -m "not slow"                  # fast tests
python -m eval.gate --split dev --source tekst     # F1 quality gate (as in CI)
```

CI on GitHub Actions runs lint, tests, the F1 gate, smoke tests on Windows and Ubuntu, and `docker build`. How F1 is computed: [eval/README.md](eval/README.md). Repository working rules: [AGENTS.md](AGENTS.md).

**Stack:** Python 3.13+, FastAPI + Uvicorn, pdfplumber / pypdf / pypdfium2, RapidOCR + ONNX Runtime, Pydantic, RapidFuzz, PyYAML.

## Acknowledgements

Training data comes from the [UZP repository](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026).
