const apiBaseUrl = process.env.PRODUCT_FACTORY_API_URL ?? "http://127.0.0.1:8000";

type Context = { params: Promise<{ path: string[] }> };

async function proxy(request: Request, context: Context): Promise<Response> {
  const { path } = await context.params;
  const upstreamUrl = new URL(
    `/${path.map((segment) => encodeURIComponent(segment)).join("/")}`,
    apiBaseUrl,
  );
  upstreamUrl.search = new URL(request.url).search;

  const headers = new Headers();
  for (const name of [
    "accept",
    "content-type",
    "cookie",
    "idempotency-key",
    "last-event-id",
    "x-request-id",
  ]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const upstream = await fetch(upstreamUrl, {
    method: request.method,
    headers,
    body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.text(),
    cache: "no-store",
  });
  const responseHeaders = new Headers();
  for (const name of [
    "cache-control",
    "content-type",
    "set-cookie",
    "x-accel-buffering",
    "x-event-cursor",
    "x-event-stream-mode",
    "x-request-id",
  ]) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
