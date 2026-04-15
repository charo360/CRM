import fs from "fs";

const data = JSON.parse(fs.readFileSync("_countries_raw.json", "utf8"));
const rows = data
  .map((x) => {
    const keys = x.currencies ? Object.keys(x.currencies) : [];
    let cur = keys[0];
    if (keys.length > 1 && keys.includes("USD") && keys[0] === "USD") {
      cur = keys.find((k) => k !== "USD") || keys[0];
    }
    return { code: x.cca2, name: x.name.common, currency: cur || "USD" };
  })
  .filter((r) => r.code)
  .sort((a, b) => a.name.localeCompare(b.name));

const curSet = new Set(rows.map((r) => r.currency));
const currencies = [...curSet].sort();

const out =
  `/** Auto-generated from restcountries.com — ISO 3166-1 alpha-2 + default ISO 4217. */\n` +
  `export type WorldCountry = { code: string; name: string; currency: string };\n` +
  `export const WORLD_COUNTRIES: WorldCountry[] = ${JSON.stringify(rows, null, 2)};\n` +
  `export const ALL_CURRENCY_CODES: string[] = ${JSON.stringify(currencies)};\n` +
  `export function getCountryByCode(code: string): WorldCountry | undefined {\n` +
  `  return WORLD_COUNTRIES.find((c) => c.code === code);\n` +
  `}\n` +
  `export function defaultCurrencyForCountryCode(code: string): string {\n` +
  `  return getCountryByCode(code)?.currency ?? "USD";\n` +
  `}\n`;

fs.writeFileSync("worldCountries.ts", out);
console.log("countries", rows.length, "currencies", currencies.length);
