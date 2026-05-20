/**
 * Unified Shopify API proxy.
 * All reads are GET /api/shopify?action=...
 * All writes are POST /api/shopify { action, ...payload }
 *
 * Uses Composio-backed HTTP on the FastAPI backend (not Nango).
 */
import { NextRequest, NextResponse } from "next/server";
import { resolveUserId } from "@/lib/nango-proxy";
import { buildServerCrmApiUrl } from "@/lib/server-crm-api";

const SHOPIFY_API = "2024-01";
const TOOLKIT = "shopify";

// ── Helpers ───────────────────────────────────────────────────────────────────

function err(msg: string, status = 400) {
  return NextResponse.json({ error: msg }, { status });
}

async function shopifyConnected(req: NextRequest, auth: string | null): Promise<boolean> {
  if (!auth?.startsWith("Bearer ")) return false;
  const url = buildServerCrmApiUrl(req, "/composio/connections");
  const res = await fetch(url, { headers: { Authorization: auth } });
  if (!res.ok) return false;
  const d = (await res.json().catch(() => ({}))) as { connected?: Record<string, boolean> };
  return !!d.connected?.[TOOLKIT];
}

async function composioShopify(
  req: NextRequest,
  auth: string | null,
  method: string,
  path: string,
  params?: Record<string, string>,
  body?: unknown,
): Promise<unknown> {
  const url = buildServerCrmApiUrl(req, "/composio/http");
  const res = await fetch(url, {
    method: "POST",
    headers: { Authorization: auth ?? "", "Content-Type": "application/json" },
    body: JSON.stringify({ toolkit: TOOLKIT, method, path, params, json: body }),
  });
  const text = await res.text();
  let data: unknown;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    const detail =
      typeof data === "object" && data !== null && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : text;
    throw new Error(detail || `Shopify ${path} → ${res.status}`);
  }
  return data;
}

async function shopifyGet(
  req: NextRequest,
  auth: string | null,
  path: string,
  params?: Record<string, string>,
) {
  return composioShopify(req, auth, "GET", path, params) as Promise<Record<string, unknown>>;
}

async function shopifyPost(req: NextRequest, auth: string | null, path: string, body: unknown) {
  return composioShopify(req, auth, "POST", path, undefined, body) as Promise<Record<string, unknown>>;
}

async function shopifyDelete(req: NextRequest, auth: string | null, path: string) {
  await composioShopify(req, auth, "DELETE", path);
}

async function shopifyPut(req: NextRequest, auth: string | null, path: string, body: unknown) {
  return composioShopify(req, auth, "PUT", path, undefined, body) as Promise<Record<string, unknown>>;
}

// ── GET handler ───────────────────────────────────────────────────────────────

