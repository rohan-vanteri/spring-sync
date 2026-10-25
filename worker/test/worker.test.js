// node --test test/   (no key or network needed: OpenAI is stubbed)
import test from "node:test";
import assert from "node:assert/strict";
import worker, { toForm, keepsFacts, handleParse, handleNarrate, rateLimited } from "../src/index.js";

const ENV = { OPENAI_API_KEY: "test", MODEL: "m", ALLOWED_ORIGINS: "https://rohan-vanteri.github.io" };

function stubModel(content) {
  return async () => ({
    ok: true,
    json: async () => ({ choices: [{ message: { content: JSON.stringify(content) } }] }),
  });
}

test("toForm turns model output into form fields and drops bad blocks", () => {
  const f = toForm({
    busy: [
      { days: ["Tue", "Thu"], start: "16:00", end: "21:00", reason: "work at Target" },
      { days: ["Sat"], start: "09:00", end: "12:00", reason: "weekend" },  // no valid day
      { days: ["Mon"], start: "14:00", end: "13:00", reason: "backwards" }, // end before start
      { days: ["Wed"], start: "9:00", end: "10:30", reason: "<script>x" },
    ],
    earliest: "10:00",
    campuses: ["Tempe", "Mars"],
    prefer_days: ["Mon", "Sun"],
    prefer_mornings: false,
    gpa: "",
    other_private: "on scholarship",
  });
  assert.equal(f.busy, "Tue Thu 16:00-21:00 work at Target\nWed 09:00-10:30 scriptx");
  assert.equal(f.earliest, "10:00");
  assert.deepEqual(f.campuses, ["Tempe"]);
  assert.deepEqual(f.prefer_days, ["Mon"]);
  assert.equal(f.other_private, "on scholarship");
});

test("toForm leaves campuses alone when none are mentioned", () => {
  const f = toForm({ busy: [], earliest: "", campuses: [], prefer_days: [], prefer_mornings: true, gpa: "", other_private: "" });
  assert.equal(f.campuses, null);
  assert.equal(f.prefer_mornings, true);
});

test("toForm rejects the wrong shape", () => {
  assert.throws(() => toForm({ nope: 1 }));
});

const ORIG = "I proposed CSE340-B (Mon Wed 12:00-13:15) to Jordan. I didn't say why.";

test("keepsFacts accepts a faithful rewrite", () => {
  assert.ok(keepsFacts(ORIG, "Sent Jordan CSE340-B for Mon Wed 12:00-13:15 and didn't mention why.", ["Alex", "Jordan"]));
});

test("keepsFacts rejects a dropped section, time, day or name", () => {
  const n = ["Alex", "Jordan"];
  assert.ok(!keepsFacts(ORIG, "Sent Jordan a CSE340 option for Mon Wed 12:00-13:15, didn't say why.", n));
  assert.ok(!keepsFacts(ORIG, "Sent Jordan CSE340-B for Mon Wed at noon, didn't say why.", n));
  assert.ok(!keepsFacts(ORIG, "Sent Jordan CSE340-B for Mon 12:00-13:15, didn't say why.", n));
  assert.ok(!keepsFacts(ORIG, "Sent your friend CSE340-B for Mon Wed 12:00-13:15, didn't say why.", n));
});

test("keepsFacts rejects invented numbers, flipped meaning and lost questions", () => {
  assert.ok(!keepsFacts(ORIG, "Sent Jordan CSE340-B for Mon Wed 12:00-13:15 in room 204, didn't say why.", ["Jordan"]));
  assert.ok(!keepsFacts("Jordan declined CSE340-B. I didn't share why.", "Jordan declined CSE340-B and I shared why.", ["Jordan"]));
  assert.ok(!keepsFacts("Want me to lock in CSE340-B?", "I'll lock in CSE340-B.", []));
  assert.ok(!keepsFacts("Test mode: I asked Alex's agent for their GPA.", "I asked Alex's agent for their GPA.", ["Alex"]));
  assert.ok(!keepsFacts(ORIG, undefined, []));
  assert.ok(!keepsFacts(ORIG, "x".repeat(400), []));
});

test("handleParse calls the model with the server's prompt and validates output", async () => {
  let sent;
  const fetchImpl = async (url, opts) => {
    sent = JSON.parse(opts.body);
    return stubModel({ busy: [{ days: ["Fri"], start: "08:00", end: "12:00", reason: "lab" }], earliest: "",
      campuses: [], prefer_days: [], prefer_mornings: false, gpa: "", other_private: "" })();
  };
  const r = await handleParse({ text: "Friday mornings I'm at lab until noon" }, ENV, fetchImpl);
  assert.equal(r.status, 200);
  assert.equal(r.json.form.busy, "Fri 08:00-12:00 lab");
  assert.equal(sent.messages[0].role, "system");
  assert.equal(sent.messages[1].content, "Friday mornings I'm at lab until noon");
  assert.equal(sent.response_format.json_schema.strict, true);
});

test("handleParse refuses empty input without calling the model", async () => {
  const r = await handleParse({ text: " " }, ENV, () => assert.fail("should not call"));
  assert.equal(r.status, 400);
});

test("handleNarrate only returns rewrites that keep the facts", async () => {
  const items = [
    { id: "a", text: ORIG },
    { id: "b", text: "Want me to lock in CSE340-B?" },
  ];
  const fetchImpl = stubModel({ messages: [
    { id: "a", text: "Sent Jordan CSE340-B for Mon Wed 12:00-13:15 and didn't say why." },
    { id: "b", text: "Locking in CSE340-B now." },  // lost the question: rejected
  ] });
  const r = await handleNarrate({ items, names: ["Alex", "Jordan"] }, ENV, fetchImpl);
  assert.deepEqual(r.json.messages.map((m) => m.id), ["a"]);
  assert.equal(r.json.rejected, 1);
});

test("rate limit kicks in after the cap", () => {
  const t = 1_000_000;
  let blocked = false;
  for (let i = 0; i < 121; i++) blocked = rateLimited("1.2.3.4", t + i);
  assert.ok(blocked);
  assert.ok(!rateLimited("5.6.7.8", t));
});

test("fetch handler: CORS, health, origin check, bad json", async () => {
  const ok = { Origin: "https://rohan-vanteri.github.io" };
  let r = await worker.fetch(new Request("https://w.dev/health", { headers: ok }), ENV);
  assert.equal(r.status, 200);
  assert.equal(r.headers.get("Access-Control-Allow-Origin"), ok.Origin);
  assert.deepEqual(await r.json(), { ok: true, model: "m" });

  r = await worker.fetch(new Request("https://w.dev/health", { headers: { Origin: "https://evil.example" } }), ENV);
  assert.equal(r.status, 403);

  r = await worker.fetch(new Request("https://w.dev/parse", { method: "POST", headers: ok, body: "{" }), ENV);
  assert.equal(r.status, 400);

  r = await worker.fetch(new Request("https://w.dev/parse", { method: "OPTIONS", headers: ok }), ENV);
  assert.equal(r.status, 204);
});
