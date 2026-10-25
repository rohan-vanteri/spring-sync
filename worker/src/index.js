// Spring Sync AI worker (Cloudflare Workers).
//
// Holds the OpenAI key as a secret so the static site never sees it, and does
// only two jobs:
//   POST /parse    plain-English schedule -> the structured form the agents use
//   POST /narrate  rewrite an agent's texts to its own student in natural words
// The site's code still makes every decision and the gate still checks every
// message between agents. Any output that fails validation is rejected and the
// site falls back to its built-in wording.

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"];
const CAMPUSES = ["Tempe", "Polytechnic"];
const TIME = /^([01]\d|2[0-3]):[0-5]\d$/;
const MAX_PARSE_CHARS = 1200;
const MAX_ITEMS = 12;
const MAX_ITEM_CHARS = 400;
const RATE_LIMIT = { windowMs: 10 * 60 * 1000, max: 120 };

// ------------------------------------------------------------------ prompts
export const PARSE_SYSTEM = `You turn a college student's description of their week into structured data for a class-scheduling agent.
Only include what the text says or clearly implies. Never invent busy times.
- busy: blocks when the student can't have class. days from Mon Tue Wed Thu Fri; 24-hour HH:MM times; reason is a few words from their text.
- earliest: the earliest time they can start a class, if they say one (like "not before 10" or "my bus gets in at 10"); otherwise "".
- campuses: which of Tempe and Polytechnic work, if mentioned; otherwise [].
- prefer_days / prefer_mornings: only if they say they prefer them.
- gpa and other_private: only if they mention them (scholarship, probation, and similar go in other_private).`;

export const NARRATE_SYSTEM = `You rewrite short text messages that a student's personal scheduling agent sends to that student.
Make each one sound natural and friendly, like a helpful friend texting. One or two short sentences.
Rules:
- Keep every fact exactly: section IDs (like CSE340-B), days, times, names, numbers, and whether something worked or was refused.
- Keep privacy statements (for example "I didn't say why" or "I didn't share it").
- Keep questions as questions, and keep a "Test mode:" prefix if there is one.
- Never add facts, guesses, reasons, grades or anything not in the original.`;

export const PARSE_SCHEMA = {
  type: "object",
  properties: {
    busy: {
      type: "array",
      items: {
        type: "object",
        properties: {
          days: { type: "array", items: { type: "string", enum: DAYS } },
          start: { type: "string" },
          end: { type: "string" },
          reason: { type: "string" },
        },
        required: ["days", "start", "end", "reason"],
        additionalProperties: false,
      },
    },
    earliest: { type: "string" },
    campuses: { type: "array", items: { type: "string", enum: CAMPUSES } },
    prefer_days: { type: "array", items: { type: "string", enum: DAYS } },
    prefer_mornings: { type: "boolean" },
    gpa: { type: "string" },
    other_private: { type: "string" },
  },
  required: ["busy", "earliest", "campuses", "prefer_days", "prefer_mornings", "gpa", "other_private"],
  additionalProperties: false,
};

export const NARRATE_SCHEMA = {
  type: "object",
  properties: {
    messages: {
      type: "array",
      items: {
        type: "object",
        properties: { id: { type: "string" }, text: { type: "string" } },
        required: ["id", "text"],
        additionalProperties: false,
      },
    },
  },
  required: ["messages"],
  additionalProperties: false,
};

// --------------------------------------------------------------- validation
function normTime(t) {
  const v = String(t || "").trim();
  const m = v.match(/^(\d{1,2}):(\d{2})$/);
  if (!m) return null;
  const out = m[1].padStart(2, "0") + ":" + m[2];
  return TIME.test(out) ? out : null;
}

const clip = (s, n) => String(s || "").replace(/[\r\n]+/g, " ").trim().slice(0, n);

