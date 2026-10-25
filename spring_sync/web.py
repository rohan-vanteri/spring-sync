"""Local web demo in a Messages style: Alex and Jordan each text their own
Spring Sync agent on their own phone; the agent-to-agent channel (the gate) is
shown between them. Each student answers with Yes/No reply chips.

Usage: python -m spring_sync.web  (then open http://localhost:8765)
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .data import ALEX, JORDAN
from .runner import Runner

PORT = int(os.environ.get("PORT", "8765"))

STATE = {"runner": None}


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
            STATE["runner"] = Runner(ALEX, JORDAN, adversary=bool(data.get("adversary")))
            self._json({"events": STATE["runner"].start(), "profiles": {
                "alex": {"name": ALEX["name"], "private": ALEX["private"]},
                "jordan": {"name": JORDAN["name"], "private": JORDAN["private"]}}})
        elif self.path == "/api/answer":
            runner = STATE["runner"]
            if not runner or not runner.pending:
                self._json({"error": "nothing to confirm"}, 400)
                return
            self._json({"events": runner.answer(data.get("yes"))})
        else:
            self.send_error(404)

    def log_message(self, *args):
        pass


def main():
    print("Spring Sync demo on http://localhost:%d" % PORT)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
