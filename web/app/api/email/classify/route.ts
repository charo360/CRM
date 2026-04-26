import { NextRequest, NextResponse } from "next/server";
import { resolveUserId } from "@/lib/nango-proxy";

const BACKEND = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export async function POST(req: NextRequest) {
  const auth = req.headers.get("authorization");
  const userId = await resolveUserId(auth);
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json() as {
    subject: string;
    from: string;
    snippet: string;
    categories: { id: string; name: string; description?: string }[];
  };

  if (!body.categories?.length) return NextResponse.json({ categoryId: null });

  const categoryList = body.categories
    .map((c) => `- ID: ${c.id} | Name: "${c.name}"${c.description ? ` | Hint: ${c.description}` : ""}`)
    .join("\n");

  const prompt = [
    "You are an email classifier for a CRM inbox. Given the email details below, determine which category it belongs to.",
    "",
    `From: ${body.from}`,
    `Subject: ${body.subject}`,
    `Preview: ${body.snippet?.slice(0, 300) ?? ""}`,
    "",
    "Available categories:",
    categoryList,
    "",
    "Respond with ONLY the exact category ID from the list above (the value after 'ID: ').",
    "If the email does not clearly fit any category, respond with: none",
    "No explanation. Just the ID or 'none'.",
  ].join("\n");

  try {
    const res = await fetch(`${BACKEND}/assistant/ai-draft`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(auth ? { Authorization: auth } : {}),
      },
      body: JSON.stringify({ prompt }),
    });

    if (!res.ok) return NextResponse.json({ categoryId: null });

    const data = await res.json() as { reply?: string; draft?: string; text?: string };
    const result = (data.reply ?? data.draft ?? data.text ?? "").trim();

    if (!result || result.toLowerCase() === "none") return NextResponse.json({ categoryId: null });

    // Validate the returned ID is actually one of our categories
    const valid = body.categories.find((c) => c.id === result);
    return NextResponse.json({ categoryId: valid ? result : null });
  } catch {
    return NextResponse.json({ categoryId: null });
  }
}
