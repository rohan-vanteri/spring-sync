"""A student's agent. It knows its own student's schedule, constraints and
private data; it only ever sends allowlisted fields, and it never relaxes a hard
constraint on its own."""

from .gate import ALLOWED, SHAREABLE_FIELDS

FIELD_LABELS = {"gpa": "GPA", "scholarship": "scholarship", "grades": "grades",
                "academic_standing": "academic standing"}


def mins(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def hhmm(m):
    return "%02d:%02d" % (m // 60, m % 60)


def overlaps(days_a, s_a, e_a, days_b, s_b, e_b):
    return bool(set(days_a) & set(days_b)) and mins(s_a) < mins(e_b) and mins(s_b) < mins(e_a)


def pretty_section(sec):
    def t(x):
        h, m = map(int, x.split(":"))
        return "%d:%02d%s" % ((h - 1) % 12 + 1, m, "am" if h < 12 else "pm")
    return "%s (%s %s-%s)" % (sec["id"], "/".join(sec["days"]), t(sec["start"]), t(sec["end"]))


class StudentAgent:
    def __init__(self, profile, sections):
        self.p = profile
        self.id = profile["id"]
        self.sections = {s["id"]: s for s in sections}
        self.declined_by_peer = set()
        self.declined_by_me = set()
        self.proposed = set()

    # ---------------------------------------------------------- constraints
    def hard_violation(self, sec):
        """Name of the hard constraint a section breaks, or None (kept private)."""
        hard = self.p["hard"]
        if sec["campus"] not in hard["campuses"]:
            return "campus"
        if mins(sec["start"]) < mins(hard["earliest"]):
            return "earliest"
        for b in self.p["busy"]:
            if overlaps(sec["days"], sec["start"], sec["end"], b["days"], b["start"], b["end"]):
                return "busy"
        return None

    def soft_score(self, sec):
        soft = self.p["soft"]
        score = 0
        if soft.get("prefer_days") and set(sec["days"]) <= set(soft["prefer_days"]):
            score += 2
        if soft.get("prefer_before") and mins(sec["end"]) <= mins(soft["prefer_before"]):
            score += 2
        return score

    def feasible(self):
        ok = [s for s in self.sections.values() if self.hard_violation(s) is None]
        return sorted(ok, key=lambda s: (-self.soft_score(s), s["id"]))

    def next_proposal(self):
        for s in self.feasible():
            if s["id"] not in self.declined_by_peer and s["id"] not in self.proposed:
                self.proposed.add(s["id"])
                return s
        return None

    def free_blocks(self, chosen=None, start="09:00", end="21:00"):
        """One-hour blocks Mon-Fri with nothing scheduled (times only, no reasons)."""
        start = max(start, self.p["hard"].get("earliest", start))
        taken = list(self.p["busy"])
        if chosen:
            taken.append(chosen)
        blocks = []
        for day in ["Mon", "Tue", "Wed", "Thu", "Fri"]:
            for m in range(mins(start), mins(end) - 59, 60):
                s, e = hhmm(m), hhmm(m + 60)
                if not any(overlaps([day], s, e, b["days"], b["start"], b["end"]) for b in taken):
                    blocks.append({"day": day, "start": s, "end": e})
        return blocks

    # ------------------------------------------------------------- messages
    def msg(self, to, mtype, payload=None, text=""):
        return {"from": self.id, "to": to, "type": mtype, "payload": payload or {}, "text": text}

    def answer_request(self, to, field, other_name=None):
        """Reply to REQUEST_INFO. Only shareable fields; everything else is refused
        and escalated to the student."""
        if field in SHAREABLE_FIELDS:
            return self.msg(to, "REFUSE", {"field": field},
                            "That's already part of our proposals."), None
        escalation = {"kind": "escalation", "student": self.id,
                      "question": "%s asked for your %s. I didn't share it. "
                                  "Nothing to do unless you want to tell them yourself."
                                  % ("%s's agent" % other_name if other_name else "The other agent",
                                     FIELD_LABELS.get(field, field.replace("_", " ")))}
        return self.msg(to, "REFUSE", {"field": field}, "I can't share that."), escalation
