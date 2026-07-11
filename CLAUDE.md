# SplitLeh

Mobile-first receipt splitting - two products in one monorepo.

| Product | Role | Constraints |
|---|---|---|
| **Lite** (`lite/web/`) | GitHub Pages PWA | Static only; on-device OCR; no login; images never leave the browser |
| **Cloud** (`cloud/api/` + `cloud/infra/`) | Optional Telegram group bot | User-deployed AWS; cloud OCR; see `cloud/infra/README.md` |

## Shared logic

- **TypeScript (canonical):** `lite/core/` - parse, repair, split, reconcile
- **Python (port):** `cloud/api/splitleh/` - same algorithms for Lambda; keep in sync when changing TS
- **SG receipt helpers:** `lite/core/src/sgReceipt.ts` + `cloud/api/splitleh/sg_receipt.py` - 10% service charge, 9% GST, footer detection
- **Fixtures:** `lite/core/tests/fixtures/receipts/*.txt` - shared by Vitest and pytest (`tsuta`, `sanook`, `pos_natureland`, …)
- **Receipt formats reference:** `docs/sg-receipt-formats.md` - IRAS-style F&B layouts, label variants, sample mapping

When editing parse/split logic in TS, port the same change to Python in the same PR and run `npm run test:all`.

## Lite tech stack

| Concern | Choice |
|---|---|
| Framework | React 18 + Vite 6 + TypeScript (strict) |
| OCR | PaddleOCR via `ppu-paddle-ocr` (browser, ONNX Runtime Web) |
| Persistence | localStorage via `SessionRepository` port |
| Routing | react-router-dom v6, HashRouter |
| Styles | CSS Modules + CSS custom properties |
| Deploy | GitHub Pages (`npm run deploy`) |

Do not add a backend, login, or paid APIs to Lite.

## Lite user flow

1. **Home** - new split or resume draft
2. **Scan** - photo/upload; OCR in browser
3. **Review** - edit items; set GST/service via `chargesFromParse()`
4. **Split** - people + item assignment
5. **Result** - totals; copy as plain text

## State model (`SplitSession`)

```
SplitSession
  ├── receipt
  │     ├── items[]     ReceiptItem { id, name, unitPrice, quantity, totalPrice }
  │     └── charges[]   Charge { id, type, label, amount, splitStrategy, rate? }
  ├── people[]          Person { id, name, color }
  ├── assignments[]     ItemAssignment { itemId, personIds[] }
  └── splitMode         'itemized' | 'equal'
```

Draft persists via `ReceiptContext` + localStorage. Completed sessions saved to history.

## Project structure

```
lite/
  web/                  # Lite PWA UI + adapters
  core/                 # TS parse/split logic + tests
cloud/
  api/
    splitleh_ocr/       # OCR Lambda
      cdk/              # per-service CDK - never bundled
      lambda_function.py, run.py, normalize.py, pick_parse.py, …
    splitleh_telegram/  # Telegram webhook Lambda (aiogram 3)
      cdk/
      lambda_function.py, router.py, keyboards.py, …
    shared/             # DynamoDB split store, scan budget → Lambda layer
    splitleh/           # parse/split port → Lambda layer
    tests/              # pytest
  infra/                # AWS CDK - see cloud/infra/README.md
    splitleh_cloud/
      paths.py          # repo paths, bundle constants, service discovery
      constructs/       # BaseLambda, Runtime, Storage, Api, Secrets, Budget
    scripts/bundle_lambda.py
docs/
  sg-receipt-formats.md # SG F&B receipt layouts + how OCR/parse uses them
```

Lite UI: `lite/web/src/`. Business logic: `lite/core/`, not in page components.

## Cloud / Bot (optional)

User-deployed AWS Telegram bot. Full deploy guide: `cloud/infra/README.md`. Region: `ap-southeast-1`.

### Bot commands

| Command | Action |
|---|---|
| `/scan` | Start split; reply with receipt photo |
| `/people Alice Bob` | Solo mode: create named people; tap a name, then tap items for them |
| `/status` | Who picked how many items |
| `/done` | Compute and post split (anyone in group) |
| `/cancel` | Abort active split |
| `/start`, `/help` | Usage |

### Claiming UX (group chat)

- One **shared** inline keyboard on the item-list message (Telegram limitation - not per-user keyboards).
- **Default (group):** each Telegram user taps their own items; picks stored in DynamoDB (`claimedItemIds` per user).
- **Solo / proxy:** `/people Alice Bob Charlie` creates named people; person chips on the keyboard; taps assign to the **active** person (● mark). Include yourself in the list if you ate.
- **Multiple people can pick the same item** - cost split equally in `calculate_split`.
- Button labels show aggregate picks: `#1 Guinness $13.00 ×2` = two people sharing. In proxy mode, ✓ marks show the active person's picks.
- Unclaimed items split equally among all participants who joined (`/status`, tapped **In group**, or listed via `/people`).
- **Done picking** button triggers same flow as `/done`.

### OCR pipeline (`splitleh_ocr/run.py`)

1. **Textract** `AnalyzeExpense` (primary)
2. Try several parse strategies; **pick best score** (`pick_parse.py`):
   - Structured Textract fields → items/charges
   - Line-item text → `parse_receipt`
   - Labeled summary + lines → `parse_receipt`
   - Raw Textract `LINE` blocks → `parse_receipt`
3. **Bedrock Nova** fallback if all Textract candidates score too low (optional; account must be authorized)
4. S3 receipt image deleted after OCR; split stored in DynamoDB

Do not name Lambda zip-root modules after Python stdlib (`select.py`, `socket.py`, …) - breaks boto3 on cold start. Bundle script rejects forbidden names.

### Lambda bundling

- **Layer** (`cloud/api/dist/lambda_layer/python/`): pip deps + `shared/` + `splitleh/`
- **Function** (`cloud/api/dist/lambda_code/{service}/`): flat `.py` at zip root - `lambda_function.py`, `run.py`, etc. No `cdk/`
- Handler: `lambda_function.handler`
- Bundling runs on `cdk deploy` via `app.py` → `ensure_bundled()`
- `setup_import_paths()` must run **before** importing `splitleh_ocr` / `splitleh_telegram` CDK modules

### IAC pattern

Shared constructs in `splitleh_cloud/constructs/` (`BaseLambda`, `Runtime`, `Storage`, …). Per-service CDK in `cloud/api/splitleh_*/cdk/` (timeout, memory, env, IAM). Stack imports `Ocr` and `Telegram` from service `cdk/` packages.

Handler modules use flat sibling imports in the bundle (`from run import …`) with `try/except ImportError` fallback to package imports for pytest.

Do not bundle CDK or infra code into Lambda zips.

## Responsive layout (Lite)

Mobile-first; desktop breakpoint `≥768px`. `BottomNav` → left sidebar on desktop (`--sidebar-width`). Two-column Review/Split/Result grids on desktop - see existing CSS Modules.

## Coding style

- Explicit TypeScript types; no `any`
- Components ~150 lines max; extract to utils when needed
- CSS Modules + design tokens
- Minimal comments; no over-abstraction

## Local development

```bash
npm install
npm run dev          # Lite at http://localhost:5173
npm run test:all     # Vitest + pytest
```

Bot setup and redeploy: `cloud/infra/README.md`.

```bash
cd cloud/infra
cdk deploy SplitlehStack-dev -c env=dev --profile splitleh
# First deploy only: -c bot_token=YOUR_TOKEN
```

## GitHub Pages

`lite/web/vite.config.ts` → `base: '/splitleh/'`. Repo: `MarcusCJH/splitleh`.
