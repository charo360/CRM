# Sam CRM — Backend API

Python **FastAPI** service for the Sam CRM product. It exposes REST APIs under `/api`, powers the web app, and integrates messaging, AI assistants, marketing automation, and business operations. The main entry point is `server.py` (`app`).

## What this backend does

- **CRM core** — contacts, conversations, teams, permissions, notifications, and related CRM flows (large surface area in `server.py`).
- **Channels** — WhatsApp (Twilio and related services), email sync, Telegram, Bird, and other channel helpers.
- **AI assistant** — multi-agent orchestration, tools, Composio integrations, document generation (`assistant/`).
- **Autoreply** — journey-style automated replies (`autoreply/`).
- **Workflows** — event triggers, deferred jobs, Shopify autopilot (`workflows/`).
- **Marketing & growth** — campaigns and growth endpoints (`marketing/`, `growth_routes.py`).
- **Content & SEO** — blog generation/scheduling (`blog/`), SEO tools and SEO agent (`seo/`, `seo_agent/`).
- **Commerce & ops** — inventory, invoices, quotes, finance, loyalty, forms, feedback, collaboration, Zernio, Shotstack, and more (routers mounted from `server.py`).
- **Background work** — Redis-backed job worker for broadcasts and receipts (`worker.py`); schedulers started with the API process where configured.

Data is stored in **MongoDB** (Motor async driver). **Redis** is used for queues and caching when running the worker or features that depend on it.

## Repository layout (high level)

| Path | Role |
|------|------|
| `server.py` | FastAPI app, `/api` router, most HTTP routes |
| `models.py` | Shared Pydantic / data models |
| `assistant/` | AI assistant routes, agents, tools |
| `agents/` | Specialized chat agents (sales, booking, payments, etc.) |
| `autoreply/` | Autoreply engine and models |
| `workflows/` | Workflow engine and API |
| `blog/`, `seo/`, `seo_agent/` | Blogging and SEO features |
| `memory/` | Conversation memory system |
| `rag/` | Retrieval indexing/search |
| `paystack_*.py` | Paystack connect, checkout initialize, webhooks, ledger |
| `flutterwave_*.py` | Flutterwave subaccounts, checkout, webhooks, ledger |
| `payhero_*.py` | PayHero M-Pesa STK, webhooks, usage ledger |
| `worker.py` | Redis queue consumer (separate process) |
| `requirements.txt` | Python dependencies (target **Python 3.11**) |
| `scripts/pip-install-resilient.sh` | Retry-friendly `pip install` for slow networks |
| `Dockerfile` | Production-style image (Python 3.11 + Playwright Chromium) |
| `ENVIRONMENT_SETUP.md` | API keys and env var notes |
| `AUTOBLOG_SETUP_GUIDE.md` | WordPress autoblog setup |

## Prerequisites

