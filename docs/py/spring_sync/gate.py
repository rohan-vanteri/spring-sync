"""Deterministic disclosure gate between two students' agents.

Every message crosses the gate. Only allowlisted fields of the right type pass;
free text is scanned for the sender's private values. The gate never trusts an
agent's own claim that a message is safe. Every blocked attempt is logged.
"""
import re

DAYS = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# What may cross, per message type.
ALLOWED = {
    "INVITE": {"task", "course"},
    "CONSENT": {"agree"},
    "PROPOSE": {"section_id", "study_block"},
    "COUNTER": {"section_id", "study_block"},
    "ACCEPT": {"section_id", "study_block"},
    "DECLINE": {"section_id", "study_block", "reason_code"},
    "FREE_BLOCKS": {"blocks"},
    "ELIGIBLE": {"course", "eligible"},
    "REQUEST_INFO": {"field"},
    "REFUSE": {"field"},
    "CONFIRM": {"section_id", "study_block"},
    "DONE": {"section_id", "study_block"},
    "CHAT": set(),               # text only, scanned
}
TASKS = {"shared_section", "study_block"}
REASON_CODES = {"conflict", "not_available", "preference"}
SHAREABLE_FIELDS = {"section_id", "study_block", "blocks", "eligible", "course"}
GPA_LIKE = re.compile(r"\b[0-4]\.\d{1,2}\b")
GRADE_LIKE = re.compile(r"\b[A-F][+-]?(?=\s|$|[.,;!?)])")


def _block_ok(b):
    return (isinstance(b, dict) and set(b) == {"day", "start", "end"} and b["day"] in DAYS
            and isinstance(b["start"], str) and isinstance(b["end"], str)
            and TIME.match(b["start"]) and TIME.match(b["end"]) and b["start"] < b["end"])


def _value_ok(key, value):
    if key == "task":
        return value in TASKS
    if key in ("course", "section_id", "field"):
        return isinstance(value, str) and len(value) <= 24 and re.fullmatch(r"[A-Za-z0-9 _-]+", value)
    if key in ("agree", "eligible"):
        return isinstance(value, bool)
    if key == "reason_code":
        return value in REASON_CODES
    if key == "study_block":
        return value is None or _block_ok(value)
    if key == "blocks":
        return isinstance(value, list) and len(value) <= 40 and all(_block_ok(b) for b in value)
    return False


def private_terms(profile):
    """Strings from the sender's private data that must never appear in text."""
    terms = []
    for key, value in profile.get("private", {}).items():
        if isinstance(value, str):
            terms.append(value)
        elif isinstance(value, list):
            terms.extend(v for v in value if isinstance(v, str))
        elif isinstance(value, dict):
            terms.extend(str(v) for v in value.values())
    for b in profile.get("busy", []):
        if b.get("reason"):
            terms.append(b["reason"])
    return [t for t in terms if t]


class Gate:
    """Filters messages from one agent to another and keeps an audit log."""

    def __init__(self, monitor=None):
        self.log = []
        self.monitor = monitor       # optional: flags suspicious incoming requests

    def _blocked(self, msg, why):
        entry = {"from": msg.get("from"), "to": msg.get("to"), "type": msg.get("type"), "reason": why}
        self.log.append(entry)
        return None, entry

    def check(self, msg, sender_profile):
        """Return (message_to_deliver or None, block_entry or None)."""
        mtype = msg.get("type")
        if mtype not in ALLOWED:
            return self._blocked(msg, "unknown message type %r" % mtype)
        payload = msg.get("payload") or {}
        if not isinstance(payload, dict):
            return self._blocked(msg, "payload is not an object")
        extra = set(payload) - ALLOWED[mtype]
        if extra:
            return self._blocked(msg, "fields not on the allowlist: %s" % ", ".join(sorted(extra)))
        for key, value in payload.items():
            if not _value_ok(key, value):
                return self._blocked(msg, "field %r failed its type check" % key)
        text = msg.get("text") or ""
        if len(text) > 400:
            return self._blocked(msg, "text too long")
        lower = text.lower()
        for term in private_terms(sender_profile):
            # Whole-word match; 1-2 character values (letter grades) are covered
            # by the grade check below instead, so "CSE340-C" isn't a leak.
            if len(term) > 2 and re.search(r"(?<!\w)%s(?!\w)" % re.escape(term.lower()), lower):
                return self._blocked(msg, "text contains a private value")
        if GPA_LIKE.search(text):
            return self._blocked(msg, "text contains a GPA-like number")
        if GRADE_LIKE.search(text) and "grade" in lower:
            return self._blocked(msg, "text discusses a letter grade")
        clean = {"from": msg["from"], "to": msg["to"], "type": mtype, "payload": dict(payload), "text": text}
        return clean, None
