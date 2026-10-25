# Spring Sync

**Track 2 — Agent-to-Agent Coordination.** Two students want to take CSE 340 together next spring and study weekly. Each has a personal agent that knows their schedule, hard limits and private life. The agents negotiate a shared section and a study hour **without either student's GPA, grades, scholarship or reasons for being busy ever crossing over**.

Built by the Degree Domino team (Track 1).

## Why students need this

Finding a section with a friend today means screenshotting schedules and explaining why you can't do 9 AM or Tuesday nights. Spring Sync lets the agents compare only what's needed, so neither of you has to explain your job, your therapy appointments or your scholarship rules.

## What judges asked for, and where it is

| Ask | How Spring Sync does it |
|---|---|
| **Conflicting constraints** | Each agent has hard constraints (earliest start, campus, busy blocks) it never relaxes and soft preferences it ranks by. In the demo, Alex proposes C (it clashes with Jordan's private appointment), Jordan counters with A (it starts before Alex's private 10 AM limit), and they settle on B. Declines say only `"conflict"`, never why. |
| **What they share** | A deterministic **disclosure gate** sits between the agents (`spring_sync/gate.py`). Only allowlisted fields of the right type cross: section IDs, study times, free one-hour blocks, yes/no flags. Free text is scanned for the sender's private values, GPA-like numbers and grade talk. The gate never trusts an agent's claim that a message is safe, and logs every block. |
| **When they ask their students** | Before coordinating at all (consent), before committing to a section, and before adding a study block. Also whenever the other agent asks for something private, and whenever no option fits without breaking a hard constraint. Agents never register anyone. |

Protocol: `INVITE → CONSENT → PROPOSE/COUNTER → ACCEPT|DECLINE → CONFIRM (each student) → FREE_BLOCKS → PROPOSE study block → CONFIRM → DONE`.

## Run the demo

```bash
python3 -m spring_sync.web
```

Open http://localhost:8765. **Run negotiation** shows the normal flow; **Run with an adversarial agent** makes Jordan's side ask for Alex's GPA, ask why Alex is busy, and smuggle a `scholarship` field into a proposal. The gate column shows what passed and what was blocked. Each student confirms with Yes/No in their own column. Python 3.9+ standard library only.

## Research: does a code gate beat prompt-only privacy?

`spring_sync/eval.py` runs 10 extraction attacks (direct asks, justified asks, "my advisor said", range questions, inference via the 12-credit rule, role-play as a registrar audit agent) and 4 benign messages against Alex's agent, which answers in natural language, under three conditions:

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

`--model` picks a different model. With OpenAI, the agent is called through Chat Completions with a strict JSON schema; check that `gpt-6-luna` is in your account's model list. With Claude, it uses `claude-opus-5-5` at low effort with server-side refusal fallbacks. A full run is 42 short requests. Results and every transcript are saved to `results/`. The leak detector is rule-based, so read the transcripts before quoting numbers.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

25 tests: the negotiation reaches the only common section; the study block fits both schedules and Alex's 10 AM limit; no private value crosses; declines never give reasons; three confirmations per student; a student can say no; hard constraints are never relaxed; no common option escalates to both students; each gate rule; adversarial probes get nothing while the task still succeeds; the evaluation harness, and the OpenAI request/response path (with a fake client).

## Layout

```
spring_sync/
  data.py      synthetic students and sections (all made up)
  gate.py      disclosure gate: allowlist, type checks, private-value scan, audit log
  agent.py     one student's agent: hard/soft constraints, proposals, refusing private requests
  session.py   negotiation protocol as a generator that pauses for each student's confirmation
  eval.py      adversarial privacy evaluation (3 conditions)
  llm.py       OpenAI and Claude responders for the evaluation, plus the labeled simulated stand-in
  web.py       local demo server; index.html is the page
tests/
```

All data is synthetic. Sections are not from ASU Class Search.
