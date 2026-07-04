# SplitSia

A mobile-first PWA for scanning receipts, splitting costs, and sharing results with friends. Fully static — no backend, no login, no server.

## Features

- Photograph or upload a receipt; the image never leaves your device
- In-browser OCR via PaddleOCR extracts items and prices automatically
- Edit any extracted item before splitting (OCR isn't perfect)
- Add people by name and assign items to one or more of them
- GST/service charge splits proportionally to each person's subtotal
- Per-person itemised breakdown you can copy as plain text to share
- Draft auto-saves to localStorage; completed sessions appear on the home screen
- Adaptive layout: mobile bottom nav + two-column desktop views at ≥768px

## User Flow

1. **Home** — start a new split or resume a saved draft
2. **Scan** — upload or photograph a receipt (stays on device)
3. **Review** — edit item names and prices; add or remove items; set tax and tip
4. **Split** — add people; assign items to one or more people
5. **Result** — view per-person totals; copy breakdown to share

## Tech Stack

| Concern | Choice |
|---|---|
| Framework | React 18 |
| Build tool | Vite 6 |
| Language | TypeScript (strict) |
| OCR | PaddleOCR (in-browser via ONNX Runtime Web) |
| Persistence | localStorage |
| Routing | react-router-dom v6, HashRouter |
| Styles | CSS Modules + CSS custom properties |
| Deployment | GitHub Pages |

## Getting Started

```bash
npm install
npm run dev       # http://localhost:5173
npm run build     # production build → dist/
npm run preview   # preview the production build locally
npm test          # run unit tests
```

## Deployment

```bash
npm run deploy    # builds and pushes dist/ to gh-pages branch
```

The app is deployed at: https://marcuscjh.github.io/splitsia/

`vite.config.ts` sets `base: '/splitsia/'`. HashRouter avoids 404s on GitHub Pages without a custom `404.html`.

## Project Structure

```
src/
  types/          # Shared TypeScript types
  store/          # React Context + useReducer (ReceiptContext)
  utils/          # Pure business logic: parsing, splitting, storage, OCR
  components/     # Reusable UI: AppShell, BottomNav
  pages/          # One folder per route: Home, Scan, Review, Split, Result
```

## Contributing

Contributions are welcome. To get started:

1. Fork the repo and create a branch from `master`
2. Run `npm install` and `npm run dev` to confirm everything works
3. Make your changes — keep components under ~150 lines and put business logic in `src/utils/`
4. Run `npm test` to make sure existing tests pass; add tests for new logic in `src/utils/__tests__/`
5. Open a pull request with a clear description of what you changed and why

A few things to keep in mind:

- No backend, login, or paid APIs — the app must remain fully static
- Receipt images must never leave the user's device
- Mobile-first: every UI change should look good on a small screen first; the desktop breakpoint is `≥768px` — see the Responsive Layout section in `CLAUDE.md`
- Avoid introducing new major dependencies without discussing it in the PR first

## Privacy

Receipt images are processed entirely in the browser using on-device ML models. No image data, receipt content, or personal information is sent to any server.
