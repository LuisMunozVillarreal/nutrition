const DEFAULT_GRAPHQL_ENDPOINT = "http://localhost:8000/graphql/";

export async function POST(request: Request) {
  const endpoint = process.env.GRAPHQL_ENDPOINT ?? DEFAULT_GRAPHQL_ENDPOINT;
  const headers = new Headers({
    "content-type": request.headers.get("content-type") ?? "application/json",
  });
  const authorization = request.headers.get("authorization");
  if (authorization) headers.set("authorization", authorization);

  try {
    const upstream = await fetch(endpoint, {
      method: "POST",
      headers,
      body: await request.text(),
      cache: "no-store",
    });

    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "content-type":
          upstream.headers.get("content-type") ?? "application/json",
      },
    });
  } catch (error) {
    console.error("Failed to proxy GraphQL request", error);
    return Response.json(
      { errors: [{ message: "GraphQL service unavailable" }] },
      { status: 502 },
    );
  }
}
