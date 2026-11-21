# GUI (sektor C) — React + Vite + TypeScript

Do zrobienia przez sektor C. Założenia:
- `npm create vite@latest . -- --template react-ts`, dev-proxy `/api` → `http://127.0.0.1:8000`.
- `npm run build` → `web/dist/` **commitujemy** (tester nie ma Node); FastAPI serwuje `web/dist` pod `/`.
- Widok: upload PDF-ów → lista (typ + pewność) → **PDF (react-pdf) | JSON** obok siebie, klik w pole → podświetlenie `source_snippet` z trace, pobranie JSON.
- Dodatkowo: podgląd/edycja `config/doctypes/*.yaml` (demo „nowy typ bez kodu”).
