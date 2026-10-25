# Spring Sync AI worker

A small Cloudflare Worker that lets the website use AI without anyone typing a key. It holds the OpenAI key as a Cloudflare secret, so the key never reaches the browser or this repo.

It does two things, and nothing else:

| Endpoint | What it does | What stops it going wrong |
|---|---|---|
| `POST /parse` | Turns "I work Tue/Thu nights and my bus gets in at 10" into the schedule form | Strict JSON schema; days, times and campuses are checked in code; bad blocks are dropped; the student reviews the form before running |
| `POST /narrate` | Rewrites each agent's texts to its own student so they sound natural | Every section ID, day, time, name and number must survive, no new numbers may appear, refusals stay refusals and questions stay questions. Any rewrite that fails is thrown away and the original text is shown |
| `GET /health` | Lets the site know AI is available | |

The AI never decides anything. The agents' code still picks sections and study times, and the gate still checks every message between agents. Each student's texts are sent in a separate request, so one student's messages are never sent alongside the other's.

Other guardrails: requests are accepted only from `rohan-vanteri.github.io` (and localhost for testing), prompts are built on the server, inputs are size-capped, there's a per-IP rate limit, and every call has a 15-second timeout. If the worker is down, slow or out of credit, the site quietly uses its built-in wording.

## Deploy (about 5 minutes, free)

1. Create a free account at <https://dash.cloudflare.com/sign-up>.
2. In this folder, sign in and save the key. Paste the key at the prompt, never on the command line:

   ```bash
   npx wrangler@3 login
   ```

   ```bash
   npx wrangler@3 secret put OPENAI_API_KEY
   ```

3. Deploy:

   ```bash
   npx wrangler@3 deploy
   ```

   It prints a URL like `https://spring-sync-ai.<your-subdomain>.workers.dev`.
4. Put that URL in `docs/index.html` as `AI_URL_DEFAULT`, then commit and push. The site shows "✨ AI on" once it can reach the worker.

To cap spending, set a monthly budget on the OpenAI key's project. To switch models, change `MODEL` in `wrangler.toml` and deploy again.

## Test locally

```bash
npm test
```

Runs the worker's checks with a fake model (no key or network).

```bash
node dev/serve.js
```

Runs the worker on <http://localhost:8788> with a fake model. Serve the site on port 8766 (`python3 -m http.server 8766 -d ../docs`) and open <http://localhost:8766/?ai=http://localhost:8788>. Start it with `OPENAI_API_KEY` set in your environment to use the real model instead.