export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization");
  if (!(await resolveUserId(auth))) return err("Unauthorized", 401);
  const connected = await shopifyConnected(req, auth);
  if (!connected) {
    return NextResponse.json({ connected: false });
  }

  const sp  = req.nextUrl.searchParams;
  const action = sp.get("action") ?? "";
  const limit  = Math.min(parseInt(sp.get("limit") ?? "50"), 250);

  try {
    // ── Orders ──────────────────────────────────────────────────────────────
    if (action === "orders") {
      const status = sp.get("status") ?? "any";          // any | open | closed | cancelled
      const financialStatus = sp.get("financial_status"); // paid | pending | refunded ...
      const fulfillmentStatus = sp.get("fulfillment_status"); // fulfilled | unfulfilled | partial
      const search = sp.get("search") ?? "";

      const params: Record<string, string> = {
        limit: String(limit),
        status,
        fields: "id,order_number,name,email,created_at,updated_at,financial_status,fulfillment_status,total_price,subtotal_price,total_discounts,currency,customer,line_items,shipping_address,note,tags,refunds,fulfillments",
      };
      if (financialStatus) params.financial_status = financialStatus;
      if (fulfillmentStatus) params.fulfillment_status = fulfillmentStatus;

      const data = await shopifyGet(req, auth, `/admin/api/${SHOPIFY_API}/orders.json`, params) as { orders: ShopifyOrder[] };
      let orders = data.orders ?? [];
      if (search) {
        const q = search.toLowerCase();
        orders = orders.filter((o) =>
          String(o.order_number).includes(q) ||
          o.email?.toLowerCase().includes(q) ||
          `${o.customer?.first_name} ${o.customer?.last_name}`.toLowerCase().includes(q)
        );
      }
      return NextResponse.json({ orders, connected: true });
    }

    // ── Single order ─────────────────────────────────────────────────────────
    if (action === "order") {
      const id = sp.get("id");
      if (!id) return err("id required");
      const data = await shopifyGet(req, auth, `/admin/api/${SHOPIFY_API}/orders/${id}.json`) as { order: ShopifyOrder };
      return NextResponse.json({ order: data.order });
    }

    // ── Products ─────────────────────────────────────────────────────────────
    if (action === "products") {
      const productStatus = sp.get("status") ?? "active";
      const data = await shopifyGet(req, auth, `/admin/api/${SHOPIFY_API}/products.json`, {
        limit: String(limit),
        status: productStatus,
        fields: "id,title,handle,product_type,status,variants,image,images",
      }) as { products: ShopifyProduct[] };
      return NextResponse.json({ products: data.products ?? [], connected: true });
    }

    // ── Customers ────────────────────────────────────────────────────────────
    if (action === "customers") {
      const data = await shopifyGet(req, auth, `/admin/api/${SHOPIFY_API}/customers.json`, {
        limit: String(limit),
        fields: "id,first_name,last_name,email,phone,orders_count,total_spent,created_at,updated_at,last_order_name,tags,accepts_marketing,default_address",
      }) as { customers: ShopifyCustomer[] };
      // Sort by total_spent desc
      const customers = (data.customers ?? []).sort(
        (a, b) => parseFloat(b.total_spent ?? "0") - parseFloat(a.total_spent ?? "0")
      );
      return NextResponse.json({ customers, connected: true });
    }

    // ── Abandoned carts ──────────────────────────────────────────────────────
    if (action === "abandoned") {
      const data = await shopifyGet(req, auth, `/admin/api/${SHOPIFY_API}/checkouts.json`, {
        limit: String(limit),
        fields: "id,token,email,created_at,updated_at,total_price,subtotal_price,currency,line_items,abandoned_checkout_url",
      }) as { checkouts: ShopifyCheckout[] };
      // Only include non-empty carts with an email
      const carts = (data.checkouts ?? []).filter(
        (c) => c.email && parseFloat(c.total_price ?? "0") > 0
      );
      return NextResponse.json({ carts, connected: true });
    }

    // ── Discounts ────────────────────────────────────────────────────────────
    if (action === "discounts") {
      const data = await shopifyGet(req, auth, `/admin/api/${SHOPIFY_API}/price_rules.json`, {
        limit: String(limit),
        fields: "id,title,value_type,value,customer_selection,starts_at,ends_at,usage_limit,times_used,created_at",
      }) as { price_rules: ShopifyPriceRule[] };
      const rules = data.price_rules ?? [];

      // Fetch codes for each rule (up to 20 rules to avoid rate limits)
      const enriched = await Promise.all(
        rules.slice(0, 20).map(async (rule) => {
          try {
            const codeData = await shopifyGet(req, auth, `/admin/api/${SHOPIFY_API}/price_rules/${rule.id}/discount_codes.json`, { limit: "5" }) as { discount_codes: { code: string; usage_count: number }[] };
            return { ...rule, codes: codeData.discount_codes ?? [] };
          } catch {
            return { ...rule, codes: [] };
          }
        })
      );
      return NextResponse.json({ discounts: enriched, connected: true });
    }

    // ── Locations ────────────────────────────────────────────────────────────
    if (action === "locations") {
      const data = await shopifyGet(req, auth, `/admin/api/${SHOPIFY_API}/locations.json`) as { locations: ShopifyLocation[] };
      return NextResponse.json({ locations: data.locations ?? [] });
    }

    // ── Overview stats ───────────────────────────────────────────────────────
    if (action === "overview") {
      const period = sp.get("period") ?? "month"; // today | week | month
      const now = new Date();
      let createdAtMin: string;
      if (period === "today") {
        createdAtMin = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();
      } else if (period === "week") {
        createdAtMin = new Date(now.getTime() - 7 * 86400000).toISOString();
      } else {
        createdAtMin = new Date(now.getFullYear(), now.getMonth(), 1).toISOString();
      }

      const [ordersData, productsData, customersData] = await Promise.all([
        shopifyGet(req, auth, `/admin/api/${SHOPIFY_API}/orders.json`, {
          limit: "250",
          status: "any",
          created_at_min: createdAtMin,
          fields: "id,order_number,name,financial_status,fulfillment_status,total_price,created_at,customer,line_items,refunds",
        }),
        shopifyGet(req, auth, `/admin/api/${SHOPIFY_API}/products/count.json`, { status: "active" }),
        shopifyGet(req, auth, `/admin/api/${SHOPIFY_API}/customers/count.json`),
      ]) as [{ orders: ShopifyOrder[] }, { count: number }, { count: number }];

      const orders = ordersData.orders ?? [];
      const revenue = orders
        .filter((o) => o.financial_status !== "refunded" && o.financial_status !== "voided")
        .reduce((sum, o) => sum + parseFloat(o.total_price ?? "0"), 0);
      const refunds = orders.filter((o) => o.financial_status === "refunded" || (o.refunds ?? []).length > 0).length;
      const fulfilled = orders.filter((o) => o.fulfillment_status === "fulfilled").length;
      const unfulfilled = orders.filter((o) => !o.fulfillment_status).length;
      const pending = orders.filter((o) => o.financial_status === "pending").length;
      const aov = orders.length ? revenue / orders.length : 0;

      // Revenue by day (last 14 days or period)
      const dayMap = new Map<string, number>();
      for (const o of orders) {
        if (o.financial_status === "refunded" || o.financial_status === "voided") continue;
        const day = o.created_at.slice(0, 10);
        dayMap.set(day, (dayMap.get(day) ?? 0) + parseFloat(o.total_price ?? "0"));
      }
      const revenueByDay = [...dayMap.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([date, amount]) => ({ date, amount }));

      // Top products by revenue
      const productMap = new Map<string, { title: string; revenue: number; units: number }>();
      for (const o of orders) {
        for (const li of o.line_items ?? []) {
          const key = String(li.product_id ?? li.title);
          const existing = productMap.get(key) ?? { title: li.title, revenue: 0, units: 0 };
          existing.revenue += parseFloat(li.price) * li.quantity;
          existing.units += li.quantity;
          productMap.set(key, existing);
        }
      }
      const topProducts = [...productMap.values()]
        .sort((a, b) => b.revenue - a.revenue)
        .slice(0, 5);

      return NextResponse.json({
        connected: true,
        period,
        stats: {
          revenue, orderCount: orders.length, aov,
          fulfilled, unfulfilled, pending, refunds,
          productCount: productsData.count ?? 0,
          customerCount: customersData.count ?? 0,
          fulfillmentRate: orders.length ? Math.round((fulfilled / orders.length) * 100) : 0,
        },
        revenueByDay,
        topProducts,
        recentOrders: orders.slice(0, 10),
      });
    }

    // ── Growth intelligence ──────────────────────────────────────────────────
    if (action === "growth") {
      // Pull 90 days of orders + full customer list in parallel
      const since90 = new Date(Date.now() - 90 * 86400000).toISOString();
      const since30  = new Date(Date.now() - 30 * 86400000).toISOString();

      const [ordersData, customersData] = await Promise.all([
        shopifyGet(req, auth, `/admin/api/${SHOPIFY_API}/orders.json`, {
          limit: "250",
          status: "any",
          created_at_min: since90,
          financial_status: "paid",
          fields: "id,customer,total_price,created_at,line_items",
        }),
        shopifyGet(req, auth, `/admin/api/${SHOPIFY_API}/customers.json`, {
          limit: "250",
          fields: "id,orders_count,total_spent,created_at,updated_at,accepts_marketing",
        }),
      ]) as [{ orders: ShopifyOrder[] }, { customers: ShopifyCustomer[] }];

      const orders     = ordersData.orders     ?? [];
      const customers  = customersData.customers ?? [];

      // ── Repeat purchase rate ─────────────────────────────────────────────
      const repeatCustomers  = customers.filter((c) => c.orders_count >= 2).length;
      const repeatRate       = customers.length ? Math.round((repeatCustomers / customers.length) * 100) : 0;

      // ── New vs returning in last 30 days ─────────────────────────────────
      const recentOrders = orders.filter((o) => o.created_at >= since30);
      let newCust = 0, returningCust = 0;
      for (const o of recentOrders) {
        const cust = customers.find((c) => c.id === o.customer?.id);
        if (!cust || cust.orders_count <= 1) newCust++;
        else returningCust++;
      }

      // ── Revenue at risk (at-risk customers × AOV) ────────────────────────
      const atRiskCustomers = customers.filter((c) => {
        const days = (Date.now() - new Date(c.updated_at).getTime()) / 86400000;
        return days > 90 && c.orders_count > 1;
      });
      const allRevenue = customers.reduce((s, c) => s + parseFloat(c.total_spent ?? "0"), 0);
      const aov        = customers.length && orders.length
        ? orders.reduce((s, o) => s + parseFloat(o.total_price ?? "0"), 0) / orders.length
        : 0;
      const revenueAtRisk = atRiskCustomers.length * aov;

      // ── Avg days to second purchase (cohort) ─────────────────────────────
      // We approximate: customers with 2+ orders / total purchase frequency
      const avgOrderGap = repeatCustomers > 0
        ? Math.round(90 / (orders.length / Math.max(repeatCustomers, 1)))
        : null;

      // ── Revenue by channel (from order tags, best-effort) ────────────────
      const channelMap = new Map<string, number>();
      for (const o of orders) {
        const tags = (o as unknown as { tags?: string })?.tags ?? "";
        const channel = tags.includes("facebook") || tags.includes("meta") ? "Meta Ads"
          : tags.includes("google") ? "Google Ads"
          : tags.includes("email") ? "Email"
          : tags.includes("whatsapp") || tags.includes("wa") ? "WhatsApp"
          : tags.includes("organic") ? "Organic"
          : "Direct / Other";
        channelMap.set(channel, (channelMap.get(channel) ?? 0) + parseFloat(o.total_price ?? "0"));
      }
      const channelRevenue = [...channelMap.entries()]
        .sort(([, a], [, b]) => b - a)
        .map(([channel, revenue]) => ({ channel, revenue }));

      // ── LTV ──────────────────────────────────────────────────────────────
      const avgLtv = customers.length ? allRevenue / customers.length : 0;

      // ── Marketing subscribers ────────────────────────────────────────────
      const subscribers = customers.filter((c) => c.accepts_marketing).length;
      const subscriberRate = customers.length ? Math.round((subscribers / customers.length) * 100) : 0;

      // ── 30-day new customer trend (week by week) ─────────────────────────
      const weekBuckets: Record<string, number> = {};
      for (const o of recentOrders) {
        const cust = customers.find((c) => c.id === o.customer?.id);
        if (cust && cust.orders_count <= 1) {
          const week = `W${Math.ceil((new Date(o.created_at).getDate()) / 7)}`;
          weekBuckets[week] = (weekBuckets[week] ?? 0) + 1;
        }
      }
      const newCustomerTrend = Object.entries(weekBuckets).map(([week, count]) => ({ week, count }));

      return NextResponse.json({
        connected: true,
        repeatRate,
        repeatCustomers,
        totalCustomers: customers.length,
        atRiskCount: atRiskCustomers.length,
        revenueAtRisk,
        avgLtv,
        aov,
        newCust,
        returningCust,
        channelRevenue,
        subscriberRate,
        subscribers,
        avgOrderGap,
        newCustomerTrend,
      });
    }

    // ── Policies ─────────────────────────────────────────────────────────────
    if (action === "policies") {
      const gql = `{
        shop {
          refundPolicy { title body url }
          privacyPolicy { title body url }
          termsOfService { title body url }
          shippingPolicy { title body url }
          legalNotice { title body url }
        }
      }`;
      const data = await shopifyPost(req, auth, `/admin/api/${SHOPIFY_API}/graphql.json`, { query: gql }) as {
        data?: { shop?: Record<string, { title: string; body: string; url: string } | null> };
      };
      return NextResponse.json({ policies: data?.data?.shop ?? {}, connected: true });
    }

    // ── Low stock check ─────────────────────────────────────────────────────
    if (action === "low_stock") {
      const threshold = parseInt(sp.get("threshold") ?? "5");
      const data = await shopifyGet(req, auth, `/admin/api/${SHOPIFY_API}/products.json`, {
        limit: "250", status: "active", fields: "id,title,variants",
      }) as { products: { id: number; title: string; variants: { id: number; title: string; sku: string; inventory_quantity: number }[] }[] };
      const low: { product_id: string; product_title: string; variant_id: string; variant_title: string; sku: string; quantity: number }[] = [];
      for (const p of data.products ?? []) {
        for (const v of p.variants ?? []) {
          if (v.inventory_quantity <= threshold) {
            low.push({ product_id: String(p.id), product_title: p.title, variant_id: String(v.id), variant_title: v.title, sku: v.sku, quantity: v.inventory_quantity });
          }
        }
      }
      low.sort((a, b) => a.quantity - b.quantity);
      return NextResponse.json({ low_stock: low, threshold, alert_count: low.length, connected: true });
    }

    // ── Auto-fulfillment history ───────────────────────────────────────────────
    if (action === "auto_fulfillments") {
      return NextResponse.json({ message: "Query via backend /api/shopify/auto-fulfillments", connected: true });
    }

    // ── Collections ──────────────────────────────────────────────────────────
    if (action === "collections") {
      const data = await shopifyGet(req, auth, `/admin/api/${SHOPIFY_API}/custom_collections.json`, {
        limit: "250",
        fields: "id,title,handle,products_count,published_at,sort_order",
      }) as { custom_collections: { id: number; title: string; handle: string; products_count: number; published_at: string | null; sort_order: string }[] };
      return NextResponse.json({ collections: data.custom_collections ?? [], connected: true });
    }

    return err("Unknown action");
  } catch (e) {
    return err(e instanceof Error ? e.message : "Shopify request failed", 500);
  }
}

