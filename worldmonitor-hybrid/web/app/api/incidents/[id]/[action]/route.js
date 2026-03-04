import { NextResponse } from "next/server";
import { apiPost } from "../../../../lib";

export async function POST(req, { params }) {
  try {
    const body = await req.json().catch(() => ({}));
    const { id, action } = params;

    const map = {
      assign: `/incidents/${id}/assign`,
      comment: `/incidents/${id}/comment`,
      resolve: `/incidents/${id}/resolve`,
    };

    if (!map[action]) {
      return NextResponse.json({ error: "unsupported action" }, { status: 400 });
    }

    const data = await apiPost(map[action], body);
    return NextResponse.json(data);
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
