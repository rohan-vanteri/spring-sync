"""Negotiation session between two student agents.

Protocol: INVITE -> CONSENT -> (PROPOSE/COUNTER -> ACCEPT|DECLINE)* -> CONFIRM
(each student) -> FREE_BLOCKS -> PROPOSE study block -> CONFIRM -> DONE.

`run()` is a generator of events. When a student must decide, it yields an
event with kind "confirm_request" and waits for `.send(True/False)`.
"""

from .agent import StudentAgent, pretty_section, overlaps
from .data import SECTIONS
from .gate import Gate

MAX_ROUNDS = 8


class Session:
    def __init__(self, a_profile, b_profile, course="CSE 340", gate=None, adversary=None):
        self.course = course
        self.a = StudentAgent(a_profile, SECTIONS[course])
        self.b = StudentAgent(b_profile, SECTIONS[course])
        self.profiles = {a_profile["id"]: a_profile, b_profile["id"]: b_profile}
        self.agents = {self.a.id: self.a, self.b.id: self.b}
        self.gate = gate or Gate()
        self.adversary = adversary          # optional list of probe messages from B
        self.result = {"section": None, "study_block": None, "status": "running"}

    # Every message goes through the gate; blocked ones never arrive.
    def send(self, msg):
        delivered, blocked = self.gate.check(msg, self.profiles[msg["from"]])
        if blocked:
            return None, {"kind": "blocked", **blocked, "attempted": msg}
        return delivered, {"kind": "message", **delivered}

    def run(self):
        for ev in self._run():
            reply = yield ev
            if ev["kind"] == "confirm_request":
                self._answer = reply
            if ev["kind"] == "blocked" and not ev.get("probe"):
                self.result["status"] = "stopped: gate blocked a protocol message"
                yield {"kind": "done", **self.result}
                return

    def _ask(self, ev):
        self._answer = None
        return ev

    def _run(self):
        A, B = self.a, self.b
        names = {A.id: A.p["name"], B.id: B.p["name"]}

        # 1. Invite and consent (each student agrees to coordinate).
        _, ev = self.send(A.msg(B.id, "INVITE", {"task": "shared_section", "course": self.course},
                                "Want to take %s together in spring?" % self.course))
        yield ev
        for agent in (A, B):
            yield {"kind": "confirm_request", "student": agent.id,
                        "question": "Coordinate a %s section%s with %s? Only section times "
                                    "and free blocks are shared." % (
                                        self.course, "" if agent is A else "",
                                        names[B.id] if agent is A else names[A.id])}
            if not self._answer:
                self.result["status"] = "declined by %s" % names[agent.id]
                yield {"kind": "done", **self.result}
                return
        _, ev = self.send(B.msg(A.id, "CONSENT", {"agree": True}, "Sure, let's find one."))
        yield ev

        # Optional adversarial probes from B's side (used by the demo and eval).
        for probe in self.adversary or []:
            delivered, ev = self.send({"from": B.id, "to": A.id, **probe})
            ev["probe"] = True
            yield ev
            if delivered and delivered["type"] == "REQUEST_INFO":
                reply, esc = A.answer_request(B.id, delivered["payload"]["field"])
                if esc:
                    yield esc
                _, ev = self.send(reply)
                yield ev
            elif delivered and delivered["type"] == "CHAT":
                _, ev = self.send(A.msg(B.id, "CHAT", {}, "Let's stick to section times."))
                yield ev

        # 2. Alternate proposals until one is acceptable to both.
        proposer, responder = A, B
        agreed = None
        for _ in range(MAX_ROUNDS):
            sec = proposer.next_proposal()
            if sec is None:
                proposer, responder = responder, proposer
                sec = proposer.next_proposal()
                if sec is None:
                    break
            mtype = "PROPOSE" if not (proposer.proposed - {sec["id"]}) and proposer is A else "COUNTER"
            _, ev = self.send(proposer.msg(responder.id, mtype, {"section_id": sec["id"]},
                                           "How about %s?" % pretty_section(sec)))
            yield ev
            if responder.hard_violation(sec) is None:
                _, ev = self.send(responder.msg(proposer.id, "ACCEPT", {"section_id": sec["id"]},
                                                "%s works for me." % sec["id"]))
                yield ev
                agreed = sec
                break
            responder.declined_by_me.add(sec["id"])
            proposer.declined_by_peer.add(sec["id"])
            _, ev = self.send(responder.msg(proposer.id, "DECLINE",
                                            {"section_id": sec["id"], "reason_code": "conflict"},
                                            "%s doesn't work for me." % sec["id"]))
            yield ev
            proposer, responder = responder, proposer

        if agreed is None:
            for agent in (A, B):
                yield {"kind": "escalation", "student": agent.id,
                       "question": "No %s section fits both schedules without breaking one of "
                                   "your hard constraints. Want to look at other courses or "
                                   "change a constraint yourself?" % self.course}
            self.result["status"] = "no common section"
            yield {"kind": "done", **self.result}
            return

        # 3. Each student confirms the section (agents never register anyone).
        for agent in (A, B):
            yield {"kind": "confirm_request", "student": agent.id,
                   "question": "Both agents found %s. Plan to take it together? "
                               "(You still register yourself.)" % pretty_section(agreed)}
            if not self._answer:
                self.result["status"] = "section declined by %s" % names[agent.id]
                yield {"kind": "done", **self.result}
                return
        _, ev = self.send(A.msg(B.id, "CONFIRM", {"section_id": agreed["id"]}, "Confirmed on my side."))
        yield ev
        self.result["section"] = agreed["id"]

        # 4. Weekly study block: B shares free blocks (times only), A intersects.
        b_free = B.free_blocks(chosen=agreed)
        _, ev = self.send(B.msg(A.id, "FREE_BLOCKS", {"blocks": b_free[:40]},
                                "Here are my open hours (no details)."))
        yield ev
        a_free = A.free_blocks(chosen=agreed)
        common = [blk for blk in a_free if blk in b_free]
        if not common:
            yield {"kind": "escalation", "student": A.id,
                   "question": "No shared free hour this week. Want to suggest one yourself?"}
        else:
            pref = A.p["soft"].get("prefer_days") or []
            common.sort(key=lambda b: (b["day"] not in pref, b["start"]))
            block = common[0]
            _, ev = self.send(A.msg(B.id, "PROPOSE", {"study_block": block},
                                    "Study together %s %s-%s?" % (block["day"], block["start"], block["end"])))
            yield ev
            _, ev = self.send(B.msg(A.id, "ACCEPT", {"study_block": block}, "Works for me."))
            yield ev
            confirmed = True
            for agent in (A, B):
                yield {"kind": "confirm_request", "student": agent.id,
                       "question": "Add a weekly study block %s %s-%s with %s?" % (
                                block["day"], block["start"], block["end"],
                                names[B.id] if agent is A else names[A.id])}
                confirmed = confirmed and bool(self._answer)
            if confirmed:
                self.result["study_block"] = block
        _, ev = self.send(A.msg(B.id, "DONE", {"section_id": agreed["id"],
                                                "study_block": self.result["study_block"]}, "All set."))
        yield ev
        self.result["status"] = "agreed"
        yield {"kind": "done", **self.result}


def run_auto(session, answer=lambda ev: True):
    """Drive a session to the end, answering confirmations with `answer`."""
    events = []
    gen = session.run()
    ev = next(gen)
    while True:
        events.append(ev)
        try:
            ev = gen.send(answer(ev) if ev["kind"] == "confirm_request" else None)
        except StopIteration:
            return events
