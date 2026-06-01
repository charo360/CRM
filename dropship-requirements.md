# Dropship & Market Intelligence — Requirements

## What we're building
1. **CJdropshipping integration** — search real supplier products, import to Shopify, store cost price for margin tracking
2. **AliExpress integration** — additional supplier catalog via Alibaba affiliate API
3. **Market trend intelligence** — Google Trends + CJ hot products to show what's selling in a category across the market (not just your own store)

---

## API Keys / Accounts Needed

### 1. CJdropshipping (Priority: HIGH)
- **What for:** Product search, hot products (trending), import to Shopify, cost price storage
- **How to get:** Register free at https://cjdropshipping.com → Developer → API
- **Endpoints we'll use:**
  - `POST /v1/authentication/getAccessToken` — auth
  - `POST /v1/product/query` — search products by keyword/category
  - `GET /v1/product/hotProductList` — trending/hot products
  - `GET /v1/product/{pid}` — product detail with cost price, images, variants
  - `GET /v1/logistic/freightCalculate` — shipping cost estimate
- **Env var:** `CJ_API_KEY` + `CJ_API_EMAIL` (or `CJ_ACCESS_TOKEN`)

### 2. AliExpress / Alibaba Affiliate API (Priority: MEDIUM)
- **What for:** Secondary supplier catalog, broader product range
- **How to get:** https://portals.aliexpress.com → apply for affiliate/API access (takes 1-3 days approval)
- **Endpoints we'll use:**
  - `aliexpress.affiliate.product.query` — search products
  - `aliexpress.affiliate.hotproduct.query` — trending products
- **Note:** Requires approved affiliate account, not instant
- **Env var:** `ALIEXPRESS_APP_KEY` + `ALIEXPRESS_APP_SECRET`

### 3. Google Trends (Priority: HIGH — no API key needed)
- **What for:** Show rising/falling search interest for any product category
- **How to get:** Uses `pytrends` Python library — no key, no account
- **Install:** `pip install pytrends`
- **What we'll show:** Interest over time, related rising queries, regional interest

---

## What gets built (in order)

| Step | What | Branch |
|------|------|--------|
| 1 | `search_cj_products` tool + `get_cj_hot_products` tool | `dropship` |
| 2 | `get_market_trends` tool (Google Trends via pytrends) | `dropship` |
| 3 | `import_cj_product_to_shopify` tool (creates Shopify product + stores CJ cost price in DB) | `dropship` |
| 4 | `shopify_product_analytics` tool (revenue, units sold, margin using stored cost) | `dropship` |
| 5 | Shopify Products tab UI — add "Source from CJ" tab alongside AI finder | `dropship` |
| 6 | Zilo Chat integration — wire new tools into shopify_products agent | `dropship` |
| 7 | AliExpress integration (after CJ is live and tested) | `dropship` |

---

## DB schema additions needed

```
cj_products collection:
{
  user_id: string,
  shopify_product_id: string,       // Shopify product ID after import
  cj_pid: string,                   // CJ product ID
  cost_price: number,               // CJ cost price (for margin calc)
  supplier: "cj" | "aliexpress",
  imported_at: datetime
}
```

---

## Environment variables checklist

```env
# CJdropshipping
CJ_API_EMAIL=your@email.com
CJ_API_KEY=your_cj_api_key

# AliExpress (when ready)
ALIEXPRESS_APP_KEY=
ALIEXPRESS_APP_SECRET=

# Shopify Partner API — required for "create a Shopify store from chat"
# SHOPIFY_PARTNER_ID     — numeric org ID from partners.shopify.com → Settings
# SHOPIFY_PARTNER_ACCESS_TOKEN — generate at partners.shopify.com → Settings → Partner API clients → Create access token
#   Required scopes: "Manage stores" (developmentStoreV2Create mutation)
SHOPIFY_PARTNER_ID=
SHOPIFY_PARTNER_ACCESS_TOKEN=
```

---

## Start signal
When `CJ_API_KEY` is in `.env.local`, we start with Step 1.
AliExpress can be added later — CJ alone gives us 90% of the value.
