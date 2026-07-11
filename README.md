# SplitLeh

A mobile-first PWA for scanning receipts, splitting costs, and sharing results with friends. Optional **Telegram group bot** for cloud OCR and tap-to-claim splitting.

| Product | What it is | Hosting |
|---|---|---|
| **Lite** | On-device OCR, no login, fully private | [GitHub Pages](https://marcuscjh.github.io/splitleh/) |
| **Bot** (optional) | Telegram group bot - cloud OCR, inline item picking | Your AWS account (`ap-southeast-1`) |

## User flow

### Lite (PWA)

1. **Home** - start a new split or resume a draft
2. **Scan** - photograph or upload a receipt (stays on device)
3. **Review** - edit item names and prices; set tax and service charge
4. **Split** - add people; assign items in the UI
5. **Result** - per-person totals; copy breakdown to share

### Bot (Telegram group)

1. `/scan` → send receipt photo
2. Bot posts numbered items with inline buttons
3. **Group:** everyone taps their own items (same dish → both tap → `×2`)
4. **Solo:** `/people Alice Bob Charlie` → tap a name chip → tap their dishes (include yourself if you ate)
5. `/status` to see picks; **Done picking** or `/done` to calculate
6. `/cancel` to abort

**Shared items:** If two people order the same dish, both get it assigned (group: both tap; solo: assign under each name). Buttons show `×2`.

## Tech stack

### Lite (GitHub Pages PWA)

| Concern | Choice |
|---|---|
| Framework | React 18 |
| Build | Vite 6 |
| Language | TypeScript (strict) |
| OCR | PaddleOCR via `ppu-paddle-ocr` (in-browser, ONNX Runtime Web) |
| Persistence | localStorage |
| Routing | react-router-dom v6, HashRouter |
| Styles | CSS Modules + CSS custom properties |
| Deploy | GitHub Pages (`npm run deploy`) |

### Cloud / Bot (optional)

| Concern | Choice |
|---|---|
| Interface | Telegram Bot API ([aiogram](https://docs.aiogram.dev/) 3) |
| Compute | AWS Lambda (Python 3.12, ARM64) - handler `lambda_function.handler` |
| IaC | AWS CDK (Python) - shared constructs + per-service `cdk/` folders |
| API | API Gateway HTTP API (webhook) |
| Storage | DynamoDB (splits/claims), S3 (temp receipt images, deleted after OCR) |
| OCR | **Textract AnalyzeExpense** (primary) → multi-strategy parse → **Bedrock Nova** fallback |
| Region | `ap-southeast-1` |

### Shared logic

| Concern | Choice |
|---|---|
| Parse / split (canonical) | `lite/core` (TypeScript) |
| Parse / split (bot port) | `cloud/api/splitleh/` (Python) |
| SG receipt heuristics | `sgReceipt.ts` / `sg_receipt.py` (service charge, GST, POS footer patterns) |
| Receipt fixtures | `lite/core/tests/fixtures/receipts/` (Natureland, Tsuta, Sanook, …) |
| Format reference | [docs/sg-receipt-formats.md](docs/sg-receipt-formats.md) |
| Monorepo | npm workspaces (`lite/*`) + uv workspace (`cloud/*`) |

## Features

**Lite**

- Receipt images never leave the device
- In-browser OCR; easy correction before splitting
- GST / service charge split proportionally by subtotal
- Draft auto-save; mobile-first layout with desktop breakpoint at ≥768px

**Bot**

- Deploy your own instance (not a shared hosted bot)
- Group receipt scan → numbered items with inline buttons
- **Shared dishes** - multiple people can claim the same item; `×N` on buttons
- Unclaimed items split equally among participants
- Fair split with per-person totals posted to the chat
- Images uploaded to S3 for OCR, then deleted

## Getting started

### Lite

```bash
npm install
npm run dev          # http://localhost:5173
npm run build
npm run test:all     # core (TS) + api (Python) tests
```

### Bot

See **[cloud/infra/README.md](cloud/infra/README.md)** for the full setup guide (BotFather, AWS, CDK, webhook, troubleshooting).

```bash
cd cloud/infra
cdk deploy SplitlehStack-dev -c env=dev --profile splitleh
# First deploy only: add -c bot_token=YOUR_TOKEN
```

Do not commit your bot token.

## Deployment

| Target | Command | When |
|---|---|---|
| Lite (GitHub Pages) | `npm run deploy` | Manual, or auto on push to `master` |
| Bot (AWS) | `cdk deploy` (see cloud/infra README) | Manual from your machine |

## Project structure

```
SplitSia/
├── lite/
│   ├── web/               # GitHub Pages PWA
│   └── core/              # Parse/split logic + tests (TypeScript)
├── cloud/
│   ├── api/
│   │   ├── splitleh_ocr/      # OCR Lambda (Textract + Bedrock fallback)
│   │   ├── splitleh_telegram/ # Telegram webhook (aiogram)
│   │   ├── shared/            # DynamoDB store, scan budget
│   │   ├── splitleh/          # parse/split Python port
│   │   └── tests/             # pytest
│   └── infra/             # AWS CDK → see cloud/infra/README.md
├── docs/
│   └── sg-receipt-formats.md  # SG F&B receipt layout reference
└── .github/workflows/     # CI + Lite CD
```

Per-service CDK lives in `cloud/api/splitleh_*/cdk/` (timeout, memory, IAM). Shared infra in `cloud/infra/splitleh_cloud/`.

## CI / CD

| Workflow | Trigger | What |
|---|---|---|
| [ci.yml](.github/workflows/ci.yml) | PR + push (not `master`) | Lite build, `npm test`, `pytest cloud/api/tests` |
| [deploy.yml](.github/workflows/deploy.yml) | Push to `master` | Tests + deploy Lite to GitHub Pages |

Bot AWS deploy is **manual** in v1. Optional GitHub OIDC bot CD is documented in [cloud/infra/README.md#cicd-optional](cloud/infra/README.md#cicd-optional).

## Contributing

1. Fork, branch from `master`, run `npm install`
2. `npm run test:all` must pass before opening a PR
3. **Lite** stays static - no backend in `lite/web/`; receipt images must not leave the device
4. Bot changes need tests under `cloud/api/tests/`
5. **Parse/split logic:** edit `lite/core/` first, port to `cloud/api/splitleh/` in the same PR; add receipt fixtures under `lite/core/tests/fixtures/receipts/` for new SG POS layouts
6. Avoid new major dependencies without discussing in the PR
7. Do not name Lambda handler modules after Python stdlib modules (e.g. `select.py`)

## Privacy

- **Lite:** OCR and images stay in the browser; nothing is sent to a server.
- **Bot:** Receipt photos go to your S3 bucket for OCR, then are deleted. Claims and parsed items live in your DynamoDB table.
