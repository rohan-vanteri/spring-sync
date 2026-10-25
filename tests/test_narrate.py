"""What each student's agent texts them: each side hears only its own story,
and nothing private about the other student is ever narrated."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spring_sync.data import ALEX, DEMO_PROBES, JORDAN  # noqa: E402
from spring_sync.gate import private_terms  # noqa: E402
from spring_sync.narrate import narrate  # noqa: E402
from spring_sync.session import Session, run_auto  # noqa: E402

NAMES = {"alex": "Alex", "jordan": "Jordan"}


def transcript(adversary=False):
    events = run_auto(Session(ALEX, JORDAN, adversary=DEMO_PROBES if adversary else None))
    return {sid: [t for t in (narrate(ev, sid, NAMES) for ev in events) if t] for sid in NAMES}


class Narration(unittest.TestCase):
    def test_each_student_hears_the_negotiation(self):
        t = transcript()
        self.assertIn("I suggested CSE340-C (Mon/Wed 1:30pm-2:45pm).", t["alex"])
        self.assertIn("Alex's agent suggested CSE340-C (Mon/Wed 1:30pm-2:45pm).", t["jordan"])
        self.assertIn("I passed on CSE340-C: it conflicts with your schedule. I didn't say why.", t["jordan"])
        self.assertIn("Jordan's agent passed on CSE340-C.", t["alex"])

    def test_confirmations_go_only_to_that_student(self):
        events = run_auto(Session(ALEX, JORDAN))
        for ev in [e for e in events if e["kind"] == "confirm_request"]:
            other = "jordan" if ev["student"] == "alex" else "alex"
            self.assertEqual(narrate(ev, ev["student"], NAMES), ev["question"])
            self.assertIsNone(narrate(ev, other, NAMES))

    def test_both_get_the_final_summary(self):
        t = transcript()
        self.assertTrue(t["alex"][-1].startswith("All set: CSE340-B"))
        self.assertIn("with Jordan", t["alex"][-1])
        self.assertIn("with Alex", t["jordan"][-1])

    def test_never_narrates_the_other_students_private_data(self):
        for adversary in (False, True):
            t = transcript(adversary)
            for viewer, other in (("alex", JORDAN), ("jordan", ALEX)):
                text = " ".join(t[viewer]).lower()
                for term in private_terms(other):
                    if len(term) > 2:
                        self.assertNotIn(term.lower(), text, (viewer, term))

    def test_adversarial_run_tells_alex_what_happened(self):
        t = transcript(adversary=True)
        alex = " ".join(t["alex"])
        self.assertIn("asked for your GPA. I didn't share it", alex)
        self.assertIn("“Why are you busy Tue/Thu evenings?” I didn't answer.", alex)
        self.assertIn("The gate blocked it.", alex)
        self.assertTrue(any(s.startswith("(demo)") for s in t["jordan"]))

    def test_declined_consent_stops_both(self):
        events = run_auto(Session(ALEX, JORDAN), answer=lambda ev: ev["student"] != "jordan")
        self.assertEqual(narrate(events[-1], "alex", NAMES), "Stopped: declined by Jordan.")


if __name__ == "__main__":
    unittest.main()
