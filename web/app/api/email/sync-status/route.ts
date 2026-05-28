import { NextRequest, NextResponse } from "next/server";
import { resolveUserId } from "@/lib/nango-proxy";
import { buildInternalCrmApiUrl } from "@/lib/server-crm-api";

export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization");
  const userId = await resolveUserId(auth);
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  try {
    const res = await fetch(buildInternalCrmApiUrl("/email-db/sync-status"), {
      headers: { Authorization: auth! },
    });
    if (!res.ok) return NextResponse.json({ status: "unknown" });
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ status: "unknown" });
  }
}
