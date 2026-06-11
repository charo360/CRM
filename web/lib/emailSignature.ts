import type { BusinessSettings } from "@/lib/api";

export type PersonalProfile = {
  name: string;
  title: string;
  company: string;
};

const PLACEHOLDER_RE = /\[(?:Your Name|Your Position|Your Company|Phone\/Email)\]/i;

export function personalProfileFromSettings(settings: BusinessSettings | null | undefined): PersonalProfile {
  return {
    name: (settings?.owner_name || "").trim(),
    title: (settings?.owner_title || "").trim(),
    company: (settings?.business_name || "").trim(),
  };
}

export function formatEmailClosing(profile: PersonalProfile, closing = "Best"): string {
  const lines = [`${closing.trim() || "Best"},`];
  if (profile.name) lines.push(profile.name);
  if (profile.title) lines.push(profile.title);
  if (profile.company) lines.push(profile.company);
  return lines.join("\n");
}

const CLOSING_LINE_RE =
  /^\s*(best|best regards|kind regards|regards|thanks|thank you|sincerely|cheers),?\s*$/i;

/** True when the body already ends with a personal sign-off block. */
export function hasExistingSignature(text: string, profile: PersonalProfile): boolean {
  const lines = (text || "")
    .trim()
    .split("\n")
    .map((ln) => ln.trim())
    .filter(Boolean);
  if (lines.length < 2) return false;

  const name = profile.name.toLowerCase();
  const title = profile.title.toLowerCase();
  const company = profile.company.toLowerCase();
  const tail = lines.slice(-6);
  const tailLower = tail.map((ln) => ln.toLowerCase());

  if (name && tailLower.some((ln) => ln.includes(name))) return true;
  if (title && company) {
    const hasTitle = tailLower.some((ln) => ln.includes(title));
    const hasCompany = tailLower.some((ln) => ln.includes(company));
    if (hasTitle && hasCompany) return true;
  }

  for (let i = 0; i < tail.length; i++) {
    if (CLOSING_LINE_RE.test(tail[i])) {
      const trailing = tail.slice(i + 1);
      if (trailing.length > 0 && trailing.some((t) => t.length > 2)) return true;
    }
  }
  return false;
}

export function applyPersonalSignature(
  body: string,
  profile: PersonalProfile,
  options?: { appendIfMissing?: boolean }
): string {
  const appendIfMissing = options?.appendIfMissing !== false;
  let text = (body || "").trim();
  if (!text) return text;

  const replacements: Record<string, string> = {
    "[Your Name]": profile.name || "[Your Name]",
    "[Your Position]": profile.title || "[Your Position]",
    "[Your Company]": profile.company || "[Your Company]",
  };
  for (const [placeholder, value] of Object.entries(replacements)) {
    text = text.split(placeholder).join(value);
  }

  if (!appendIfMissing || hasExistingSignature(text, profile)) {
    return text;
  }

  const sigLines = [profile.name, profile.title, profile.company].filter(Boolean);
  if (sigLines.length && !PLACEHOLDER_RE.test(text)) {
    const tail = text.replace(/\s+$/, "");
    if (/\b(best|best regards|kind regards|regards|thanks|thank you),?\s*$/i.test(tail)) {
      text = `${tail}\n${sigLines.join("\n")}`;
    }
  }

  return text;
}

export function hasSignaturePlaceholders(text: string): boolean {
  return PLACEHOLDER_RE.test(text || "");
}

export {
  adaptProfileForPlatform,
  buildPlatformCommentDraft,
  normalizeSocialPlatform,
  PLATFORM_IDENTITY_HINTS,
  substituteSocialTemplate,
  senderDisplayName,
} from "@/lib/socialPlatformProfile";
export type { AdaptedSocialProfile } from "@/lib/socialPlatformProfile";