// ── POST handler ──────────────────────────────────────────────────────────────

export async function POST(req: NextRequest) {
  const auth = req.headers.get("authorization");
  if (!(await resolveUserId(auth))) return err("Unauthorized", 401);
  if (!(await shopifyConnected(req, auth))) {
    return err("Shopify not connected", 400);
  }

  const body = await req.json() as {
    action: string;
    orderId?: string;
    reason?: string;
    // inventory
    inventoryItemId?: string;
    locationId?: string;
    adjustment?: number;
    available?: number;
    // discount
    code?: string;
    valueType?: "percentage" | "fixed_amount";
    value?: number;
    minPurchase?: number;
    usageLimit?: number;
    endsAt?: string;
    priceRuleId?: string;
    // product
    variantId?: string;
    newPrice?: string;
    // customer email
    to?: string;
    subject?: string;
    emailBody?: string;
    // note
    noteText?: string;
    // product creation
    product?: {
      title: string;
      description?: string;
      product_type?: string;
      price: string;
      compare_at_price?: string;
      tags?: string;
      vendor?: string;
      variants?: { title: string; price: string; compare_at_price?: string; inventory_quantity?: number }[];
    };
    // product deletion
    productId?: string;
    productIds?: string[];
    // product update
    title?: string;
    description?: string;
    tags?: string;
    vendor?: string;
    productType?: string;
    status?: string;
    // collections
    collectionId?: string;
    collectionIds?: string[];
    // policies (set_policy action)
    refundPolicy?: string;
    privacyPolicy?: string;
    termsOfService?: string;
    shippingPolicy?: string;
    legalNotice?: string;
    // customer update
    customerId?: string;
    first_name?: string;
    last_name?: string;
    email?: string;
    phone?: string;
    note?: string;
    // product images
    imageUrls?: string[];
    // seo
    seoTitle?: string;
    seoDescription?: string;
  };

  try {
    // ── Fulfill order ────────────────────────────────────────────────────────
    if (body.action === "fulfill") {
      if (!body.orderId) return err("orderId required");
      // Get fulfillment orders first
      const foData = await shopifyGet(req, auth, `/admin/api/${SHOPIFY_API}/orders/${body.orderId}/fulfillment_orders.json`) as { fulfillment_orders: { id: number; status: string }[] };
      const openFOs = (foData.fulfillment_orders ?? []).filter((fo) => fo.status === "open");
      if (!openFOs.length) return NextResponse.json({ ok: true, message: "Already fulfilled" });

      const result = await shopifyPost(req, auth, `/admin/api/${SHOPIFY_API}/fulfillments.json`, {
        fulfillment: {
          line_items_by_fulfillment_order: openFOs.map((fo) => ({ fulfillment_order_id: fo.id })),
          notify_customer: true,
        },
      });
      return NextResponse.json({ ok: true, fulfillment: result });
    }

    // ── Cancel order ─────────────────────────────────────────────────────────
    if (body.action === "cancel") {
      if (!body.orderId) return err("orderId required");
      const result = await shopifyPost(req, auth, `/admin/api/${SHOPIFY_API}/orders/${body.orderId}/cancel.json`, {
        reason: body.reason ?? "customer",
        email: true,
        refund: true,
      });
      return NextResponse.json({ ok: true, order: result });
    }

    // ── Adjust inventory ─────────────────────────────────────────────────────
    if (body.action === "adjust_inventory") {
      if (!body.inventoryItemId || !body.locationId) return err("inventoryItemId and locationId required");
      if (body.available !== undefined) {
        // Absolute set
        const result = await shopifyPost(req, auth, `/admin/api/${SHOPIFY_API}/inventory_levels/set.json`, {
          location_id: parseInt(body.locationId),
          inventory_item_id: parseInt(body.inventoryItemId),
          available: body.available,
        });
        return NextResponse.json({ ok: true, inventoryLevel: result });
      }
      if (body.adjustment !== undefined) {
        const result = await shopifyPost(req, auth, `/admin/api/${SHOPIFY_API}/inventory_levels/adjust.json`, {
          location_id: parseInt(body.locationId),
          inventory_item_id: parseInt(body.inventoryItemId),
          available_adjustment: body.adjustment,
        });
        return NextResponse.json({ ok: true, inventoryLevel: result });
      }
      return err("available or adjustment required");
    }

    // ── Create discount ──────────────────────────────────────────────────────
    if (body.action === "create_discount") {
      if (!body.code || !body.valueType || body.value === undefined) return err("code, valueType, value required");
      // Create price rule
      const priceRuleBody: Record<string, unknown> = {
        price_rule: {
          title: body.code,
          target_type: "line_item",
          target_selection: "all",
          allocation_method: "across",
          value_type: body.valueType,
          value: String(-Math.abs(body.value)),
          customer_selection: "all",
          starts_at: new Date().toISOString(),
          ...(body.endsAt ? { ends_at: new Date(body.endsAt).toISOString() } : {}),
          ...(body.usageLimit ? { usage_limit: body.usageLimit } : {}),
          ...(body.minPurchase ? {
            prerequisite_subtotal_range: { greater_than_or_equal_to: String(body.minPurchase) },
          } : {}),
        },
      };
      const ruleResult = await shopifyPost(req, auth, `/admin/api/${SHOPIFY_API}/price_rules.json`, priceRuleBody) as { price_rule: { id: number } };
      const ruleId = ruleResult.price_rule.id;
      // Create discount code
      const codeResult = await shopifyPost(req, auth, `/admin/api/${SHOPIFY_API}/price_rules/${ruleId}/discount_codes.json`, {
        discount_code: { code: body.code.toUpperCase() },
      });
      return NextResponse.json({ ok: true, priceRuleId: ruleId, discountCode: codeResult });
    }

    // ── Delete discount ──────────────────────────────────────────────────────
    if (body.action === "delete_discount") {
      if (!body.priceRuleId) return err("priceRuleId required");
      await shopifyDelete(req, auth, `/admin/api/${SHOPIFY_API}/price_rules/${body.priceRuleId}.json`);
      return NextResponse.json({ ok: true });
    }

    // ── Add order note ───────────────────────────────────────────────────────
    if (body.action === "add_note") {
      if (!body.orderId || !body.noteText) return err("orderId and noteText required");
      const result = await shopifyPut(req, auth, `/admin/api/${SHOPIFY_API}/orders/${body.orderId}.json`, {
        order: { id: body.orderId, note: body.noteText },
      });
      return NextResponse.json({ ok: true, order: result });
    }

    // ── Update variant price ─────────────────────────────────────────────────
    if (body.action === "update_price") {
      if (!body.variantId || !body.newPrice) return err("variantId and newPrice required");
      const result = await shopifyPut(req, auth, `/admin/api/${SHOPIFY_API}/variants/${body.variantId}.json`, {
        variant: { id: body.variantId, price: body.newPrice },
      });
      return NextResponse.json({ ok: true, variant: result });
    }

    // ── Create product (AI sourced or manual) ────────────────────────────────
    if (body.action === "create_product") {
      if (!body.product?.title) return err("product.title required");
      const p = body.product;
      const variants = (p.variants && p.variants.length > 0)
        ? p.variants.map((v) => ({
            title: v.title ?? "Default Title",
            price: v.price ?? p.price,
            ...(v.compare_at_price ? { compare_at_price: v.compare_at_price } : {}),
            inventory_management: "shopify",
            inventory_quantity: v.inventory_quantity ?? 10,
          }))
        : [{ title: "Default Title", price: p.price, inventory_management: "shopify", inventory_quantity: 10,
             ...(p.compare_at_price ? { compare_at_price: p.compare_at_price } : {}) }];

      const payload = {
        product: {
          title: p.title,
          body_html: p.description ? `<p>${p.description.replace(/\n/g, "</p><p>")}</p>` : "",
          vendor: p.vendor ?? "",
          product_type: p.product_type ?? "",
          status: "active",
          tags: p.tags ?? "",
          variants,
        },
      };
      const result = await shopifyPost(req, auth, `/admin/api/${SHOPIFY_API}/products.json`, payload) as { product: { id: number; title: string; handle: string; admin_graphql_api_id: string } };
      return NextResponse.json({ ok: true, product: result.product });
    }

    // ── Delete single product ────────────────────────────────────────────────
    if (body.action === "delete_product") {
      if (!body.productId) return err("productId required");
      await shopifyDelete(req, auth, `/admin/api/${SHOPIFY_API}/products/${body.productId}.json`);
      return NextResponse.json({ ok: true });
    }

    // ── Bulk delete products ─────────────────────────────────────────────────
    if (body.action === "bulk_delete_products") {
      if (!body.productIds?.length) return err("productIds required");
      const results = await Promise.allSettled(
        body.productIds.map((id) =>
          shopifyDelete(req, auth, `/admin/api/${SHOPIFY_API}/products/${id}.json`)
        )
      );
      const failed = results.filter((r) => r.status === "rejected").length;
      return NextResponse.json({ ok: true, deleted: results.length - failed, failed });
    }

    // ── Update product ───────────────────────────────────────────────────────
    if (body.action === "update_product") {
      if (!body.productId) return err("productId required");
      const update: Record<string, unknown> = { id: body.productId };
      if (body.title)        update.title        = body.title;
      if (body.description)  update.body_html    = `<p>${body.description}</p>`;
      if (body.tags != null) update.tags         = body.tags;
      if (body.vendor)       update.vendor       = body.vendor;
      if (body.productType)  update.product_type = body.productType;
      if (body.status)       update.status       = body.status;
      const result = await shopifyPut(req, auth, `/admin/api/${SHOPIFY_API}/products/${body.productId}.json`, { product: update });
      return NextResponse.json({ ok: true, product: (result as { product?: unknown }).product });
    }

    // ── Create collection ────────────────────────────────────────────────────
    if (body.action === "create_collection") {
      if (!body.title) return err("title required");
      const result = await shopifyPost(req, auth, `/admin/api/${SHOPIFY_API}/custom_collections.json`, {
        custom_collection: {
          title:      body.title,
          body_html:  body.description ? `<p>${body.description}</p>` : "",
          published:  true,
          sort_order: "best-selling",
        },
      }) as { custom_collection: { id: number; title: string; handle: string } };
      return NextResponse.json({ ok: true, collection: result.custom_collection });
    }

    // ── Add products to collection ───────────────────────────────────────────
    if (body.action === "add_to_collection") {
      if (!body.collectionId || !body.productIds?.length) return err("collectionId and productIds required");
      const results = await Promise.allSettled(
        body.productIds.map((pid: string) =>
          shopifyPost(req, auth, `/admin/api/${SHOPIFY_API}/collects.json`, {
            collect: { collection_id: body.collectionId, product_id: pid },
          })
        )
      );
      const added = results.filter((r) => r.status === "fulfilled").length;
      const failed = results.length - added;
      return NextResponse.json({ ok: true, added, failed });
    }

    // ── Delete collection(s) ──────────────────────────────────────────────────
    if (body.action === "delete_collection") {
      const ids: string[] = body.collectionIds ?? (body.collectionId ? [body.collectionId] : []);
      if (!ids.length) return err("collectionId or collectionIds required");
      let deleted = 0, failed = 0;
      for (const cid of ids) {
        // Try custom collection first, fall back to smart collection
        let ok = false;
        try {
          await shopifyDelete(req, auth, `/admin/api/${SHOPIFY_API}/custom_collections/${cid}.json`);
          ok = true;
        } catch { /* try smart */ }
        if (!ok) {
          try {
            await shopifyDelete(req, auth, `/admin/api/${SHOPIFY_API}/smart_collections/${cid}.json`);
            ok = true;
          } catch { failed++; continue; }
        }
        if (ok) deleted++;
      }
      return NextResponse.json({ ok: failed === 0, deleted, failed });
    }

    // ── Update customer ───────────────────────────────────────────────────────
    if (body.action === "update_customer") {
      if (!body.customerId) return err("customerId required");
      const update: Record<string, unknown> = { id: body.customerId };
      for (const f of ["first_name","last_name","email","phone","note","tags"] as const) {
        if (body[f as keyof typeof body] != null) update[f] = body[f as keyof typeof body];
      }
      const result = await shopifyPut(req, auth, `/admin/api/${SHOPIFY_API}/customers/${body.customerId}.json`, { customer: update });
      return NextResponse.json({ ok: true, customer: (result as { customer?: unknown }).customer });
    }

    // ── Add product images ────────────────────────────────────────────────────
    if (body.action === "add_product_images") {
      if (!body.productId || !body.imageUrls?.length) return err("productId and imageUrls required");
      const results = await Promise.allSettled(
        body.imageUrls.map((url: string) =>
          shopifyPost(req, auth, `/admin/api/${SHOPIFY_API}/products/${body.productId}/images.json`, { image: { src: url } })
        )
      );
      const added = results.filter((r) => r.status === "fulfilled").length;
      return NextResponse.json({ ok: true, added, failed: results.length - added });
    }

    // ── Set SEO metafields ────────────────────────────────────────────────────
    if (body.action === "set_seo_metafields") {
      if (!body.productId) return err("productId required");
      const mfs: { namespace: string; key: string; value: string; type: string }[] = [];
      if (body.seoTitle)       mfs.push({ namespace: "global", key: "title_tag",       value: body.seoTitle,       type: "single_line_text_field" });
      if (body.seoDescription) mfs.push({ namespace: "global", key: "description_tag", value: body.seoDescription, type: "single_line_text_field" });
      if (!mfs.length) return err("seoTitle or seoDescription required");
      const results = await Promise.allSettled(
        mfs.map((mf) => shopifyPost(req, auth, `/admin/api/${SHOPIFY_API}/products/${body.productId}/metafields.json`, { metafield: mf }))
      );
      return NextResponse.json({ ok: true, set: results.filter((r) => r.status === "fulfilled").length });
    }

    // ── Set store policies via GraphQL ───────────────────────────────────────
    if (body.action === "set_policy") {
      const policyMap: Record<string, string> = {
        refundPolicy:    body.refundPolicy    ?? "",
        privacyPolicy:   body.privacyPolicy   ?? "",
        termsOfService:  body.termsOfService  ?? "",
        shippingPolicy:  body.shippingPolicy  ?? "",
        legalNotice:     body.legalNotice     ?? "",
      };
      const provided = Object.entries(policyMap).filter(([, v]) => v);
      if (!provided.length) return err("At least one policy field required");

      const mutArgs  = provided.map(([k]) => `$${k}: ShopPolicyInput`).join(", ");
      const callArgs = provided.map(([k]) => `${k}: $${k}`).join(", ");
      const mutation = `
        mutation SetPolicies(${mutArgs}) {
          shopPoliciesUpdate(${callArgs}) {
            shopPolicies { type title url }
            userErrors { field message }
          }
        }`;
      const variables = Object.fromEntries(provided.map(([k, v]) => [k, { body: v }]));
      const result = await shopifyPost(req, auth, `/admin/api/${SHOPIFY_API}/graphql.json`, {
        query: mutation, variables,
      }) as { data?: { shopPoliciesUpdate?: { shopPolicies: { type: string }[]; userErrors: { field: string; message: string }[] } } };

      const gqlResult = result?.data?.shopPoliciesUpdate;
      const errors = gqlResult?.userErrors ?? [];
      if (errors.length) return NextResponse.json({ ok: false, errors }, { status: 422 });
      return NextResponse.json({ ok: true, updated: gqlResult?.shopPolicies?.map((p) => p.type) ?? [] });
    }

    return err("Unknown action");
  } catch (e) {
    return err(e instanceof Error ? e.message : "Shopify operation failed", 500);
  }
}

