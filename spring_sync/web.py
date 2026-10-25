"""Local web demo in a Messages style: Alex and Jordan each text their own
Spring Sync agent on their own phone; the agent-to-agent channel (the gate) is
shown between them. Each student answers with Yes/No reply chips.

Usage: python -m spring_sync.web  (then open http://localhost:8765)
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .data import ALEX, DEMO_PROBES, JORDAN
from .narrate import narrate
from .session import Session

PORT = int(os.environ.get("PORT", "8765"))
PROBES = DEMO_PROBES

STATE = {"gen": None, "session": None, "pending": None}


def advance(answer=None, first=False):
    """Run the session until the next confirmation or the end; return new events."""
    gen = STATE["gen"]
    events = []
    try:
        ev = next(gen) if first else gen.send(answer)
        while True:
            events.append(ev)
            if ev["kind"] in ("confirm_request", "done"):
                break
            ev = next(gen)
    except StopIteration:
        pass
    STATE["pending"] = events[-1] if events and events[-1]["kind"] == "confirm_request" else None
    names = {"alex": ALEX["name"], "jordan": JORDAN["name"]}
    for ev in events:
        ev["say"] = {sid: narrate(ev, sid, names) for sid in names}
    return events


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        with open(os.path.join(os.path.dirname(__file__), "index.html"), "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        data = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/start":
            s = Session(ALEX, JORDAN, adversary=PROBES if data.get("adversary") else None)
            STATE.update(session=s, gen=s.run())
            self._json({"events": advance(first=True), "profiles": {
                "alex": {"name": ALEX["name"], "private": ALEX["private"]},
                "jordan": {"name": JORDAN["name"], "private": JORDAN["private"]}}})
        elif self.path == "/api/answer":
            if not STATE["pending"]:
                self._json({"error": "nothing to confirm"}, 400)
                return
            self._json({"events": advance(answer=bool(data.get("yes")))})
        else:
            self.send_error(404)

    def log_message(self, *args):
        pass


def main():
    print("Spring Sync demo on http://localhost:%d" % PORT)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
