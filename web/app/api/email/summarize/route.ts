import { NextRequest, NextResponse } from "next/server";
import { resolveUserId } from "@/lib/nango-proxy";

const BACKEND = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export async function POST(req: NextRequest) {
  const auth = req.headers.get("authorization");
  const userId = await resolveUserId(auth);
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json() as {
    subject: string;
    messages: { from: string; date: string; body: string }[];
  };

  if (!body.messages?.length) return NextResponse.json({ summary: null });

  const thread = body.messages
    .slice(-10) // last 10 messages max
    .map((m, i) => `[${i + 1}] From: ${m.from}\n${m.body.slice(0, 400)}`)
    .join("\n\n---\n\n");

  const prompt = [
    `Summarize this email thread in 3 short bullet points (max 15 words each).`,
    `Focus on: what was requested, what was agreed or decided, what's pending.`,
    `Subject: ${body.subject}`,
    ``,
    thread,
    ``,
    `Format: start each bullet with "• ". No intro, no conclusion. Just the 3 bullets.`,
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

    if (!res.ok) return NextResponse.json({ summary: null });

    const data = await res.json() as { reply?: string; draft?: string; text?: string };
    const summary = (data.reply ?? data.draft ?? data.text ?? "").trim();
    return NextResponse.json({ summary: summary || null });
  } catch {
    return NextResponse.json({ summary: null });
  }
}
