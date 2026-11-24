// Worker for the restricted preview: serves the built site (dist/) and a small replies API used by
// the "Questions for review" page.
//
//   GET  /api/me        -> {email}                        who is signed in (through Cloudflare Access)
//   GET  /api/replies   -> [{id, issue, author, status, body, created_at}]
//   POST /api/replies   <- {issue, status, body}          stores one reply
//
// Every request reaches this Worker only through Cloudflare Access. The API checks that for itself
// as well: it verifies the Access token (Cf-Access-Jwt-Assertion) against the team's signing keys
// and the application audience, held as Worker secrets ACCESS_TEAM_DOMAIN and ACCESS_AUD (not in
// the repository). Without a valid token the API answers 403. For a local test only, the variable
// DEV_ALLOW_NO_ACCESS=1 (wrangler dev --var) skips the check and uses a fixed test identity.
//
// Replies live in the D1 database bound as REPLIES (schema in worker/schema.sql). They are read
// back into the project with scripts/pull_replies.sh.

const STATUSES = new Set(["answer", "partial", "dont-know", "discuss", "comment"]);
const ISSUE_RE = /^[A-Z]{2}-\d{1,3}[a-z]?$/; // FS-3, or a follow-up such as FS-3b
const MAX_BODY = 20000;

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });

let keyCache = { at: 0, keys: [] };

function b64urlToBytes(s) {
  const pad = s.length % 4 ? "=".repeat(4 - (s.length % 4)) : "";
  const bin = atob(s.replace(/-/g, "+").replace(/_/g, "/") + pad);
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

async function signingKeys(team) {
  if (Date.now() - keyCache.at < 3600_000 && keyCache.keys.length) return keyCache.keys;
  const r = await fetch(`https://${team}/cdn-cgi/access/certs`);
  if (!r.ok) throw new Error(`Access certs: ${r.status}`);
  keyCache = { at: Date.now(), keys: (await r.json()).keys || [] };
  return keyCache.keys;
}

// Returns the signed-in email, or null.
async function accessEmail(request, env) {
  if (env.DEV_ALLOW_NO_ACCESS === "1") return "local-test@example.invalid";
  const token = request.headers.get("cf-access-jwt-assertion");
  if (!token || !env.ACCESS_TEAM_DOMAIN || !env.ACCESS_AUD) return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const header = JSON.parse(new TextDecoder().decode(b64urlToBytes(parts[0])));
    const payload = JSON.parse(new TextDecoder().decode(b64urlToBytes(parts[1])));
    const jwk = (await signingKeys(env.ACCESS_TEAM_DOMAIN)).find((k) => k.kid === header.kid);
    if (!jwk || header.alg !== "RS256") return null;
    const key = await crypto.subtle.importKey(
      "jwk",
      jwk,
      { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
      false,
      ["verify"],
    );
    const ok = await crypto.subtle.verify(
      "RSASSA-PKCS1-v1_5",
      key,
      b64urlToBytes(parts[2]),
      new TextEncoder().encode(`${parts[0]}.${parts[1]}`),
    );
    const aud = Array.isArray(payload.aud) ? payload.aud : [payload.aud];
    const now = Math.floor(Date.now() / 1000);
    if (!ok || !aud.includes(env.ACCESS_AUD) || !(payload.exp > now)) return null;
    if (payload.iss !== `https://${env.ACCESS_TEAM_DOMAIN}`) return null;
    return typeof payload.email === "string" ? payload.email.toLowerCase() : null;
  } catch {
    return null;
  }
}

async function api(request, env, url) {
  const email = await accessEmail(request, env);
  if (!email) return json({ error: "not signed in through Cloudflare Access" }, 403);

  if (url.pathname === "/api/me" && request.method === "GET") return json({ email });

  if (url.pathname === "/api/replies" && request.method === "GET") {
    const { results } = await env.REPLIES.prepare(
      "SELECT id, issue, author, status, body, created_at FROM replies ORDER BY id",
    ).all();
    return json(results);
  }

  if (url.pathname === "/api/replies" && request.method === "POST") {
    // same-origin only: a form on another site cannot post here with the reviewer's login
    const origin = request.headers.get("origin");
    if (origin && origin !== url.origin) return json({ error: "cross-origin request refused" }, 403);
    let data;
    try {
      data = await request.json();
    } catch {
      return json({ error: "expected JSON" }, 400);
    }
    const issue = String(data.issue || "");
    const status = String(data.status || "comment");
    const body = String(data.body || "").trim();
    if (!ISSUE_RE.test(issue)) return json({ error: "unknown question number" }, 400);
    if (!STATUSES.has(status)) return json({ error: "unknown status" }, 400);
    if (!body || body.length > MAX_BODY) return json({ error: "reply is empty or too long" }, 400);
    const row = await env.REPLIES.prepare(
      "INSERT INTO replies (issue, author, status, body) VALUES (?1, ?2, ?3, ?4) " +
        "RETURNING id, issue, author, status, body, created_at",
    )
      .bind(issue, email, status, body)
      .first();
    return json(row, 201);
  }

  return json({ error: "not found" }, 404);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/api/")) return api(request, env, url);
    return env.ASSETS.fetch(request);
  },
};