/** Model output -> the site's form fields, or throw. */
export function toForm(data) {
  if (!data || typeof data !== "object" || !Array.isArray(data.busy)) throw new Error("bad shape");
  const lines = [];
  for (const b of data.busy.slice(0, 12)) {
    const days = DAYS.filter((d) => (b.days || []).includes(d));
    const start = normTime(b.start), end = normTime(b.end);
    if (!days.length || !start || !end || start >= end) continue;
    const reason = clip(b.reason, 40).replace(/[^\w .,'&/-]/g, "");
    lines.push(`${days.join(" ")} ${start}-${end}${reason ? " " + reason : ""}`);
  }
  const earliest = normTime(data.earliest) || "";
  const campuses = CAMPUSES.filter((c) => (data.campuses || []).includes(c));
  return {
    busy: lines.join("\n"),
    earliest,
    campuses: campuses.length ? campuses : null, // null = keep what the form has
    prefer_days: DAYS.filter((d) => (data.prefer_days || []).includes(d)),
    prefer_mornings: !!data.prefer_mornings,
    gpa: clip(data.gpa, 10),
    other_private: clip(data.other_private, 60),
  };
}

const FACT_PATTERNS = [
  /\bCSE ?\d{3}(?:-[A-Z])?\b/g,     // course and section IDs
  /\b\d{1,2}:\d{2}\b/g,             // times
  /\b(?:Mon|Tue|Wed|Thu|Fri)\b/g,   // days
  /\b\d+\b/g,                       // other numbers (credits, counts)
];

function facts(text, names) {
  const out = new Set();
  for (const re of FACT_PATTERNS) for (const m of text.match(re) || []) out.add(m.replace(/ /g, ""));
  for (const n of names) if (n && text.includes(n)) out.add(n);
  return out;
}

const NEGATION = /\b(?:not|never|no|won't|can't|cannot|didn't|wouldn't|isn't|doesn't)\b|n't\b/i;

/** True when a rewrite keeps every fact, the meaning markers, and adds no numbers. */
export function keepsFacts(original, rewrite, names = []) {
  if (typeof rewrite !== "string") return false;
  const r = rewrite.trim();
  if (!r || r.length > 320) return false;
  const want = facts(original, names);
  const got = facts(r.replace(/(\bCSE) (\d{3})/g, "$1$2"), names);
  for (const f of want) if (!got.has(f) && !r.replace(/ /g, "").includes(f)) return false;
  for (const f of got) if (!want.has(f) && /\d/.test(f)) return false;       // no invented numbers
  if (NEGATION.test(original) && !NEGATION.test(r)) return false;
  if (original.trim().endsWith("?") && !r.includes("?")) return false;
  if (/^Test mode:/i.test(original) && !/^Test mode:/i.test(r)) return false;
  return true;
}

// ------------------------------------------------------------------ OpenAI
async function callModel(env, system, user, name, schema, fetchImpl = fetch) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 15000);
  try {
    const res = await fetchImpl("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      signal: ctrl.signal,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.OPENAI_API_KEY}` },
      body: JSON.stringify({
        model: env.MODEL || "gpt-6-luna",
        messages: [{ role: "system", content: system }, { role: "user", content: user }],
        response_format: { type: "json_schema", json_schema: { name, schema, strict: true } },
        max_completion_tokens: 900,
      }),
    });
    if (!res.ok) throw new Error("upstream " + res.status);
    const data = await res.json();
    const msg = data.choices && data.choices[0] && data.choices[0].message;
    if (!msg || msg.refusal || !msg.content) throw new Error("no content");
    return JSON.parse(msg.content);
  } finally {
    clearTimeout(timer);
  }
}

// ----------------------------------------------------------------- handlers
export async function handleParse(body, env, fetchImpl) {
  const text = clip(body && body.text, MAX_PARSE_CHARS);
  if (text.length < 3) return { status: 400, json: { error: "Describe your week first." } };
  const out = await callModel(env, PARSE_SYSTEM, text, "schedule", PARSE_SCHEMA, fetchImpl);
  return { status: 200, json: { form: toForm(out) } };
}

export async function handleNarrate(body, env, fetchImpl) {
  const items = Array.isArray(body && body.items) ? body.items.slice(0, MAX_ITEMS) : [];
  const names = Array.isArray(body && body.names) ? body.names.slice(0, 2).map((n) => clip(n, 20)) : [];
  const clean = items
    .filter((i) => i && typeof i.id === "string" && typeof i.text === "string")
    .map((i) => ({ id: i.id.slice(0, 40), text: i.text.slice(0, MAX_ITEM_CHARS) }));
  if (!clean.length) return { status: 200, json: { messages: [] } };
  const out = await callModel(env, NARRATE_SYSTEM, JSON.stringify({ messages: clean }), "messages",
    NARRATE_SCHEMA, fetchImpl);
  const byId = new Map((out.messages || []).map((m) => [m.id, m.text]));
  // Only rewrites that keep every fact are returned; the site keeps its own text otherwise.
  const messages = clean
    .filter((i) => keepsFacts(i.text, byId.get(i.id), names))
    .map((i) => ({ id: i.id, text: byId.get(i.id).trim() }));
  return { status: 200, json: { messages, rejected: clean.length - messages.length } };
}

// ------------------------------------------------------------- HTTP / CORS
const hits = new Map();

export function rateLimited(ip, now = Date.now()) {
  const list = (hits.get(ip) || []).filter((t) => now - t < RATE_LIMIT.windowMs);
  list.push(now);
  hits.set(ip, list);
  return list.length > RATE_LIMIT.max;
}

function corsHeaders(origin, env) {
  const allowed = String(env.ALLOWED_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean);
  const ok = allowed.includes(origin);
  return {
    ok,
    headers: {
      "Access-Control-Allow-Origin": ok ? origin : allowed[0] || "null",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400",
      Vary: "Origin",
    },
  };
}

const json = (status, obj, headers) =>
  new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json", ...headers } });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const cors = corsHeaders(request.headers.get("Origin") || "", env);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors.headers });
    if (!cors.ok) return json(403, { error: "origin not allowed" }, cors.headers);
    if (url.pathname === "/health") return json(200, { ok: !!env.OPENAI_API_KEY, model: env.MODEL || "gpt-6-luna" }, cors.headers);
    if (request.method !== "POST") return json(405, { error: "POST only" }, cors.headers);
    if (rateLimited(request.headers.get("CF-Connecting-IP") || "unknown")) {
      return json(429, { error: "Too many requests, try again in a few minutes." }, cors.headers);
    }
    let body;
    try {
      body = await request.json();
    } catch {
      return json(400, { error: "bad json" }, cors.headers);
    }
    try {
      const r = url.pathname === "/parse" ? await handleParse(body, env)
        : url.pathname === "/narrate" ? await handleNarrate(body, env)
        : { status: 404, json: { error: "not found" } };
      return json(r.status, r.json, cors.headers);
    } catch (e) {
      return json(502, { error: "AI unavailable" }, cors.headers);
    }
  },
};
