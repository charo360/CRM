# Zilo public catalog and checkout plan

## Recommendation

Build a **Zilo Storefront** from the existing Zilo product catalog, rather than
creating a second product database or depending on the unofficial WhatsApp
catalogue protocol.

Each merchant receives a public, mobile-first shop such as:

```text
https://zilo.pro/s/home-serve
https://zilo.pro/s/home-serve/p/modern-lamp-abc123
```

The merchant shares the shop or a specific product in WhatsApp. A customer can
view items, add them to a cart, enter delivery details, and either pay online or
place a WhatsApp/cash-on-delivery order. This works with WAHA because it is a
normal web link; it does not need WhatsApp's official Commerce API.

## What is already in Zilo

- The mobile and web dashboards already use the `products` collection with
  photos, stock, variants, modifiers, pricing tiers and currencies.
- The backend already has orders, order payments, receipts and WhatsApp
  notifications.
- Merchant payment infrastructure already supports Paystack, Stripe,
  Flutterwave and PayHero, including hosted payment links and verified webhooks.
- `web/app/dashboard/shop/page.tsx` already advertises a public
  `/shop/{business_slug}` link, but there is no matching public route yet. This
  is the gap to complete.
- The current WordPress/WooCommerce generator is **out of scope**. It duplicates
  catalog, product and payment behaviour that Zilo should own directly, so it
  should be retired rather than extended.

## First release: catalogue and orders

1. Add a public route in the existing Next.js web app:
   `web/app/s/[storeSlug]/page.tsx` and a public product page.
2. Add a merchant-controlled **Show in my online catalogue** switch on each
   product. Products are private until the merchant opts in.
3. Public API endpoints return only live, in-stock products for that merchant.
   They never expose dashboard data, phone numbers or private order history.
4. Give the customer a cart, quantity selector, variants/modifiers, delivery
   notes and contact form.
5. Create an order with a price snapshot and `payment_status: pending`.
6. Let merchants choose **Order on WhatsApp / cash / bank transfer** first.
   Zilo sends the merchant an immediate WhatsApp notification and sends the
   customer an acknowledgement.
7. Generate Open Graph title, price and product image so a shared link has a
   useful WhatsApp preview.

This first release is valuable even before online payments: a merchant shares
one link and receives trackable orders inside Zilo.

## Second release: hosted online payment

The checkout page collects the customer email and phone number, creates the
order on the Zilo server, then requests a hosted checkout URL from the
merchant's selected payment provider. The customer is redirected to the
provider's page, not a card form built by Zilo.

- Kenya / KES: make Flutterwave or PayHero the first supported choice. The
  existing Flutterwave integration can create a hosted checkout and Flutterwave
  documents M-PESA and cards for KES.
- International merchants: use the existing Stripe Connect path where the
  merchant's country is supported.
- Nigeria and relevant African markets: retain Paystack / Flutterwave as
  available choices according to the merchant's verified country and currency.
- A provider webhook, verified by its signature, is the source of truth. It
  marks the saved order paid and triggers the existing receipt and WhatsApp
  confirmation. Redirect pages are never treated as payment proof.

Do not make one Zilo Stripe account collect every merchant's sales. Each
merchant connects their own account (or a managed provider account) so payouts,
refunds and compliance are correct.

## Safeguards required before launch

- Server-side price, stock and variant validation; never trust the cart total
  from the browser.
- Rate limit public checkout and add bot protection once traffic begins.
- Keep product availability and public visibility separate from the merchant's
  private catalog.
- Use opaque order IDs/references and verify provider webhook signatures,
  currency, amount and merchant before marking an order paid.
- Capture consent for order updates on WhatsApp and provide a privacy link.
- Add inventory reservation only after a payment/order expiry policy is agreed.

## Delivery sequence

1. Build the public catalogue and share links.
2. Test a cash/WhatsApp order end-to-end with one business.
3. Enable Flutterwave or PayHero checkout for that business and test payment
   webhooks in sandbox.
4. Add merchant onboarding, analytics, promo codes and abandoned-cart follow-up.
5. Retire the WordPress/WooCommerce generator and remove its web navigation,
   provisioning and promotion only after a focused dependency audit. No new
   feature should be built on it.

## Product decision

This is a good paid feature. It removes the biggest friction for small
businesses: they can turn their existing WhatsApp catalogue into a real shop
without building a separate website. Start it as a paid plan feature or a
small per-transaction fee only after the basic catalog/order flow is proven.

## References

- [Stripe Checkout](https://docs.stripe.com/payments/checkout) supports a
  hosted checkout page and Checkout Sessions.
- [Stripe Payment Links](https://docs.stripe.com/payment-links) shows the
  simpler shareable-link pattern.
- [Flutterwave payment methods](https://developer.flutterwave.com/v3.0.0/docs/payment-methods)
  lists KES card and M-PESA support.
- [Flutterwave M-PESA](https://developer.flutterwave.com/v3.0/docs/m-pesa)
  describes customer authorisation and the payment webhook flow.
