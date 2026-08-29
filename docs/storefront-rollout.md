# Zilo public catalog and payment rollout

The Zilo mobile product catalog is the source of truth.  There is no
WordPress or WooCommerce catalog in this flow.

## What a business uses

1. Add products in **Product Catalog** in the Zilo app.
2. Tap the new share icon in the catalog header. Zilo creates a stable link
   such as `https://zilo.pro/s/business-abc123` and opens the phone's share
   sheet. The same link appears in the web Shop dashboard.
3. The customer chooses products and options, adds them to a cart, gives their
   contact details, and is sent to the merchant's selected payment provider.
4. The provider's webhook, not the customer's return to the browser, marks the
   Zilo order **Paid**. The order confirmation screen keeps polling until that
   happens, and offers a retry link if a checkout session could not start.

## Payment behaviour

- **Kenya / Zilo Paystack:** the existing Paystack platform subaccount flow is
  used. Zilo passes the merchant subaccount to every checkout and uses
  `bearer=subaccount`, so the merchant—not Zilo—pays Paystack's processing
  fee. The configured Zilo commission remains zero.
- **Own Paystack account:** businesses outside that flow can connect their own
  Paystack secret key through Integrations. Checkout uses that account instead
  of Zilo's platform account.
- **Other existing connections:** Flutterwave, Stripe Connect, and PayHero are
  recognized automatically when they are ready. Flutterwave and Stripe use
  hosted checkout; PayHero sends the M-Pesa STK prompt to the buyer's phone.
- If more than one provider is connected, `PUT /api/storefront/settings` can
  set `payment_provider` to `paystack`, `flutterwave`, `stripe`, `payhero`,
  `manual`, or `auto`.

## Required production configuration

- `FRONTEND_URL=https://zilo.pro` on the backend. This controls catalog URLs
  and the safe payment return URL.
- `PAYSTACK_PLATFORM_SECRET_KEY` for Zilo-managed Paystack subaccounts.
- `BACKEND_URL` when PayHero is enabled, so its STK callback reaches
  `/api/webhooks/payhero`.
- Keep each provider's existing verified webhook configuration enabled. A
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
