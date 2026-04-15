"use client";

import type { BusinessKnowledge } from "@/lib/api";

type Patch = Record<string, unknown>;

function Check({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-start gap-3 py-2">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-1 w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
      />
      <div>
        <label className="text-sm font-medium text-slate-800">{label}</label>
        {hint && <p className="text-xs text-slate-500 mt-0.5">{hint}</p>}
      </div>
    </div>
  );
}

function Row({
  label,
  hint,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-700 mb-1">{label}</label>
      {hint && <p className="text-xs text-slate-500 mb-1">{hint}</p>}
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500"
      />
    </div>
  );
}

function num(bk: BusinessKnowledge, k: string, fallback = ""): string {
  const v = bk[k];
  if (v === undefined || v === null) return fallback;
  return String(v);
}

function bool(bk: BusinessKnowledge, k: string, defaultVal = false): boolean {
  const v = bk[k];
  if (v === undefined || v === null) return defaultVal;
  return Boolean(v);
}

export function TypeFields({
  businessType,
  bk,
  patchBk,
}: {
  businessType: string;
  bk: BusinessKnowledge;
  patchBk: (p: Patch) => void;
}) {
  const t = businessType || "other";

  const set = (p: Patch) => patchBk(p);

  return (
    <div className="space-y-8">
      <div>
        <h3 className="text-sm font-semibold text-slate-900 mb-1">Business-type operations</h3>
        <p className="text-xs text-slate-500 mb-4">
          These power AI replies and booking flows (same as the mobile app).
        </p>
      </div>

      {t === "retail" && (
        <section className="space-y-3 border-t border-slate-100 pt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Retail</p>
          <Check label="Offer delivery" checked={bool(bk, "retail_has_delivery", true)} onChange={(v) => set({ retail_has_delivery: v })} />
          <Check label="Offer pickup" checked={bool(bk, "retail_has_pickup", true)} onChange={(v) => set({ retail_has_pickup: v })} />
          <Row label="Delivery fee" value={num(bk, "retail_delivery_fee")} onChange={(v) => set({ retail_delivery_fee: v })} placeholder="e.g. KES 200" />
          <Row label="Free delivery above" value={num(bk, "retail_free_delivery_above")} onChange={(v) => set({ retail_free_delivery_above: v })} />
          <Check label="Custom / made-to-order" checked={bool(bk, "retail_has_custom_orders")} onChange={(v) => set({ retail_has_custom_orders: v })} />
          <Row label="Custom order lead time" value={num(bk, "retail_custom_lead_time")} onChange={(v) => set({ retail_custom_lead_time: v })} />
          <Row label="Return policy" value={String(bk.retail_return_policy ?? "")} onChange={(v) => set({ retail_return_policy: v })} placeholder="Returns & exchanges" />
        </section>
      )}

      {t === "grocery" && (
        <section className="space-y-3 border-t border-slate-100 pt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Grocery</p>
          <Row label="Min. order value" value={num(bk, "grocery_min_order")} onChange={(v) => set({ grocery_min_order: v })} />
          <Row label="Delivery slots" value={String(bk.grocery_delivery_slots ?? "")} onChange={(v) => set({ grocery_delivery_slots: v })} />
          <Check label="Suggest substitutes" checked={bool(bk, "grocery_allow_substitutions", true)} onChange={(v) => set({ grocery_allow_substitutions: v })} />
        </section>
      )}

      {(t === "restaurant" || t === "food") && (
        <section className="space-y-3 border-t border-slate-100 pt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Restaurant</p>
          <Check label="Dine-in" checked={bool(bk, "restaurant_has_dine_in")} onChange={(v) => set({ restaurant_has_dine_in: v })} />
          <Check label="Delivery" checked={bool(bk, "restaurant_has_delivery")} onChange={(v) => set({ restaurant_has_delivery: v })} />
          <Check label="Takeout" checked={bool(bk, "restaurant_has_takeout")} onChange={(v) => set({ restaurant_has_takeout: v })} />
          <Row label="Avg. wait / prep" value={String(bk.restaurant_avg_wait ?? "")} onChange={(v) => set({ restaurant_avg_wait: v })} />
          <Row label="Min. delivery order" value={String(bk.restaurant_min_delivery ?? "")} onChange={(v) => set({ restaurant_min_delivery: v })} />
          {t === "restaurant" && (
            <Row label="Table range" hint="Helps AI ask for table numbers" value={String(bk.restaurant_table_range ?? "")} onChange={(v) => set({ restaurant_table_range: v })} placeholder="e.g. Tables 1–20" />
          )}
        </section>
      )}

      {t === "bakery" && (
        <section className="space-y-3 border-t border-slate-100 pt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Bakery</p>
          <Row label="Advance notice (days)" type="number" value={num(bk, "bakery_advance_days", "3")} onChange={(v) => set({ bakery_advance_days: parseInt(v, 10) || 3 })} />
          <Check label="Require deposit for custom orders" checked={bool(bk, "bakery_deposit_required")} onChange={(v) => set({ bakery_deposit_required: v })} />
          {bool(bk, "bakery_deposit_required") && (
            <Row label="Deposit %" type="number" value={num(bk, "bakery_deposit_pct", "50")} onChange={(v) => set({ bakery_deposit_pct: parseInt(v, 10) || 50 })} />
          )}
        </section>
      )}

      {t === "wholesale" && (
        <section className="space-y-3 border-t border-slate-100 pt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Wholesale</p>
          <Row label="Lead time" value={String(bk.wholesale_lead_time ?? "")} onChange={(v) => set({ wholesale_lead_time: v })} />
          <Row label="Min. order value" value={String(bk.wholesale_min_order_value ?? "")} onChange={(v) => set({ wholesale_min_order_value: v })} />
          <Row label="Payment terms" value={String(bk.wholesale_payment_terms ?? "")} onChange={(v) => set({ wholesale_payment_terms: v })} />
          <Check label="Credit accounts" checked={bool(bk, "wholesale_has_credit_account")} onChange={(v) => set({ wholesale_has_credit_account: v })} />
        </section>
      )}

      {(t === "salon" || t === "spa") && (
        <section className="space-y-3 border-t border-slate-100 pt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t === "spa" ? "Spa" : "Salon"}</p>
          {t === "salon" && (
            <>
              <Check label="Multiple stylists" checked={bool(bk, "salon_multiple_stylists")} onChange={(v) => set({ salon_multiple_stylists: v })} />
              {bool(bk, "salon_multiple_stylists") && (
                <Row label="Stylist names" value={String(bk.salon_stylist_names ?? "")} onChange={(v) => set({ salon_stylist_names: v })} placeholder="Comma-separated" />
              )}
              <Check label="Require deposit" checked={bool(bk, "salon_deposit_required")} onChange={(v) => set({ salon_deposit_required: v })} />
              {bool(bk, "salon_deposit_required") && (
                <Row label="Deposit %" type="number" value={num(bk, "salon_deposit_pct", "50")} onChange={(v) => set({ salon_deposit_pct: parseInt(v, 10) || 50 })} />
              )}
              <Row label="Cancellation policy" value={String(bk.salon_cancellation_policy ?? "")} onChange={(v) => set({ salon_cancellation_policy: v })} />
            </>
          )}
          {t === "spa" && (
            <>
              <Check label="Couples treatments" checked={bool(bk, "spa_has_couples", true)} onChange={(v) => set({ spa_has_couples: v })} />
              <Check label="Require deposit" checked={bool(bk, "spa_deposit_required", true)} onChange={(v) => set({ spa_deposit_required: v })} />
              {bool(bk, "spa_deposit_required") && (
                <Row label="Deposit %" type="number" value={num(bk, "spa_deposit_pct", "50")} onChange={(v) => set({ spa_deposit_pct: parseInt(v, 10) || 50 })} />
              )}
              <Row label="Cancellation notice (hours)" type="number" value={num(bk, "spa_cancellation_hours", "24")} onChange={(v) => set({ spa_cancellation_hours: parseInt(v, 10) || 24 })} />
            </>
          )}
        </section>
      )}

      {t === "repair" && (
        <section className="space-y-3 border-t border-slate-100 pt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Repair</p>
          <Check label="On-site visits" checked={bool(bk, "repair_has_onsite", true)} onChange={(v) => set({ repair_has_onsite: v })} />
          <Check label="Drop-off at shop" checked={bool(bk, "repair_has_dropoff", true)} onChange={(v) => set({ repair_has_dropoff: v })} />
          <Check label="Free diagnosis" checked={bool(bk, "repair_diagnosis_free", true)} onChange={(v) => set({ repair_diagnosis_free: v })} />
          <Row label="Typical turnaround" value={String(bk.repair_turnaround ?? "")} onChange={(v) => set({ repair_turnaround: v })} />
          <Row label="Warranty policy" value={String(bk.repair_warranty ?? "")} onChange={(v) => set({ repair_warranty: v })} />
        </section>
      )}

      {t === "services" && (
        <section className="space-y-3 border-t border-slate-100 pt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Services</p>
          <Check label="On-site / field work" checked={bool(bk, "services_has_onsite", true)} onChange={(v) => set({ services_has_onsite: v })} />
          <Check label="Remote work" checked={bool(bk, "services_has_remote", true)} onChange={(v) => set({ services_has_remote: v })} />
          <Check label="Quote first (owner confirms price)" checked={bool(bk, "services_quote_first")} onChange={(v) => set({ services_quote_first: v })} />
          <Check label="Require deposit" checked={bool(bk, "services_deposit_required")} onChange={(v) => set({ services_deposit_required: v })} />
          <Row label="Typical turnaround" value={String(bk.services_turnaround ?? "")} onChange={(v) => set({ services_turnaround: v })} />
          <Row label="Cancellation policy" value={String(bk.services_cancellation_policy ?? "")} onChange={(v) => set({ services_cancellation_policy: v })} />
        </section>
      )}

      {t === "support" && (
        <section className="space-y-3 border-t border-slate-100 pt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Support</p>
          <Row label="Ticket prefix" value={String(bk.support_ticket_prefix ?? "TKT")} onChange={(v) => set({ support_ticket_prefix: v })} />
          <Row label="Response SLA" value={String(bk.support_response_sla ?? "")} onChange={(v) => set({ support_response_sla: v })} />
          <Check label="Billing support" checked={bool(bk, "support_has_billing_support", true)} onChange={(v) => set({ support_has_billing_support: v })} />
          <Check label="Technical support" checked={bool(bk, "support_has_technical_support", true)} onChange={(v) => set({ support_has_technical_support: v })} />
          <Check label="Complaints handling" checked={bool(bk, "support_has_complaints", true)} onChange={(v) => set({ support_has_complaints: v })} />
          <Check label="Live handoff" checked={bool(bk, "support_has_live_handoff")} onChange={(v) => set({ support_has_live_handoff: v })} />
          <Row label="Escalation policy" value={String(bk.support_escalation_policy ?? "")} onChange={(v) => set({ support_escalation_policy: v })} />
          <Row label="Refund policy" value={String(bk.support_refund_policy ?? "")} onChange={(v) => set({ support_refund_policy: v })} />
        </section>
      )}

      {t === "hotel" && (
        <section className="space-y-3 border-t border-slate-100 pt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Hotel</p>
          <Row label="Check-in time" value={String(bk.hotel_checkin_time ?? "2:00 PM")} onChange={(v) => set({ hotel_checkin_time: v })} />
          <Row label="Check-out time" value={String(bk.hotel_checkout_time ?? "11:00 AM")} onChange={(v) => set({ hotel_checkout_time: v })} />
          <Row label="Minimum nights" type="number" value={num(bk, "hotel_min_nights")} onChange={(v) => set({ hotel_min_nights: v ? parseInt(v, 10) : 0 })} />
          <Check label="Require deposit" checked={bool(bk, "hotel_deposit_required", true)} onChange={(v) => set({ hotel_deposit_required: v })} />
          {bool(bk, "hotel_deposit_required") && (
            <Row label="Deposit %" type="number" value={num(bk, "hotel_deposit_pct", "30")} onChange={(v) => set({ hotel_deposit_pct: parseInt(v, 10) || 30 })} />
          )}
          <Check label="Meal plans" checked={bool(bk, "hotel_has_meal_plans")} onChange={(v) => set({ hotel_has_meal_plans: v })} />
          {bool(bk, "hotel_has_meal_plans") && (
            <Row label="Meal plan options" value={String(bk.hotel_meal_plan_options ?? "")} onChange={(v) => set({ hotel_meal_plan_options: v })} />
          )}
          <Check label="Airport transfer" checked={bool(bk, "hotel_has_airport_transfer")} onChange={(v) => set({ hotel_has_airport_transfer: v })} />
          <Check label="Spa amenity" checked={bool(bk, "hotel_has_spa")} onChange={(v) => set({ hotel_has_spa: v })} />
          <Check label="Pool amenity" checked={bool(bk, "hotel_has_pool")} onChange={(v) => set({ hotel_has_pool: v })} />
          <Row label="Cancellation policy" value={String(bk.hotel_cancellation_policy ?? "")} onChange={(v) => set({ hotel_cancellation_policy: v })} />
        </section>
      )}

      {t === "rental" && (
        <section className="space-y-3 border-t border-slate-100 pt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Rental</p>
          <Row label="Listing type" value={String(bk.rental_type ?? "property")} onChange={(v) => set({ rental_type: v })} placeholder="property | vehicle | equipment" />
          <Check label="Require deposit" checked={bool(bk, "rental_deposit_required", true)} onChange={(v) => set({ rental_deposit_required: v })} />
          {bool(bk, "rental_deposit_required") && (
            <Row label="Deposit %" type="number" value={num(bk, "rental_deposit_pct", "30")} onChange={(v) => set({ rental_deposit_pct: parseInt(v, 10) || 30 })} />
          )}
          <Row label="Min. nights" type="number" value={num(bk, "rental_min_nights")} onChange={(v) => set({ rental_min_nights: v ? parseInt(v, 10) : 0 })} />
          <Row label="Check-in time" value={String(bk.rental_checkin_time ?? "")} onChange={(v) => set({ rental_checkin_time: v })} />
          <Row label="Check-out time" value={String(bk.rental_checkout_time ?? "")} onChange={(v) => set({ rental_checkout_time: v })} />
          <Row label="Pet policy" value={String(bk.rental_pet_policy ?? "")} onChange={(v) => set({ rental_pet_policy: v })} />
          <Row label="Cancellation policy" value={String(bk.rental_cancellation_policy ?? "")} onChange={(v) => set({ rental_cancellation_policy: v })} />
          <Check label="Extras add-ons" checked={bool(bk, "rental_has_extras")} onChange={(v) => set({ rental_has_extras: v })} />
        </section>
      )}

      {t === "cleaning" && (
        <section className="space-y-3 border-t border-slate-100 pt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Cleaning</p>
          <Check label="Recurring bookings" checked={bool(bk, "cleaning_has_recurring", true)} onChange={(v) => set({ cleaning_has_recurring: v })} />
          <Check label="Commercial jobs" checked={bool(bk, "cleaning_has_commercial")} onChange={(v) => set({ cleaning_has_commercial: v })} />
          <Check label="Supplies included" checked={bool(bk, "cleaning_supplies_included", true)} onChange={(v) => set({ cleaning_supplies_included: v })} />
        </section>
      )}

      {t === "fitness" && (
        <section className="space-y-3 border-t border-slate-100 pt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Fitness</p>
          <Check label="Memberships" checked={bool(bk, "fitness_has_memberships", true)} onChange={(v) => set({ fitness_has_memberships: v })} />
          <Check label="Classes" checked={bool(bk, "fitness_has_classes", true)} onChange={(v) => set({ fitness_has_classes: v })} />
          <Check label="Personal training" checked={bool(bk, "fitness_has_personal_training")} onChange={(v) => set({ fitness_has_personal_training: v })} />
          <Check label="Trial sessions" checked={bool(bk, "fitness_has_trial", true)} onChange={(v) => set({ fitness_has_trial: v })} />
          <Row label="Class schedule" value={String(bk.fitness_class_schedule ?? "")} onChange={(v) => set({ fitness_class_schedule: v })} />
        </section>
      )}

      {t === "events" && (
        <section className="space-y-3 border-t border-slate-100 pt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Events</p>
          <Row label="Deposit %" type="number" value={num(bk, "events_deposit_pct", "50")} onChange={(v) => set({ events_deposit_pct: parseInt(v, 10) || 50 })} />
          <Row label="Lead time" value={String(bk.events_lead_time ?? "")} onChange={(v) => set({ events_lead_time: v })} />
          <Row label="Delivery / setup days" value={String(bk.events_delivery_days ?? "")} onChange={(v) => set({ events_delivery_days: v })} />
        </section>
      )}

      {t === "healthcare" && (
        <section className="space-y-3 border-t border-slate-100 pt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Healthcare</p>
          <Row label="Consultation fee" value={String(bk.hc_consultation_fee ?? "")} onChange={(v) => set({ hc_consultation_fee: v })} />
          <Check label="Lab tests" checked={bool(bk, "hc_has_lab_tests")} onChange={(v) => set({ hc_has_lab_tests: v })} />
          <Check label="Home visits" checked={bool(bk, "hc_has_home_visit")} onChange={(v) => set({ hc_has_home_visit: v })} />
          <Row label="Prep instructions" value={String(bk.hc_prep_instructions ?? "")} onChange={(v) => set({ hc_prep_instructions: v })} />
          <Row label="Insurance accepted" value={String(bk.hc_insurance_accepted ?? "")} onChange={(v) => set({ hc_insurance_accepted: v })} />
        </section>
      )}

      {t === "creator" && (
        <section className="space-y-3 border-t border-slate-100 pt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Creator</p>
          <Row label="Niche" value={String(bk.creator_niche ?? "")} onChange={(v) => set({ creator_niche: v })} />
          <Row label="Platforms" value={String(bk.creator_platforms ?? "")} onChange={(v) => set({ creator_platforms: v })} />
          <Row label="Audience / followers" value={String(bk.creator_followers ?? "")} onChange={(v) => set({ creator_followers: v })} />
          <Row label="Lead time" value={String(bk.creator_lead_time ?? "")} onChange={(v) => set({ creator_lead_time: v })} />
          <Row label="Revisions" value={String(bk.creator_revisions ?? "")} onChange={(v) => set({ creator_revisions: v })} />
          <Row label="Usage rights" value={String(bk.creator_usage_rights ?? "")} onChange={(v) => set({ creator_usage_rights: v })} />
          <Row label="Deposit %" type="number" value={num(bk, "creator_deposit_pct", "50")} onChange={(v) => set({ creator_deposit_pct: parseInt(v, 10) || 50 })} />
          <Check label="Rates on request only" checked={bool(bk, "creator_rates_on_request")} onChange={(v) => set({ creator_rates_on_request: v })} />
        </section>
      )}

      {t === "general" && (
        <p className="text-sm text-slate-500 border-t border-slate-100 pt-6">
          Use shared location, hours, and AI fields. Add specifics in Products & services and FAQs.
        </p>
      )}

      {![
        "retail",
        "grocery",
        "restaurant",
        "food",
        "bakery",
        "wholesale",
        "salon",
        "spa",
        "repair",
        "services",
        "support",
        "hotel",
        "rental",
        "cleaning",
        "fitness",
        "events",
        "healthcare",
        "creator",
        "general",
      ].includes(t) && (
        <p className="text-sm text-slate-500 border-t border-slate-100 pt-6">
          No extra type-specific fields for this category yet. Use Business info and AI sections.
        </p>
      )}
    </div>
  );
}
