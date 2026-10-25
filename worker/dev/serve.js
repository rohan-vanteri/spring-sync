// Run the worker locally on http://localhost:8788 (or $PORT) without Cloudflare.
//   node dev/serve.js                      -> fake model (no key, no network), for testing the site
//   OPENAI_API_KEY=sk-... node dev/serve.js -> the real model
// Then open the site with ?ai=http://localhost:8788
import http from "node:http";
import worker from "../src/index.js";

const PORT = +process.env.PORT || 8788;

const env = {
  OPENAI_API_KEY: process.env.OPENAI_API_KEY || "fake",
  MODEL: process.env.MODEL || "gpt-6-luna",
  ALLOWED_ORIGINS: "http://localhost:8766,http://127.0.0.1:8766",
};

if (!process.env.OPENAI_API_KEY) {
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url, opts) => {
    if (!String(url).startsWith("https://api.openai.com/")) return realFetch(url, opts);
    const req = JSON.parse(opts.body);
    const user = req.messages[1].content;
    const content = req.response_format.json_schema.name === "messages" ? fakeNarrate(user) : fakeParse(user);
    await new Promise((r) => setTimeout(r, 400));
    return new Response(JSON.stringify({ choices: [{ message: { content: JSON.stringify(content) } }] }));
  };
  console.log("Using a fake model (set OPENAI_API_KEY to use the real one).");
}

// Fake model: friendlier openers, facts untouched, so the site's AI path can be exercised.
function fakeNarrate(user) {
  const openers = ["Quick update: ", "Heads up: ", "Okay! ", "Good news: "];
  const { messages } = JSON.parse(user);
  return {
    messages: messages.map((m, i) => ({
      id: m.id,
      text: /^Test mode:/.test(m.text) ? m.text : openers[i % openers.length] + m.text[0].toLowerCase() + m.text.slice(1),
    })),
  };
}

function fakeParse(text) {
  const t = text.toLowerCase();
  const busy = [];
  if (/work/.test(t)) busy.push({ days: ["Tue", "Thu"], start: "16:00", end: "21:00", reason: "work" });
  if (/lab/.test(t)) busy.push({ days: ["Fri"], start: "08:00", end: "12:00", reason: "lab" });
  const early = t.match(/(?:before|until|at) (\d{1,2})\b/);
  return {
    busy,
    earliest: early ? String(early[1]).padStart(2, "0") + ":00" : "",
    campuses: /poly/.test(t) ? ["Tempe", "Polytechnic"] : [],
    prefer_days: [],
    prefer_mornings: /morning/.test(t),
    gpa: "",
    other_private: /scholarship/.test(t) ? "scholarship" : "",
  };
}

http.createServer(async (req, res) => {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const request = new Request(`http://localhost:${PORT}` + req.url, {
    method: req.method,
    headers: req.headers,
    body: ["GET", "HEAD", "OPTIONS"].includes(req.method) ? undefined : Buffer.concat(chunks),
  });
  const r = await worker.fetch(request, env);
  res.writeHead(r.status, Object.fromEntries(r.headers));
  res.end(Buffer.from(await r.arrayBuffer()));
}).listen(PORT, "127.0.0.1", () => console.log(`Spring Sync AI worker on http://localhost:${PORT}`));
