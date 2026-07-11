# SplitLeh Bot - AWS setup guide

Deploy your own Telegram group bot: DynamoDB, S3, API Gateway webhook, and Python Lambdas (OCR + split logic).

**Region:** `ap-southeast-1` (Singapore)

---

## Prerequisites

| Requirement | Notes |
|---|---|
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Python package manager |
| Python 3.12 | See `.python-version` at repo root |
| [AWS CLI](https://aws.amazon.com/cli/) | `aws sts get-caller-identity` must work |
| Telegram bot token | From [@BotFather](https://t.me/BotFather) - **never commit this** |
| AWS account | You deploy into **your** account; costs ~$4–7/mo at moderate use; OCR capped at ~$10/month |

### AWS services (one-time, in `ap-southeast-1`)

- **Amazon Textract** - primary receipt OCR (`AnalyzeExpense`)
- **Amazon Bedrock** (optional) - Nova Lite fallback when Textract confidence is low; auto-enabled on first invoke when your account is authorized

Optional budget alert email:

```bash
-c alert_email=you@example.com
```

---

## 1. Create the Telegram bot

1. Open [@BotFather](https://t.me/BotFather) → `/newbot`
2. Choose display name and username (must end in `bot`)
3. Copy the **HTTP API token**

### Group chat settings

When adding the bot to a dinner group, pick one:

- **Recommended:** BotFather → `/mybots` → your bot → **Bot Settings** → **Group Privacy** → **Turn off** (bot sees all messages), or
- Keep privacy on and **@mention** the bot when sending receipt photos

---

## 2. Install dependencies

From the **repo root**:

```bash
uv sync --all-packages --group dev
npm install   # optional, for Lite / core tests
```

---

## 3. Deploy with CDK

### Service layout (one folder per Lambda)

```
cloud/api/
  splitleh_ocr/
    cdk/                  ← service CDK (timeout, memory, env, IAM)
    lambda_function.py
    run.py, textract_provider.py, ...
  splitleh_telegram/
    cdk/
    lambda_function.py
    router.py, ...
  shared/                 ← bundled into lambda_layer
  splitleh/
  dist/                   ← build output (gitignored)
```

**Infra layout** (`cloud/infra/splitleh_cloud/`):

| Module | Role |
|---|---|
| `paths.py` | Repo paths, bundle constants, `lambda_services()`, `setup_import_paths()` |
| `lambda_runtime.py` | CDK Python 3.12 + ARM64 |
| `arns.py` | Cross-Lambda ARN helpers |
| `constructs/_lambda.py` | `BaseLambda` - shared Function wiring |
| `constructs/runtime.py` | Shared layer + base env vars |
| `constructs/storage.py`, `api.py`, `secrets.py`, `budget.py` | Shared stack building blocks |
| `splitleh_stack.py` | Composes stack; imports `Ocr` / `Telegram` from each service's `cdk/` |

Per-service CDK lives in `cloud/api/splitleh_*/cdk/` so each Lambda can diverge (timeout, memory, extra env vars, IAM) without touching shared infra.

First time only - bootstrap CDK in your account/region:

```bash
cd cloud/infra
cdk bootstrap aws://YOUR_ACCOUNT_ID/ap-southeast-1 --profile splitleh
```

Deploy:

```bash
cdk deploy SplitlehStack-dev -c env=dev --profile splitleh
```

**First deploy only** - pass both secrets once (stored in SSM Parameter Store; later deploys omit them):

```bash
# Generate a webhook secret (one-time)
python -c "import secrets; print(secrets.token_urlsafe(24))"

cdk deploy SplitlehStack-dev -c env=dev -c bot_token=YOUR_TOKEN -c webhook_secret=YOUR_WEBHOOK_SECRET --profile splitleh
```

### Bot token vs webhook secret

| | Bot token | Webhook secret |
|---|---|---|
| **Source** | [@BotFather](https://t.me/BotFather) | Generate once with `secrets.token_urlsafe(24)` |
| **Purpose** | Lambda calls Telegram API | Verify incoming webhook requests |
| **Stored** | `/splitleh/telegram/bot_token_dev` (SSM) | `/splitleh/telegram/webhook_secret_dev` (SSM) |
| **On every deploy?** | No - only `-c bot_token=` on first deploy | No - only `-c webhook_secret=` on first deploy |

They are unrelated - do not use the bot token as the webhook secret.

Fetch webhook secret for `setWebhook` (one time after deploy):

```bash
aws ssm get-parameter --name /splitleh/telegram/webhook_secret_dev --query Parameter.Value --output text --profile splitleh
```

The **CDK CLI** is a Node tool (`npm install -g aws-cdk`). Use `cdk` directly - not `uv run cdk`. CDK invokes the app via `uv run python app.py` (see `cdk.json`), which bundles Lambda code first.

Deps install (~30s) is skipped when `requirements.txt` has not changed. App code is refreshed on every deploy.

Optional manual bundle (debug only):

```bash
npm run bundle:lambda
```

Approve IAM changes when prompted.

### Stack already exists / logical ID conflicts

If CDK fails with **"Resource 'splitleh_ocr' already exists"** after a major infra refactor, CloudFormation logical IDs changed while `function_name` stayed the same. For **dev**, destroy then redeploy:

```bash
cd cloud/infra
cdk destroy SplitlehStack-dev -c env=dev --profile splitleh
cdk deploy SplitlehStack-dev -c env=dev -c bot_token=YOUR_TOKEN -c webhook_secret=YOUR_SECRET --profile splitleh
```

Save both values before destroy if you want to reuse them. Re-run `setWebhook` if the API Gateway URL changes.

### CDK outputs to save

| Output | Use |
|---|---|
| `WebhookUrl` | Telegram webhook URL (ends with `/telegram/webhook`) |
| `WebhookSecretParamName` | SSM parameter name - fetch value once for `setWebhook` |
| `SessionsTableName` | DynamoDB table |
| `ReceiptsBucketName` | Temp receipt uploads |

If you deployed with a placeholder token, update **SSM Parameter Store** → `/splitleh/telegram/bot_token_dev` with the real token, then wait for the next Lambda cold start.

---

## 4. Register the webhook

Replace `<TOKEN>`, `<WebhookUrl>`, and `<WebhookSecret>` (from SSM - see deploy section):

```bash
WEBHOOK_SECRET=$(aws ssm get-parameter --name /splitleh/telegram/webhook_secret_dev --query Parameter.Value --output text --profile splitleh)

curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"<WebhookUrl>\", \"secret_token\": \"$WEBHOOK_SECRET\"}"
```

Verify:

```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

Expect `"url": "<WebhookUrl>"` and no persistent error.

**Re-run `setWebhook` only when** the API Gateway URL changes (new stack / destroy+recreate).

---

## 5. Smoke test

1. Add the bot to a **test group**
2. `/start` - help text with privacy note
3. `/scan` - then send a receipt **photo**
4. Wait for numbered items + inline buttons
5. Each person taps their items (use `/status` to see who picked)
6. `/done` or tap **Done picking** - per-person totals appear

### Bot commands

| Command | Action |
|---|---|
| `/start`, `/help` | Help |
| `/scan` | Start split; send photo next |
| `/status` | Who has picked items |
| `/done` | Calculate and post totals |
| `/cancel` | Abort (scanner only) |

---

## 6. Run tests locally

```bash
# From repo root
npm run test:all

# Bot backend only
uv run --directory cloud/api pytest tests -q
```

---

## CI/CD (optional)

### What GitHub Actions already does

- **CI** ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)): on PR/push (not `master`) - Lite build + all tests
- **Lite CD** ([`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml)): on push to `master` - GitHub Pages

**Bot deploy is not automated** - you run `cdk deploy` locally. That is intentional for v1.

### Adding bot CD later (GitHub → AWS)

If you want a “Deploy bot” button in GitHub Actions:

1. **AWS:** Create OIDC identity provider for `token.actions.githubusercontent.com`
2. **AWS:** IAM role trusting your repo (e.g. `MarcusCJH/splitleh`, branch `master`)
3. **GitHub:** Repository secrets:
   - `AWS_ROLE_ARN` - the IAM role ARN
   - `TELEGRAM_BOT_TOKEN` - BotFather token (for `-c bot_token=...`)
   - Optional: `ALERT_EMAIL`
4. Add workflow (e.g. `deploy-bot.yml`) with `workflow_dispatch` (manual) or `push` to `master`

Reference: [GitHub OIDC with AWS](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)

**Webhook:** Usually still a one-time manual `setWebhook` after first deploy unless you automate that step too.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Bot silent after photo | CloudWatch → `splitleh_telegram`, `splitleh_ocr` log groups |
| `401` on webhook | `WebhookSecret` must match `X-Telegram-Bot-Api-Secret-Token`; re-run `setWebhook` |
| OCR fails | CloudWatch → `splitleh_ocr`; Textract needs S3 object present; Bedrock fallback is optional |
| Bot ignores group photos | Turn off Group Privacy or `@mention` the bot |
| Monthly scan limit message | `$10 cap` hit - use [Lite](https://marcuscjh.github.io/splitleh/) or reset `SYSTEM#billing` row in DynamoDB (dev only) |
| `cdk deploy` fails on bundle | Ensure `uv` works from repo root; run `npm run bundle:lambda` to see the error |
| `Resource 'splitleh_ocr' already exists` | Destroy stack then redeploy (see deploy section) |

---

## Redeploy after code changes

```bash
cd cloud/infra
cdk deploy SplitlehStack-dev -c env=dev --profile splitleh
```

Bundling runs automatically. Webhook URL usually stays the same - no need to call `setWebhook` again unless the stack was recreated.
