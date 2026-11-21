# Biblioteki dołączone lokalnie (GUI działa offline, bez CDN)

| Katalog | Źródło | Wersja | Licencja |
|---|---|---|---|
| `pdfjs/` | [pdfjs-dist](https://www.npmjs.com/package/pdfjs-dist) (Mozilla PDF.js): `legacy/build/pdf.min.mjs`, `legacy/build/pdf.worker.min.mjs`, fragment `web/pdf_viewer.css` z regułami warstwy tekstowej (`text_layer.css`) | 4.10.38 | Apache-2.0 (`pdfjs/LICENSE`) |
| `fonts/` | [@fontsource/open-sans](https://www.npmjs.com/package/@fontsource/open-sans): woff2 400/600/700, podzbiory latin i latin-ext (polskie znaki) | 5.3.0 | SIL OFL 1.1 (`fonts/LICENSE`) |

Pliki skopiowano bez zmian (poza wycięciem fragmentu CSS warstwy tekstowej i własnym `fonts/open-sans.css` z regułami `@font-face`).
