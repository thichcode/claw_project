import { NextResponse } from "next/server";
import { apiPost } from "../../../../lib";

export async function POST(req, { params }) {
  try {
    const body = await req.json().catch(() => ({}));
    const data = await apiPost(`/alerts/${params.id}/ack`, body);
    return NextResponse.json(data);
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
