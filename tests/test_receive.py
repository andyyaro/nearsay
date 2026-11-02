import io
import json
import os
import subprocess
import sys

from helpers import ROOT, TapTestCase

from nearsay import jobs, receive


class ReceiveTests(TapTestCase):
    def send(self, text, hint="tap", env=None, now=None):
        e = {"SSH_ORIGINAL_COMMAND": hint, "SSH_CONNECTION": "192.168.1.23 51234 192.168.1.10 22"}
        e.update(env or {})
        out = io.StringIO()
        data = text if isinstance(text, bytes) else text.encode("utf-8")
        code = receive.run(io.BytesIO(data), e, out, paths=self.paths, now=now)
        return code, out.getvalue().strip()

    def queued(self):
        return [json.loads(p.read_text(encoding="utf-8")) for p in jobs.list_queue(self.paths)]

    def log_events(self):
        path = self.paths.logs / "receive.log"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_phone_hanging_up_before_the_reply_is_not_a_crash(self):
        class HungUp(io.StringIO):
            def flush(self):
                raise BrokenPipeError(32, "Broken pipe")

        e = {"SSH_ORIGINAL_COMMAND": "tap", "SSH_CONNECTION": "192.168.1.23 51234 192.168.1.10 22"}
        code = receive.run(io.BytesIO(b"In inbox, tidy the notes"), e, HungUp(), paths=self.paths)
        self.assertEqual(code, 0)
        self.assertEqual([j["task"] for j in self.queued()], ["tidy the notes"])  # the task still runs
        gone = self.log_events()[-1]
        self.assertEqual((gone["event"], gone["client"]), ("client_gone", "192.168.1.23"))
        self.assertTrue(gone["reply"].startswith("✓ inbox"), gone)

    def test_entry_point_exits_cleanly_when_the_pipe_is_closed(self):
        # The real failure: sshd's end of stdout is gone by the time the receiver answers.
        env = dict(os.environ, NEARSAY_HOME=str(self.paths.root), SSH_ORIGINAL_COMMAND="tap")
        code = "import sys; sys.path.insert(0, sys.argv[1]); from nearsay import receive; sys.exit(receive.main())"
        proc = subprocess.Popen([sys.executable, "-I", "-c", code, str(ROOT)], env=env, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.stdout.close()  # hang up first; the receiver only answers after stdin closes
        proc.stdin.close()   # nothing was said
        err = proc.stderr.read().decode()
        proc.stderr.close()
        self.assertEqual(proc.wait(timeout=30), 0, err)
        self.assertEqual(err, "")
        self.assertEqual([ev["event"] for ev in self.log_events()], ["client_gone"])
        self.assertIn("Nothing was heard", self.log_events()[0]["reply"])

    def test_happy_path_with_sticker(self):
        code, msg = self.send("add tests for the parser", hint="tap desk")
        self.assertEqual(code, 0)
        self.assertTrue(msg.startswith("✓ orkestra"), msg)
        (job,) = self.queued()
        self.assertEqual((job["project"], job["task"], job["matched_by"], job["mode"]),
                         ("orkestra", "add tests for the parser", "sticker", "run"))
        self.assertEqual(job["client"], "192.168.1.23")
        self.assertEqual(job["source"], "ssh")

    def test_spoken_routing_from_default_sticker(self):
        code, msg = self.send("In provalume, fix the README")
        (job,) = self.queued()
        self.assertEqual((job["project"], job["task"], job["matched_by"]), ("provalume", "fix the README", "spoken"))

    def test_empty_and_whitespace_only(self):
        for text in ("", "   \n\t ", "\u200b\u200b", "- - -"):
            code, msg = self.send(text)
            self.assertEqual(code, 0)
            self.assertTrue(msg.startswith("✗ Nothing was heard"), (text, msg))
        self.assertEqual(self.queued(), [])

    def test_too_long(self):
        code, msg = self.send(b"x" * (receive.MAX_STDIN_BYTES + 10))
        self.assertIn("too long", msg)
        raw = dict(self.raw, max_task_chars=50)
        self.write_config(raw)
        code, msg = self.send("y" * 51)
        self.assertIn("Task too long", msg)
        self.assertEqual(self.queued(), [])

    def test_hostile_script_field_is_rejected_and_never_executed(self):
        marker = self.tmp / "pwned"
        for hint in (f"tap; touch {marker}", f"$(touch {marker})", f"`touch {marker}`",
                     f"orkestra && touch {marker}", "../../etc/passwd", "a" * 300, "cat /etc/passwd"):
            code, msg = self.send("add tests", hint=hint)
            self.assertEqual(code, 0)
            self.assertTrue(msg.startswith("✗"), (hint, msg))
        self.assertFalse(marker.exists())
        self.assertEqual(self.queued(), [])

    def test_unknown_sticker_lists_known_names(self):
        _, msg = self.send("x", hint="tap kitchen")
        self.assertIn("Unknown sticker or project 'kitchen'", msg)
        self.assertIn("orkestra", msg)
        self.assertIn("desk", msg)

    def test_two_projects_rejected(self):
        _, msg = self.send("x", hint="tap orkestra provalume")
        self.assertIn("two different projects", msg)

    def test_mode_override(self):
        self.send("draft release notes", hint="tap orkestra mode=review")
        (job,) = self.queued()
        self.assertEqual(job["mode"], "review")
        _, msg = self.send("again", hint="tap mode=turbo")
        self.assertIn("Unknown mode", msg)

    def test_ping_and_status_queue_nothing(self):
        _, msg = self.send("", hint="ping")
        self.assertIn("is reachable", msg)
        _, msg = self.send("", hint="status")
        self.assertIn("No tasks yet", msg)
        self.assertEqual(self.queued(), [])
        self.send("add tests", hint="tap desk")
        _, msg = self.send("", hint="status")
        self.assertIn("1 waiting in queue", msg)

    def test_duplicate_tap_ignored_within_window(self):
        self.send("add tests", hint="tap desk", now=1000.0)
        _, msg = self.send("add tests", hint="tap desk", now=1005.0)
        self.assertIn("ignored the repeat", msg)
        _, msg = self.send("add tests", hint="tap desk", now=1030.0)
        self.assertTrue(msg.startswith("✓"), msg)
        self.assertEqual(len(self.queued()), 2)

    def test_dedupe_can_be_disabled(self):
        self.write_config(dict(self.raw, dedupe_seconds=0))
        self.send("same", now=1.0)
        self.send("same", now=1.5)
        self.assertEqual(len(self.queued()), 2)

    def test_missing_and_broken_config(self):
        self.paths.config.unlink()
        _, msg = self.send("x")
        self.assertIn("not set up", msg)
        self.paths.config.write_text("{bad json", encoding="utf-8")
        _, msg = self.send("x")
        self.assertIn("Config problem", msg)

    def test_invalid_utf8_is_tolerated(self):
        code, msg = self.send(b"fix the caf\xe9 bug")
        self.assertTrue(msg.startswith("✓"))
        (job,) = self.queued()
        self.assertIn("�", job["task"])

    def test_project_without_task(self):
        _, msg = self.send("In orkestra.")
        self.assertIn("no task after it", msg)
        self.assertEqual(self.queued(), [])

    def test_backlog_warning(self):
        for i in range(3):
            self.send(f"task {i}")
        _, msg = self.send("task 4")
        self.assertIn("already waiting", msg)

    def test_multiline_script_field_uses_our_line_only(self):
        h = receive.parse_hint("export LANG=C\ntap desk\n", self.cfg())
        self.assertEqual((h.project, h.error), ("orkestra", None))
        # ...but a line that tries to chain a command is still rejected as a whole.
        h = receive.parse_hint("tap desk; rm -rf ~", self.cfg())
        self.assertIsNotNone(h.error)

    def test_hint_parser_noops(self):
        h = receive.parse_hint("tap - nearsay", self.cfg())
        self.assertEqual((h.project, h.mode, h.command, h.error), (None, None, None, None))
