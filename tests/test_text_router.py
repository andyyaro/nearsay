from helpers import TapTestCase

from nearsay import config as config_mod
from nearsay.router import resolve_name, route
from nearsay.text import normalize_task, preview, sound_key


class TextTests(TapTestCase):
    def test_removes_invisible_and_bidi_controls(self):
        raw = "add\u200b tests\u202e for\u2066 the\ufeff parser\x07"
        self.assertEqual(normalize_task(raw), "add tests for the parser")

    def test_keeps_newlines_but_tidies(self):
        self.assertEqual(normalize_task("line one  \r\n\r\n\r\n\r\nline two\r"), "line one\n\nline two")

    def test_never_starts_with_a_dash(self):
        for raw in ("-rf everything", "--help me", "— dash", "• bullet item", "  - spaced"):
            self.assertFalse(normalize_task(raw).startswith(("-", "—", "•")), raw)

    def test_preview(self):
        self.assertEqual(preview("short"), "short")
        p = preview("word " * 40, 20)
        self.assertLessEqual(len(p), 20)
        self.assertTrue(p.endswith("…"))

    def test_sound_key_matches_dictation_spelling(self):
        self.assertEqual(sound_key("Orchestra"), sound_key("orkestra"))
        self.assertEqual(sound_key("Philter"), sound_key("filter"))


class RouterTests(TapTestCase):
    def r(self, text, sticker=None):
        return route(normalize_task(text), self.cfg(), sticker)

    def assertRoute(self, text, project, task, by, sticker=None):
        r = self.r(text, sticker)
        self.assertEqual((r.project, r.task, r.matched_by), (project, task, by), text)

    def test_route_word_and_exact_name(self):
        self.assertRoute("In orkestra, add tests for the parser.", "orkestra", "add tests for the parser.", "spoken")

    def test_dictation_spelling_matches_loosely(self):
        self.assertRoute("In Orchestra, add tests", "orkestra", "add tests", "spoken")
        self.assertRoute("in prova loom add a CLI flag", "provalume", "add a CLI flag", "spoken")

    def test_bare_name_needs_punctuation(self):
        self.assertRoute("Orkestra: fix the flaky test", "orkestra", "fix the flaky test", "spoken")
        self.assertRoute("Orkestra, fix the flaky test", "orkestra", "fix the flaky test", "spoken")
        self.assertRoute("Orkestra fix the flaky test", "inbox", "Orkestra fix the flaky test", "default")

    def test_fillers_and_determiners_and_trailers(self):
        self.assertRoute("Hey Claude, in provalume add a CLI flag", "provalume", "add a CLI flag", "spoken")
        self.assertRoute("For the EV model project, rerun the notebook", "ev-model", "rerun the notebook", "spoken")
        self.assertRoute("In my orkestra repo: add docs", "orkestra", "add docs", "spoken")
        self.assertRoute("in Olympus repo, draft the schedule", "olympus", "draft the schedule", "spoken")
        self.assertRoute("In charge ready, update the readme", "ev-model", "update the readme", "spoken")

    def test_hyphenated_project_name_spoken_as_words(self):
        self.assertRoute("In ev model, plot demand", "ev-model", "plot demand", "spoken")

    def test_accents_are_ignored(self):
        self.assertRoute("In Orkéstrà, add tests", "orkestra", "add tests", "spoken")

    def test_no_false_positives(self):
        for text in ("In Paris we need a bakery list", "On the parser, add tests",
                     "In order to fix the build, bump the version", "For now, just summarize the diff",
                     "So the build is broken"):
            r = self.r(text)
            self.assertEqual((r.project, r.matched_by, r.task), ("inbox", "default", normalize_task(text)), text)

    def test_sticker_used_when_nothing_spoken(self):
        self.assertRoute("add tests", "orkestra", "add tests", "sticker", sticker="orkestra")

    def test_spoken_beats_sticker(self):
        self.assertRoute("In provalume, fix the README", "provalume", "fix the README", "spoken", sticker="orkestra")

    def test_project_without_task(self):
        r = self.r("In orkestra")
        self.assertEqual((r.project, r.task), ("orkestra", ""))
        r = self.r("In orkestra.")
        self.assertEqual((r.project, r.task), ("orkestra", ""))

    def test_ambiguous_fuzzy_match_is_not_guessed(self):
        raw = dict(self.raw)
        raw["projects"] = dict(raw["projects"])
        raw["projects"]["telemetry"] = {"path": str(self.tmp / "proj" / "inbox")}
        raw["projects"]["telemetri"] = {"path": str(self.tmp / "proj" / "inbox")}
        cfg = config_mod.parse(raw)
        # Sounds equally like both projects: refuse to guess.
        r = route("in telemetrie, do the thing", cfg)
        self.assertEqual(r.matched_by, "default")
        # An exact name still wins outright.
        r = route("in telemetry, do the thing", cfg)
        self.assertEqual((r.project, r.task), ("telemetry", "do the thing"))

    def test_resolve_name(self):
        cfg = self.cfg()
        self.assertEqual(resolve_name("desk", cfg), "orkestra")
        self.assertEqual(resolve_name("ORKESTRA", cfg), "orkestra")
        self.assertEqual(resolve_name("scratch", cfg), "inbox")
        self.assertIsNone(resolve_name("nope", cfg))
