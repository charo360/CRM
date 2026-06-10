import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const token = req.headers.get("authorization") ?? "";
  const { searchParams } = new URL(req.url);
  const path = searchParams.get("_path") ?? "products";
  searchParams.delete("_path");

  const backendUrl = `${process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api"}/ae/${path}?${searchParams.toString()}`;
  const res = await fetch(backendUrl, { headers: { Authorization: token } });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
