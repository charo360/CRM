import { NextRequest, NextResponse } from "next/server";
import { resolveUserId } from "@/lib/nango-proxy";

const BACKEND = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export async function POST(req: NextRequest) {
  const auth = req.headers.get("authorization");
  const userId = await resolveUserId(auth);
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json() as {
    threadSubject?: string;
    latestMessage?: string;    // plain text of the message to reply to
    senderName?: string;
    tone?: "professional" | "friendly" | "concise";
    extraContext?: string;
  };

  const tone = body.tone ?? "professional";
  const prompt = [
    `You are a helpful email assistant. Draft a ${tone} reply to the email below.`,
    body.threadSubject ? `Subject: ${body.threadSubject}` : "",
    body.senderName   ? `From: ${body.senderName}` : "",
    "",
    "--- Original message ---",
    body.latestMessage ?? "(no message content provided)",
    "------------------------",
    body.extraContext ? `Additional context from the owner: ${body.extraContext}` : "",
    "",
    "Write ONLY the reply body (no greeting header, no signature). Keep it under 150 words unless detail is clearly needed.",
  ].filter(Boolean).join("\n");

  try {
    // Use the backend's assistant AI for the draft
    const res = await fetch(`${BACKEND}/assistant/ai-draft`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(auth ? { Authorization: auth } : {}),
      },
      body: JSON.stringify({ prompt }),
    });

    if (!res.ok) {
      // Fallback: simple template draft
      return NextResponse.json({
        draft: `Thank you for your email. I will look into this and get back to you shortly.\n\nBest regards`,
      });
    }

    const data = await res.json() as { reply?: string; draft?: string; text?: string };
    const draft = data.reply ?? data.draft ?? data.text ?? "";
    return NextResponse.json({ draft });
  } catch {
    return NextResponse.json({
      draft: `Thank you for reaching out. I will review your message and respond as soon as possible.\n\nBest regards`,
    });
  }
}
