"""The browser site: its copy of the engine matches spring_sync/, the runner
drives sessions step by step, and the schedule form is validated."""
import copy
import filecmp
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import build_site  # noqa: E402
from spring_sync.data import ALEX, JORDAN  # noqa: E402
from spring_sync.gate import private_terms  # noqa: E402
from spring_sync.runner import SAMPLE_FORMS, Runner, build_profile, parse_busy  # noqa: E402


def run_all(runner, answer=True):
    events = runner.start()
    out = list(events)
    while runner.pending:
        events = runner.answer(answer)
        out += events
    return out


class SiteCopy(unittest.TestCase):
    def test_site_engine_matches_repo(self):
        for name in build_site.FILES:
            src = os.path.join(build_site.SRC, name)
            dst = os.path.join(build_site.DST, name)
            self.assertTrue(os.path.exists(dst), "missing %s: run python3 tools/build_site.py" % name)
            self.assertTrue(filecmp.cmp(src, dst, shallow=False),
                            "docs/py/spring_sync/%s is stale: run python3 tools/build_site.py" % name)

    def test_page_loads_every_engine_file(self):
        with open(os.path.join(ROOT, "docs", "index.html")) as f:
            page = f.read()
        for name in build_site.FILES:
            self.assertIn('"%s"' % name, page)


class RunnerFlow(unittest.TestCase):
    def test_sample_run_matches_session(self):
        events = run_all(Runner(ALEX, JORDAN))
        self.assertEqual(events[-1]["status"], "agreed")
        self.assertEqual(events[-1]["section"], "CSE340-B")
        self.assertTrue(all(set(e["say"]) == {"alex", "jordan"} for e in events))

    def test_answer_without_pending_raises(self):
        r = Runner(ALEX, JORDAN)
        run_all(r)
        with self.assertRaises(ValueError):
            r.answer(True)

    def test_no_stops_both(self):
        events = run_all(Runner(ALEX, JORDAN), answer=False)
        self.assertIn("declined by Alex", events[-1]["status"])

    def test_events_are_json_safe(self):
        json.dumps(run_all(Runner(ALEX, JORDAN, adversary=True)))


class Forms(unittest.TestCase):
    def test_sample_forms_round_trip(self):
        a = build_profile("alex", SAMPLE_FORMS["alex"])
        b = build_profile("jordan", SAMPLE_FORMS["jordan"])
        self.assertEqual(a["busy"], ALEX["busy"])
        self.assertEqual(b["busy"], JORDAN["busy"])
        self.assertEqual(run_all(Runner(a, b))[-1]["section"], "CSE340-B")

    def test_custom_students_negotiate_and_keep_reasons_private(self):
        fa = dict(SAMPLE_FORMS["alex"], name="Priya", busy="Mon Wed Fri 08:00-12:30 lab job\nTue 13:00-17:00 therapy",
                  earliest="09:00", gpa="3.9", other_private="Dean's list")
        fb = dict(SAMPLE_FORMS["jordan"], name="Sam", busy="Tue Thu 08:00-10:00 ROTC", gpa="2.4",
                  other_private="on probation")
        a, b = build_profile("alex", fa), build_profile("jordan", fb)
        events = run_all(Runner(a, b, adversary=True))
        self.assertEqual(events[-1]["status"], "agreed")
        for viewer, other in (("alex", b), ("jordan", a)):
            said = " ".join(e["say"][viewer] or "" for e in events).lower()
            for term in private_terms(other):
                if len(term) > 2:
                    self.assertNotIn(term.lower(), said, (viewer, term))
        crossed = json.dumps([e for e in events if e["kind"] == "message"]).lower()
        for term in ("lab job", "therapy", "rotc", "3.9", "2.4", "probation", "dean"):
            self.assertNotIn(term, crossed)

    def test_no_common_section_is_reported(self):
        fb = dict(SAMPLE_FORMS["jordan"], busy="Mon Tue Wed Thu Fri 08:00-20:00 everything")
        events = run_all(Runner(build_profile("alex", SAMPLE_FORMS["alex"]), build_profile("jordan", fb)))
        self.assertEqual(events[-1]["status"], "no common section")

    def test_parse_busy_variants(self):
        self.assertEqual(parse_busy("tue, thu 9:00-10:30 gym", "X"),
                         [{"days": ["Tue", "Thu"], "start": "09:00", "end": "10:30", "reason": "gym"}])
        self.assertEqual(parse_busy("Mon 12:00-13:00", "X")[0]["reason"], "busy")
        self.assertEqual(parse_busy("\n  \n", "X"), [])

    def test_bad_input_gives_a_readable_error(self):
        bad = [dict(SAMPLE_FORMS["alex"], name=""),
               dict(SAMPLE_FORMS["alex"], name="<script>"),
               dict(SAMPLE_FORMS["alex"], campuses=[]),
               dict(SAMPLE_FORMS["alex"], busy="sometimes in the afternoon"),
               dict(SAMPLE_FORMS["alex"], busy="Mon 14:00-13:00 backwards"),
               dict(SAMPLE_FORMS["alex"], earliest="25:00")]
        for form in bad:
            with self.assertRaises(ValueError):
                build_profile("alex", form)

    def test_form_cannot_inject_fields(self):
        form = copy.deepcopy(SAMPLE_FORMS["alex"])
        form["hard"] = {"earliest": "00:00"}
        form["id"] = "jordan"
        p = build_profile("alex", form)
        self.assertEqual(p["id"], "alex")
        self.assertEqual(p["hard"]["earliest"], SAMPLE_FORMS["alex"]["earliest"])


if __name__ == "__main__":
    unittest.main()
