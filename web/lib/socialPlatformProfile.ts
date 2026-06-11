import type { PersonalProfile } from "@/lib/emailSignature";

export type AdaptedSocialProfile = PersonalProfile & {
  first_name: string;
  full_name: string;
  sender_intro: string;
};

export function normalizeSocialPlatform(platform: string): string {
  const p = (platform || "").trim().toLowerCase();
  if (p === "x" || p === "twitter/x") return "twitter";
  if (p === "fb" || p === "meta") return "facebook";
  if (p === "ig") return "instagram";
  if (p === "li") return "linkedin";
  if (p === "gmail" || p === "outlook") return "email";
  return p || "default";
}

export function adaptProfileForPlatform(
  profile: PersonalProfile,
  platform = ""
): AdaptedSocialProfile {
  const p = normalizeSocialPlatform(platform);
  const fullName = profile.name.trim();
  const title = profile.title.trim();
  const company = profile.company.trim();
  const first = fullName.split(/\s+/)[0] || "";

  let adaptedName = fullName;
  let adaptedTitle = title;
  let senderIntro = fullName || company;

  if (p === "linkedin") {
    const bits = [fullName];
    if (title && company) bits.push(`${title} at ${company}`);
    else if (title) bits.push(title);
    else if (company) bits.push(company);
    senderIntro = bits.filter(Boolean).join(", ");
  } else if (p === "twitter") {
    adaptedName = first || fullName;
    adaptedTitle = "";
    senderIntro = first || fullName || company;
  } else if (["instagram", "facebook", "messenger", "tiktok", "whatsapp"].includes(p)) {
    adaptedName = first || fullName;
    adaptedTitle = "";
    senderIntro = first && company ? `${first} from ${company}` : first || fullName || company;
  } else if (p === "email") {
    senderIntro = [fullName, title, company].filter(Boolean).join(" · ") || fullName || company;
  } else if (fullName && company) {
    senderIntro = `${fullName} (${company})`;
  } else {
    senderIntro = fullName || company;
  }

  return {
    name: adaptedName || fullName,
    title: adaptedTitle,
    company,
    first_name: first,
    full_name: fullName,
    sender_intro: senderIntro,
  };
}

export function substituteSocialTemplate(
  text: string,
  profile: PersonalProfile,
  recipientFirstName = "",
  platform = ""
): string {
  let out = (text || "").trim();
  if (!out) return out;

  const adapted = adaptProfileForPlatform(profile, platform);
  const recipient = recipientFirstName.trim().split(/\s+/)[0];
  out = out.split("{name}").join(recipient || "there");

  const replacements: Record<string, string> = {
    "[Your Name]": adapted.name || adapted.full_name || "[Your Name]",
    "[Your Position]": adapted.title || "[Your Position]",
    "[Your Company]": adapted.company || "[Your Company]",
    "{your_name}": adapted.name || adapted.full_name,
    "{owner_name}": adapted.name || adapted.full_name,
    "{sender_name}": adapted.name || adapted.full_name,
    "{your_title}": adapted.title,
    "{owner_title}": adapted.title,
    "{your_position}": adapted.title,
    "{your_company}": adapted.company,
    "{business_name}": adapted.company,
    "{sender_intro}": adapted.sender_intro,
    "{your_first_name}": adapted.first_name,
    "{sender_first_name}": adapted.first_name,
    "{full_name}": adapted.full_name,
  };

  for (const [token, value] of Object.entries(replacements)) {
    if (value) out = out.split(token).join(value);
  }

  return out;
}

export function senderDisplayName(profile: PersonalProfile, platform = ""): string {
  const adapted = adaptProfileForPlatform(profile, platform);
  return adapted.name || adapted.full_name || adapted.company || "You";
}

/** Platform-specific quick comment reply opener (fallback when AI unavailable). */
function commentIntent(text: string): string {
  const low = text.toLowerCase();
  if (low.includes("?") || /\b(how|what|when|where|why|can you|do you)\b/.test(low)) return "question";
  if (/\b(price|cost|how much|quote|budget|rate)\b/.test(low)) return "pricing";
  if (/\b(thank|thanks|appreciate)\b/.test(low)) return "thanks";
  if (/\b(bad|worst|terrible|disappointed|refund|scam)\b/.test(low)) return "complaint";
  if (/\b(love|great|awesome|amazing|beautiful)\b/.test(low)) return "praise";
  return "general";
}

export function buildPlatformCommentDraft(
  platform: string,
  authorFirst: string,
  commentText: string
): string {
  const author = authorFirst || "there";
  const raw = commentText.trim();
  const p = normalizeSocialPlatform(platform);
  const intent = commentIntent(raw);
  const snippet = raw.length > 80 ? `${raw.slice(0, 80).trim()}…` : raw;

  if (p === "linkedin") {
    if (intent === "complaint") {
      return `Hi ${author}, sorry to hear that — I want to make this right. Message me directly and we will sort it out.`;
    }
    if (intent === "question") {
      return `Hi ${author}, good question about "${snippet}" — message me and I will share the details.`;
    }
    if (intent === "pricing") {
      return `Hi ${author}, happy to share pricing for what you need. Send me a DM with specifics and I will reply with options.`;
    }
    if (intent === "thanks") {
      return `You are welcome, ${author} — glad I could help.`;
    }
    if (intent === "praise") {
      return `Thank you, ${author} — really appreciate you saying that.`;
    }
    return `Hi ${author}, thanks for your comment on this. I will follow up with you shortly.`;
  }

  if (intent === "complaint") {
    return `Hi ${author}, sorry about that — we want to fix this. DM us and we will help you personally.`;
  }
  if (intent === "question") {
    return `Hi ${author}, great question! DM us with a bit more detail on "${snippet}" and we will help right away.`;
  }
  if (intent === "pricing") {
    return `Hi ${author}, thanks for asking! DM us what you are looking for and we will share price and options.`;
  }
  if (intent === "thanks") {
    return `You are welcome ${author} — we appreciate you!`;
  }
  if (intent === "praise") {
    return `Thank you ${author} — that means a lot to us!`;
  }
  if (snippet) {
    return `Hi ${author}, thanks for commenting — we saw your note about "${snippet}" and will get back to you soon.`;
  }
  return `Hi ${author}, thanks for your comment! We will get back to you soon.`;
}

export const PLATFORM_IDENTITY_HINTS: Record<string, string> = {
  linkedin: "Full name + title on LinkedIn",
  instagram: "First name on Instagram",
  facebook: "First name on Facebook/Messenger",
  twitter: "First name, very short on X",
  tiktok: "Casual first name on TikTok",
  whatsapp: "First name on WhatsApp",
};