- **Python 3.11** (recommended; matches `Dockerfile` and `.venv` layout)
- **MongoDB** — connection string in env (e.g. `MONGO_URL`)
- **Redis** — required if you run `worker.py` or use queue-backed features
- A filled-in **`backend/.env`** (see [Configuration](#configuration))

Use the project virtualenv, not system Python 3.12+ / 3.14. System `uvicorn` often points at a different interpreter without project packages (`ModuleNotFoundError: No module named 'dotenv'`).

## Setup

From the repo root:

```bash
cd backend
```

### 1. Create or fix the virtual environment

If you do not have `.venv` yet:

```bash
python3.11 -m venv .venv
```

Ensure `python` / `python3` inside `.venv/bin` point at **3.11** (not system 3.14):

```bash
ls -l .venv/bin/python3   # should resolve to python3.11
.venv/bin/python3 --version # expect Python 3.11.x
```

### 2. Install dependencies

```bash
scripts/pip-install-resilient.sh
```

Or manually:

```bash
.venv/bin/python3 -m pip install --upgrade pip
.venv/bin/python3 -m pip install -r requirements.txt
```

Install logs are appended to `pip-install.log` when using the resilient script.

### 3. Configuration

Environment loading (see `server.py`):

1. **`backend/.env`** — loaded first (`override=True` for process env).
2. **`backend/.env.local`** — optional; only **non-empty** values override `.env` (blank lines do not wipe existing keys).

Copy or maintain secrets in `backend/.env`. Do not commit real credentials.

Common variables (not exhaustive — see `ENVIRONMENT_SETUP.md`):

| Variable | Purpose |
|----------|---------|
| `MONGO_URL` | MongoDB URI |
| `JWT_SECRET` | Auth token signing |
| `OPENAI_API_KEY` / OpenRouter keys | LLM providers (per feature) |
| `TWILIO_*` | WhatsApp / SMS where used |
| Redis URL vars | As defined in `redis_client.py` / `.env` |

For OpenAI key behavior and troubleshooting, see **`ENVIRONMENT_SETUP.md`**.

### Paystack (merchant payments)

Each business connects their own **secret key** (`sk_test_…` / `sk_live_…`) in the web app (**Integrations → Paystack**). The backend stores it on the user document and calls [Paystack’s API](https://paystack.com/docs/api/) server-side.

| Item | Value |
|------|--------|
| Webhook URL (set in [Paystack Dashboard → Settings → API & Webhooks](https://dashboard.paystack.com/#/settings/developer)) | `{BACKEND_URL}/api/webhooks/paystack` |
| Checkout callback (optional) | `{FRONTEND_URL}/dashboard/orders?paystack=success` |
| Collections | `paystack_payment_intents`, `paystack_transactions` |

`BACKEND_URL` and `FRONTEND_URL` must be reachable from Paystack and the customer’s browser (use ngrok or your public API host in development).

### Flutterwave (platform subaccounts)

Platform-managed only: set **`FLUTTERWAVE_PLATFORM_SECRET_KEY`** (`FLWSECK_TEST-…` / `FLWSECK-…`) and **`FLUTTERWAVE_SECRET_HASH`** (dashboard webhook hash). Merchants connect in **Integrations → Flutterwave** (bank + settlement details); the server creates a Flutterwave subaccount and stores `flutterwave_subaccount_id` on the user document.

| Item | Value |
|------|--------|
| Webhook URL | `{BACKEND_URL}/api/webhooks/flutterwave` |
| Redirect after pay | `{FRONTEND_URL}/dashboard/orders?flutterwave=success` |
| Merchant split % | `FLUTTERWAVE_MERCHANT_SPLIT_PERCENT` (default `90` = 90% to merchant; API sends `0.9`) |
| Collections | `flutterwave_payment_intents`, `flutterwave_transactions` |

### Stripe Connect (platform destination charges)

Set **`STRIPE_PLATFORM_SECRET_KEY`** (`sk_test_…` / `sk_live_…`). Merchants onboard via **Integrations → Stripe** (Express Connect account link). Checkout uses **destination charges** with an application fee; configure **`STRIPE_MERCHANT_TRANSFER_PERCENT`** (default `90` = 90% to the connected account before Stripe fees).

Before any merchant can connect, the **platform** Stripe account must finish [Connect platform profile](https://dashboard.stripe.com/settings/connect/platform-profile) (including who manages losses on connected accounts). If this is skipped, account creation returns an error about “managing losses for connected accounts”.

Merchant **country** must be one where Stripe allows the `card_payments` capability on Express connected accounts (see [global availability](https://stripe.com/global)). **Kenya, Nigeria, and Ghana** are not in that list for this integration — use Paystack or PayHero instead.

| Item | Value |
|------|--------|
| Webhook (your account — onboarding + destination checkout) | `{BACKEND_URL}/api/webhooks/stripe` |
| Webhook (connected accounts — optional, direct charges) | `{BACKEND_URL}/api/webhooks/stripe/connect` |
| Signing secrets | `STRIPE_WEBHOOK_SECRET` or `STRIPE_WEBHOOK_SECRET_PLATFORM`; optional `STRIPE_WEBHOOK_SECRET_CONNECT` |
| After onboarding | `{FRONTEND_URL}/dashboard/integrations?stripe=return` |
| Order success redirect | `{FRONTEND_URL}/dashboard/orders?stripe=success` |
| Collections | `stripe_payment_intents`, `stripe_transactions` |

## Running locally

Always run from **`backend/`** using the venv.

### API server (development)

```bash
cd backend
source .venv/bin/activate
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

Without activating:

```bash
cd backend
.venv/bin/uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

- App title: **WhatsApp CRM** (OpenAPI: `http://127.0.0.1:8000/docs`)
- Health: `GET /health` and `GET /api/health`

Point the **web** app at this URL (e.g. `NEXT_PUBLIC_API_URL` or your project’s equivalent in `web/`).

### Background worker (optional)

Separate terminal, same venv and env:

```bash
cd backend
source .venv/bin/activate
python worker.py
```

Processes Redis queues such as broadcast and receipt jobs (see `worker.py` header).

### Production-style (Docker)

```bash
cd backend
docker build -t sam-crm-backend .
docker run --env-file .env -p 8000:8000 sam-crm-backend
```

Railway-style deploy uses `railway.toml` (`uvicorn` with `$PORT`, health check `/api/health`).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `No module named 'dotenv'` | Use `.venv/bin/uvicorn` or `source .venv/bin/activate`; avoid `/usr/bin/uvicorn` on Python 3.14 |
| Wrong Python version in venv | Recreate venv with `python3.11 -m venv .venv` or fix symlinks under `.venv/bin` |
| MongoDB / DNS errors on import | Check `MONGO_URL` and network; Atlas SRV needs working DNS |
| AI replies are generic fallbacks | Verify API keys in `backend/.env`; see `ENVIRONMENT_SETUP.md` |

Verify the interpreter:

```bash
which python uvicorn
python --version
```

Both should live under `backend/.venv/bin` and report **3.11.x**.

## Related docs

- [`ENVIRONMENT_SETUP.md`](./ENVIRONMENT_SETUP.md) — API keys and required env vars
- [`AUTOBLOG_SETUP_GUIDE.md`](./AUTOBLOG_SETUP_GUIDE.md) — WordPress multisite autoblog
- [`memory/README_MEMORY_SYSTEM.md`](./memory/README_MEMORY_SYSTEM.md) — Memory system design
- [`assistant/README_STRUCTURED_CHOICES.md`](./assistant/README_STRUCTURED_CHOICES.md) — Assistant UI choices
