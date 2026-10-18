
import { GoogleAuth } from "google-auth-library";
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const auth = new GoogleAuth();

type RouteContext = {
    params: Promise<{ path: string[] }>;
};

async function proxyRequest(
    request: NextRequest,
    context: RouteContext
): Promise<Response> {
    const backendUrl = process.env.AURA_BACKEND_URL?.replace(/\/$/, "");

    if (!backendUrl) {
        return NextResponse.json(
            { detail: "Backend URL is not configured" },
            { status: 503 }
        );
    }

    const { path } = await context.params;

    if (!path?.length || path.some((segment) => segment === "." || segment === "..")) {
        return NextResponse.json(
            { detail: "Invalid API path" },
            { status: 400 }
        );
    }

    const backendPath =
        path.length === 1 && path[0] === "health"
            ? "/health"
            : `/api/${path.map(encodeURIComponent).join("/")}`;

    const target = new URL(backendPath, backendUrl);
    target.search = request.nextUrl.search;

    try {
        const client = await auth.getIdTokenClient(backendUrl);
        const tokenHeaders = await client.getRequestHeaders(backendUrl);
        const authorization = tokenHeaders.get("Authorization");

        if (!authorization) {
            throw new Error("Cloud Run identity token is unavailable");
        }

        const headers = new Headers({
            Authorization: authorization,
            Accept: "application/json",
        });

        const contentType = request.headers.get("content-type");
        if (contentType) {
            headers.set("Content-Type", contentType);
        }

        const ownerId = request.headers.get("x-owner-id");
        if (ownerId) {
            headers.set("X-Owner-Id", ownerId);
        }

        const response = await fetch(target, {
            method: request.method,
            headers,
            body:
                request.method === "GET" || request.method === "HEAD"
                    ? undefined
                    : await request.arrayBuffer(),
            cache: "no-store",
            signal: request.signal,
        });

        const responseHeaders = new Headers();
        const responseContentType = response.headers.get("content-type");

        if (responseContentType) {
            responseHeaders.set("Content-Type", responseContentType);
        }

        return new Response(response.body, {
            status: response.status,
            headers: responseHeaders,
        });
    } catch (error) {
        console.error("AURA backend proxy failed:", error);
        return NextResponse.json(
            { detail: "Unable to reach AURA backend" },
            { status: 502 }
        );
    }
}

export const GET = proxyRequest;
export const POST = proxyRequest;
