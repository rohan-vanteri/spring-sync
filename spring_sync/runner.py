"""Drive a session one step at a time and build student profiles from a form.

Used by the local server (web.py) and by the static site, which runs this same
code in the browser with Pyodide. Slot ids are always "alex" (left phone) and
"jordan" (right phone); the names shown can be anything.
"""

import re

from .data import ALEX, DEMO_PROBES, JORDAN
from .narrate import narrate
from .session import Session

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
CAMPUSES = ["Tempe", "Polytechnic"]
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
BUSY_LINE = re.compile(
    r"^\s*(?P<days>(?:(?:Mon|Tue|Wed|Thu|Fri)[\s,/]*)+)\s+"
    r"(?P<start>\d{1,2}:\d{2})\s*-\s*(?P<end>\d{1,2}:\d{2})\s*(?P<reason>.*)$", re.I)


class Runner:
    """One negotiation. `start()` and `answer(yes)` return the next batch of
    events (up to a confirmation or the end), each with what both phones say."""

    def __init__(self, a_profile=ALEX, b_profile=JORDAN, adversary=False):
        self.names = {a_profile["id"]: a_profile["name"], b_profile["id"]: b_profile["name"]}
        self.session = Session(a_profile, b_profile, adversary=DEMO_PROBES if adversary else None)
        self.gen = self.session.run()
        self.pending = None

    def _advance(self, answer=None, first=False):
        events = []
        try:
            ev = next(self.gen) if first else self.gen.send(answer)
            while True:
                events.append(ev)
                if ev["kind"] in ("confirm_request", "done"):
                    break
                ev = next(self.gen)
        except StopIteration:
            pass
        self.pending = events[-1] if events and events[-1]["kind"] == "confirm_request" else None
        for ev in events:
            ev["say"] = {sid: narrate(ev, sid, self.names) for sid in self.names}
        return events

    def start(self):
        return self._advance(first=True)

    def answer(self, yes):
        if not self.pending:
            raise ValueError("nothing to confirm")
        return self._advance(answer=bool(yes))


def _time(value, label):
    v = str(value).strip()
    if re.fullmatch(r"\d:\d{2}", v):
        v = "0" + v
    if not TIME.match(v):
        raise ValueError("%s must be a time like 09:30 (got %r)." % (label, value))
    return v


def parse_busy(text, who):
    """Lines like 'Tue Thu 16:00-21:00 shift at Target' -> busy blocks.
    The reason after the times is private and never leaves the student's agent."""
    blocks = []
    for n, line in enumerate(str(text or "").splitlines(), 1):
        if not line.strip():
            continue
        m = BUSY_LINE.match(line)
        if not m:
            raise ValueError("%s, busy line %d: write it like 'Tue Thu 16:00-21:00 reason'." % (who, n))
        days = [d.capitalize() for d in re.findall(r"Mon|Tue|Wed|Thu|Fri", m.group("days"), re.I)]
        start = _time(m.group("start"), "%s, busy line %d start" % (who, n))
        end = _time(m.group("end"), "%s, busy line %d end" % (who, n))
        if start >= end:
            raise ValueError("%s, busy line %d: the end time must be after the start." % (who, n))
        blocks.append({"days": days, "start": start, "end": end,
                       "reason": m.group("reason").strip() or "busy"})
    return blocks


def build_profile(slot, form):
    """Form fields -> agent profile. `slot` is "alex" or "jordan"."""
    if slot not in ("alex", "jordan"):
        raise ValueError("unknown slot")
    name = str(form.get("name") or "").strip()[:20]
    if not name or not re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", name):
        raise ValueError("Enter a first name for the %s phone (letters only)." % ("left" if slot == "alex" else "right"))
    campuses = [c for c in CAMPUSES if c in (form.get("campuses") or [])]
    if not campuses:
        raise ValueError("%s needs at least one campus." % name)
    busy = parse_busy(form.get("busy"), name)
    prefer_days = [d for d in DAYS if d in (form.get("prefer_days") or [])]
    private = {k: str(form.get(k) or "").strip()[:60] for k in ("gpa", "other_private") if str(form.get(k) or "").strip()}
    reasons = [b["reason"] for b in busy if b["reason"] != "busy"]
    if reasons:
        private["busy_reasons"] = reasons
    return {
        "id": slot,
        "name": name,
        "private": private,
        "busy": busy,
        "hard": {"earliest": _time(form.get("earliest") or "08:00", "%s's earliest class" % name),
                 "campuses": campuses},
        "soft": {"prefer_days": prefer_days,
                 "prefer_before": "12:00" if form.get("prefer_mornings") else None},
        "eligible": {"CSE 340": True},
    }


def profile_to_form(profile):
    """The inverse, used to prefill the form with the sample students."""
    busy_lines = ["%s %s-%s %s" % (" ".join(b["days"]), b["start"], b["end"], b.get("reason", ""))
                  for b in profile["busy"]]
    return {
        "name": profile["name"],
        "busy": "\n".join(line.strip() for line in busy_lines),
        "earliest": profile["hard"]["earliest"],
        "campuses": list(profile["hard"]["campuses"]),
        "prefer_days": list(profile["soft"].get("prefer_days") or []),
        "prefer_mornings": bool(profile["soft"].get("prefer_before")),
        "gpa": profile["private"].get("gpa", ""),
        "other_private": profile["private"].get("scholarship", profile["private"].get("academic_standing", "")),
    }


SAMPLE_FORMS = {"alex": profile_to_form(ALEX), "jordan": profile_to_form(JORDAN)}
