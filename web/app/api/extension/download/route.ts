import { NextResponse } from "next/server";

const BACKEND = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api").replace(/\/$/, "");

export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/extension/download`, { cache: "no-store" });

    if (!res.ok) {
      return NextResponse.json({ error: "Extension not available" }, { status: res.status });
    }

    const blob = await res.arrayBuffer();
    return new NextResponse(blob, {
      status: 200,
      headers: {
        "Content-Type": "application/zip",
        "Content-Disposition": "attachment; filename=zilo-extension.zip",
      },
    });
  } catch (err) {
    console.error("[extension/download]", err);
    return NextResponse.json({ error: "Download failed" }, { status: 500 });
  }
}