// ── Types ─────────────────────────────────────────────────────────────────────

export type ShopifyOrder = {
  id: number;
  order_number: number;
  name: string;
  email: string;
  created_at: string;
  updated_at: string;
  financial_status: string;
  fulfillment_status: string | null;
  total_price: string;
  subtotal_price: string;
  total_discounts: string;
  currency: string;
  customer: { id: number; first_name: string; last_name: string; email: string; orders_count?: number; total_spent?: string };
  line_items: { id: number; title: string; quantity: number; price: string; variant_title?: string; product_id?: number; sku?: string }[];
  shipping_address?: { first_name: string; last_name: string; address1: string; city: string; country: string; zip?: string };
  note?: string;
  tags?: string;
  refunds?: unknown[];
  fulfillments?: unknown[];
};

export type ShopifyProduct = {
  id: number;
  title: string;
  handle: string;
  product_type: string;
  status: string;
  variants: { id: number; title: string; price: string; sku: string; inventory_quantity: number; inventory_item_id: number }[];
  image?: { src: string };
  images?: { src: string }[];
};

export type ShopifyCustomer = {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  orders_count: number;
  total_spent: string;
  created_at: string;
  updated_at: string;
  last_order_name?: string;
  tags?: string;
  accepts_marketing: boolean;
  default_address?: { city?: string; country?: string };
};

export type ShopifyCheckout = {
  id: number;
  token: string;
  email: string;
  created_at: string;
  updated_at: string;
  total_price: string;
  subtotal_price: string;
  currency: string;
  line_items: { title: string; quantity: number; price: string }[];
  abandoned_checkout_url?: string;
};

export type ShopifyPriceRule = {
  id: number;
  title: string;
  value_type: "fixed_amount" | "percentage";
  value: string;
  customer_selection: string;
  starts_at: string;
  ends_at: string | null;
  usage_limit: number | null;
  times_used: number;
  created_at: string;
  codes?: { code: string; usage_count: number }[];
};

export type ShopifyLocation = {
  id: number;
  name: string;
  active: boolean;
};
