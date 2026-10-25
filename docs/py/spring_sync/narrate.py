"""Turn session events into what each student's agent texts them.

Each student only hears their own side: what their agent did, what the other
agent said, and what the gate blocked. Nothing private about the other student
is ever narrated (the events don't contain it in the first place).
"""

from .agent import pretty_section
from .data import SECTIONS

_BY_ID = {s["id"]: s for secs in SECTIONS.values() for s in secs}


def _sec(sid):
    return pretty_section(_BY_ID[sid]) if sid in _BY_ID else sid


def _block(b):
    return "%s %s-%s" % (b["day"], b["start"], b["end"])


def narrate(ev, viewer, names):
    """Text `viewer`'s agent sends them for this event, or None."""
    other = next(n for k, n in names.items() if k != viewer)
    kind = ev["kind"]

    if kind == "confirm_request":
        return ev["question"] if ev["student"] == viewer else None
    if kind == "escalation":
        return "⚑ " + ev["question"] if ev["student"] == viewer else None
    if kind == "done":
        if ev["status"] != "agreed":
            return "Stopped: %s." % ev["status"]
        text = "All set: %s." % _sec(ev["section"])
        if ev.get("study_block"):
            text += " Weekly study time with %s: %s." % (other, _block(ev["study_block"]))
        return text + " You still register yourself."
    if kind == "blocked":
        a = ev["attempted"]
        if a["from"] == viewer:
            extra = [k for k in a["payload"] if k not in ("section_id", "study_block")]
            what = ("tried to slip a %s question into a proposal" % extra[0].replace("_", " ")
                    if extra else "sent something that isn't allowed")
            return "Test mode: I %s. The gate blocked it." % what
        return "🛡 %s's agent tried to send something that isn't allowed. The gate blocked it." % other
    if kind != "message":
        return None

    mine = ev["from"] == viewer
    t, p = ev["type"], ev["payload"]
    if t == "INVITE":
        return ("Asking %s's agent about taking %s together." % (other, p["course"]) if mine
                else "%s's agent wants to take %s with you next spring." % (other, p["course"]))
    if t == "CONSENT":
        return None if mine else ("%s is in. Comparing section times now. I only share section IDs "
                                  "and open hours, never why you're busy." % other)
    if t in ("PROPOSE", "COUNTER") and p.get("section_id"):
        return ("I suggested %s." % _sec(p["section_id"]) if mine
                else "%s's agent suggested %s." % (other, _sec(p["section_id"])))
    if t in ("PROPOSE", "COUNTER") and p.get("study_block"):
        return ("I suggested studying together %s." % _block(p["study_block"]) if mine
                else "%s's agent suggested studying together %s." % (other, _block(p["study_block"])))
    if t == "DECLINE":
        return ("I passed on %s: it conflicts with your schedule. I didn't say why." % p["section_id"] if mine
                else "%s's agent passed on %s." % (other, p["section_id"]))
    if t == "ACCEPT" and p.get("section_id"):
        return ("%s fits your schedule, so I said yes." % p["section_id"] if mine
                else "%s's agent accepted %s. ✅" % (other, p["section_id"]))
    if t == "ACCEPT" and p.get("study_block"):
        return ("%s works for you, so I said yes." % _block(p["study_block"]) if mine
                else "%s's agent is free then too." % other)
    if t == "CONFIRM":
        return ("You and %s both confirmed %s." % (other, p["section_id"]) if mine
                else "%s confirmed %s." % (other, p["section_id"]))
    if t == "FREE_BLOCKS":
        return ("I shared your open hours with %s's agent (times only, no details)." % other if mine
                else "Got %s's open hours." % other)
    if t == "REQUEST_INFO":
        label = {"gpa": "GPA"}.get(p["field"], p["field"].replace("_", " "))
        return "Test mode: I asked %s's agent for their %s." % (other, label) if mine else None
    if t == "REFUSE":
        return None if mine else "%s's agent wouldn't share that." % other
    if t == "CHAT":
        if mine:
            return ("Test mode: I asked %s's agent “%s”" % (other, ev["text"])) if ev.get("probe") else None
        return "%s's agent asked: “%s” I didn't answer." % (other, ev["text"]) \
            if ev.get("probe") else "%s's agent: “%s”" % (other, ev["text"])
    return None
