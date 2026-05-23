/** Client-side mirror of PayHero Kenya tiers (sync with backend/payhero_rates.py). */
export const PAYHERO_RATE_CARD_VERSION = "kenya-mpesa-v1";

// mirrors is PayHero’s Kenya rate card — what your app uses to quote and record usage, not Safaricom’s standard M-Pesa charges on the payer’s phone.

// Per successful M-Pesa collection (STK / Paybill / Till, etc.): a flat KES fee from the bracket for that payment amount (e.g. KES 500–999 → KES 10).
export const PAYHERO_MPESA_TIERS: { minKes: number; maxKes: number; feeKes: number }[] = [
  { minKes: 1, maxKes: 49, feeKes: 1 },
  { minKes: 50, maxKes: 499, feeKes: 6 },
  { minKes: 500, maxKes: 999, feeKes: 10 },
  { minKes: 1000, maxKes: 1499, feeKes: 15 },
  { minKes: 1500, maxKes: 2499, feeKes: 20 },
  { minKes: 2500, maxKes: 3499, feeKes: 25 },
  { minKes: 3500, maxKes: 4999, feeKes: 30 },
  { minKes: 5000, maxKes: 7499, feeKes: 40 },
  { minKes: 7500, maxKes: 9999, feeKes: 45 },
  { minKes: 10000, maxKes: 14999, feeKes: 50 },
  { minKes: 15000, maxKes: 19999, feeKes: 55 },
  { minKes: 20000, maxKes: 34999, feeKes: 80 },
  { minKes: 35000, maxKes: 49999, feeKes: 105 },
  { minKes: 50000, maxKes: 149999, feeKes: 130 },
  { minKes: 150000, maxKes: 249999, feeKes: 160 },
  { minKes: 250000, maxKes: 349999, feeKes: 180 },
  { minKes: 350000, maxKes: 549999, feeKes: 210 },
  { minKes: 550000, maxKes: 749999, feeKes: 240 },
  { minKes: 750000, maxKes: 999999, feeKes: 270 },
];

//  Per SMS sent via PayHero.
export const PAYHERO_SMS_KES = 1.8;
// Per WhatsApp message via PayHero.
export const PAYHERO_WHATSAPP_KES = 0.6;

export function estimateMpesaFeeKes(amount: number): number {
  const amt = Math.round(amount);
  for (const t of PAYHERO_MPESA_TIERS) {
    if (amt >= t.minKes && amt <= t.maxKes) return t.feeKes;
  }
  if (amt > 0) return PAYHERO_MPESA_TIERS[PAYHERO_MPESA_TIERS.length - 1].feeKes;
  return 0;
}
