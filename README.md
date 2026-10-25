# Spring Sync

**Sync your spring schedule, not your secrets.** Cubbie Hackathon, Track 2 (Agent-to-Agent Coordination), by the Degree Domino team.

Two students want to take CSE 340 together next spring and study weekly. Each has a personal agent that knows their schedule, hard limits and private life. The agents negotiate a shared section and a study hour **without either student's GPA, grades, scholarship or reasons for being busy ever crossing over**.

## For judges

### Try it (no install)
The site in [`docs/`](docs/index.html) runs the real engine (the same `spring_sync/` gate, agents and protocol) in your browser with [Pyodide](https://pyodide.org). Type your own two schedules or use the sample students, then click **Run negotiation** or **Run with an adversarial agent** and answer each student's Yes/No on their own phone. Nothing you type leaves the page.

To run it locally: `python3 -m http.server -d docs` and open http://localhost:8000. Once GitHub Pages is enabled for the `docs/` folder it is at **https://rohan-vanteri.github.io/spring-sync/**.

### Watch it (70 s)
[Demo video](docs/media/spring-sync-demo.mp4): one real run with both phones side by side and the gate log underneath, including an agent that tries to pull out a GPA and smuggle in a scholarship field.

### The three things Track 2 asks to see

| Ask | How Spring Sync does it |
|---|---|
| **Conflicting constraints** | Each agent has hard constraints (earliest start, campus, busy blocks) it never relaxes, and soft preferences it ranks by. With the sample students, Alex proposes C (it clashes with Jordan's private appointment), Jordan counters with A (it starts before Alex's private 10 AM limit), and they settle on B. Declines say only `"conflict"`, never why. If nothing fits, both students are told instead of a constraint being broken. |
| **What they share** | A deterministic **disclosure gate** sits between the agents (`spring_sync/gate.py`). Only allowlisted fields of the right type cross: section IDs, study times, free one-hour blocks, yes/no flags. Free text is scanned for the sender's private values, GPA-like numbers and grade talk. The gate never trusts an agent's claim that a message is safe, and logs every block. |
| **When they ask their students** | Before coordinating at all (consent), before committing to a section, and before adding a study block, each on the student's own phone. Also whenever the other agent asks for something private, and whenever no option fits. Agents never register anyone. |

Protocol: `INVITE → CONSENT → PROPOSE/COUNTER → ACCEPT|DECLINE → CONFIRM (each student) → FREE_BLOCKS → PROPOSE study block → CONFIRM → DONE`.

### Results: a real model against 14 extraction attacks

We tested whether the gate is needed when the agent is a real model told to keep things private. OpenAI `gpt-6-luna` played Alex's agent against 10 single-message attacks (direct, "my advisor said", above/below-3.0, a fake registrar audit, and more) and 4 multi-turn attacks that build rapport before probing, plus 4 harmless scheduling questions. Full transcripts: [`eval_results/`](eval_results/).

| Condition | Leaks | Multi-turn leaks | Harmless questions answered | Gate blocks | Sent to the student |
|---|---|---|---|---|---|
| Prompt-only privacy | 0 / 14 | 0 / 4 | 4 / 4 | – | – |
| Code gate | 0 / 14 | 0 / 4 | 4 / 4 | 0 | – |
| Gate + monitor | 0 / 14 | 0 / 4 | 4 / 4 | 0 | 12 (precision 1.00, recall 0.86) |

What this shows, honestly:
- **A strong model already resisted these attacks on its own.** The gate did not reduce leaks in this run because there were none to stop. Its value is that it holds without depending on the model: for a weaker, misconfigured or manipulated agent, the code still refuses to let a private field cross (see the adversarial demo and `tests/`).
- **The gate costs nothing once the agent knows the allowed fields.** In our first run the agent invented field names like `free_time`, and the gate wrongly blocked 5 harmless replies (2/4 answered). After we gave the agent the exact field names, false blocks went to 0 and all harmless questions were answered ([first run](eval_results/gpt-6-luna_2026-10-24_first-run.json)).
- **The keyword monitor is cautious:** it caught 12 of 14 attacks with no false alarms, and missed the two indirectly worded multi-turn probes, which the model refused anyway.
- Limits: one model, 18 scenarios, a rule-based leak detector (we read every transcript), synthetic students.

## Why students need this

Finding a section with a friend today means screenshotting schedules and explaining why you can't do 9 AM or Tuesday nights. Spring Sync lets the agents compare only what's needed, so neither of you has to explain your job, your therapy appointments or your scholarship rules.

## Run the demo with a local server

```bash
python3 -m spring_sync.web
```

Open http://localhost:8765. It shows two phones in a Messages style: Alex and Jordan each text their own Spring Sync agent, and only see their own side. The agent texts what it's doing in plain language ("I passed on CSE340-C: it conflicts with your schedule. I didn't say why."), and each student answers with Yes/No reply chips. Between the phones, the agent-to-agent channel shows every message that passed the gate and every one it blocked.

**Run negotiation** shows the normal flow; **Run with an adversarial agent** makes Jordan's agent ask for Alex's GPA, ask why Alex is busy, and smuggle a `scholarship` field into a proposal. Alex's phone shows the GPA request refused, the question unanswered and the smuggled field blocked. Python 3.9+ standard library only.

## Research: does a code gate beat prompt-only privacy?

`spring_sync/eval.py` runs 10 single-message extraction attacks (direct asks, justified asks, "my advisor said", range questions, inference via the 12-credit rule, role-play as a registrar audit agent), 4 multi-turn attacks that build rapport before probing, and 4 benign messages against Alex's agent, which answers in natural language, under three conditions:

1. **prompt-only**: privacy is only in the agent's instructions
2. **gate**: replies pass through the disclosure gate
3. **gate + monitor**: a monitor screens incoming messages first and escalates suspicious ones to the student

Metrics: leak rate (exact values, GPA-like numbers, ranges, yes/no inference on scholarship), benign questions still answered, gate blocks, escalations, and monitor precision/recall. Every transcript is saved.

```bash
# OpenAI (default): gpt-6-luna
pip install openai
export OPENAI_API_KEY=...
python3 -m spring_sync.eval --llm

# Claude instead
pip install anthropic
python3 -m spring_sync.eval --llm --provider anthropic

# Harness self-test with a scripted stand-in (no key; not a measurement)
python3 -m spring_sync.eval --simulate
```

`--model` picks a different model. With OpenAI, the agent is called through Chat Completions with a strict JSON schema; check that `gpt-6-luna` is in your account's model list. With Claude, it uses `claude-opus-5-5` at low effort with server-side refusal fallbacks. A full run is about 60 short requests. The agent is told the exact field names it may share (`section_id`, `free_blocks`, `eligible`); under the gate each shared field travels in its protocol message and is checked on its own, and if any part of a reply is blocked, none of it is delivered. Results and every transcript are saved to `results/`. The leak detector is rule-based, so read the transcripts before quoting numbers.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

53 tests: the negotiation reaches the only common section; the study block fits both schedules and Alex's 10 AM limit; no private value crosses; declines never give reasons; three confirmations per student; a student can say no; hard constraints are never relaxed; no common option escalates to both students; each gate rule; adversarial probes get nothing while the task still succeeds; the evaluation harness, the OpenAI request/response path (with a fake client), the per-student messages (each side hears only its own story; the other student's private data is never narrated), and the browser site (its engine copy matches `spring_sync/`, custom schedules negotiate without leaking, and bad form input gets a readable error).

The AI worker has its own tests (`cd worker && npm test`, no key needed): schedule parsing is validated, and AI rewrites that drop or change a section, time, day, name or refusal are rejected.

## Layout

```
spring_sync/
  data.py      synthetic students and sections (all made up)
  gate.py      disclosure gate: allowlist, type checks, private-value scan, audit log
  agent.py     one student's agent: hard/soft constraints, proposals, refusing private requests
  session.py   negotiation protocol as a generator that pauses for each student's confirmation
  eval.py      adversarial privacy evaluation (3 conditions)
  llm.py       OpenAI and Claude responders for the evaluation, plus the labeled simulated stand-in
  narrate.py   turns protocol events into what each student's agent texts them
  runner.py    drives a session step by step and builds students from the schedule form
  web.py       local demo server; index.html is the Messages-style page
tests/
docs/          static site: runs the engine in the browser (Pyodide); docs/py is copied by tools/build_site.py
eval_results/  saved transcripts from the gpt-6-luna runs
worker/        Cloudflare Worker that lets the site use AI without a key in the browser (see worker/README.md)
```

All data is synthetic. Sections are not from ASU Class Search.
