# Zilo public catalog and payment rollout

The Zilo mobile product catalog is the source of truth.  There is no
WordPress or WooCommerce catalog in this flow.

## What a business uses

1. Add products in **Product Catalog** in the Zilo app.
2. Tap the new share icon in the catalog header. Zilo creates a stable link
   such as `https://zilo.pro/s/business-abc123` and opens the phone's share
   sheet. The same link appears in the web Shop dashboard.
3. The customer chooses products and options, adds them to a cart, gives their
   contact details, and is sent to secure Paystack checkout.
4. Paystack's webhook, not the customer's return to the browser, marks the
   Zilo order **Paid**. The order confirmation screen keeps polling until that
   happens, and offers a retry link if a checkout session could not start.

## Payment behaviour

- **Kenya / Zilo Paystack:** businesses select a Kenyan bank account or M-Pesa
  payout provider. Zilo creates a Paystack subaccount in KES and passes it to
  each checkout using `bearer=subaccount`. The merchant pays Paystack's
  processing fee and Zilo's commission is zero.
- **Nigeria and other supported Paystack countries:** businesses connect their
  own Paystack account with its `sk_test_` or `sk_live_` secret key. Their
  payments and settlement then stay in that Paystack account; no Zilo
  subaccount is created.
- **Storefront checkout:** uses Paystack only for now. PayHero is deliberately
  not offered in this flow because it requires the merchant to maintain a
  PayHero balance. It can be reconsidered as a separate future integration.
- `PUT /api/storefront/settings` accepts `payment_provider` as `paystack`,
  `manual`, or `auto`. The live storefront automatically chooses Paystack when
  it is connected.

## Required production configuration

- `FRONTEND_URL=https://zilo.pro` on the backend. This controls catalog URLs
  and the safe payment return URL.
- `PAYSTACK_PLATFORM_SECRET_KEY` for Zilo-managed Paystack subaccounts.
- The business's Zilo catalog currency must match the Paystack connection:
  **KES** for the Zilo-managed Kenya flow, or the merchant-selected currency
  for an own Paystack account. Zilo rejects a checkout if they do not match,
  rather than charging the wrong currency.
- Keep Paystack's verified webhook configuration enabled. A
  payment return URL alone must never be treated as proof of payment.

## Test checklist before advertising

1. In the mobile app, add one in-stock product and tap Share Catalog.
2. Open the link in an incognito browser; confirm the product, price and stock
   match the app.
3. Add it to the cart and use a **Paystack test account** to complete checkout.
4. Confirm the webhook changes the order to Paid in Zilo and no duplicate order
   is created if the payment-status page is refreshed.
5. Cancel once, then use the retry button; make sure the original order and
   stock reservation are reused.
6. Only after the test above passes, make a small live payment on Zilo's
   Paystack account and confirm the merchant payout destination in Paystack.
