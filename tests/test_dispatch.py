import fcntl
import os

from helpers import RecordingRunner, TapTestCase
from test_config_jobs import make_job

from nearsay import jobs
from nearsay.dispatch import Dispatcher
from nearsay.launcher import Launcher, LaunchResult
from nearsay.notify import Notifier


class FakeLauncher:
    def __init__(self, result=None, exc=None):
        self.result = result or LaunchResult(True, "opened Terminal")
        self.exc = exc
        self.seen = []

    def launch(self, cfg, project, job, job_dir):
        self.seen.append((project.name, job.task, job.mode))
        if self.exc:
            raise self.exc
        return self.result


class DispatchTests(TapTestCase):
    def setUp(self):
        super().setUp()
        self.notes = []

        def factory(on, speak):
            n = Notifier(RecordingRunner(), on, speak)
            self.notes.append(n)
            return n
        self.factory = factory

    def disp(self, launcher):
        return Dispatcher(self.paths, launcher=launcher, notifier_factory=self.factory)

    def notifications(self):
        return [argv for n in self.notes for argv in n.sent if argv[0] == "osascript"]

    def test_processes_queue_and_leaves_it_empty(self):
        for t in ("one", "two"):
            jobs.enqueue(self.paths, make_job(task=t))
        fl = FakeLauncher()
        d = self.disp(fl)
        self.assertEqual(d.run(linger=0), 0)
        self.assertEqual([s[1] for s in fl.seen], ["one", "two"])
        self.assertEqual(jobs.list_queue(self.paths), [])
        statuses = [jobs.read_status(x)["status"] for x in jobs.job_dirs(self.paths)]
        self.assertEqual(statuses, ["launched", "launched"])
        self.assertEqual(len(self.notifications()), 2)
        self.assertIn("Claude Code ▸ orkestra", self.notifications()[0])

    def test_bad_job_file_fails_cleanly(self):
        (self.paths.queue / "20260101T000000-aaaaaa.json").write_text("{not json", encoding="utf-8")
        (self.paths.queue / "20260101T000001-bbbbbb.json").write_text('{"id": "x"}', encoding="utf-8")
        d = self.disp(FakeLauncher())
        d.run(linger=0)
        self.assertEqual(jobs.list_queue(self.paths), [])
        self.assertEqual([jobs.read_status(x)["status"] for x in jobs.job_dirs(self.paths)], ["failed", "failed"])

    def test_strays_never_block_the_queue(self):
        (self.paths.queue / ".DS_Store").write_bytes(b"\0")
        (self.paths.queue / "subdir").mkdir()
        self.disp(FakeLauncher()).run(linger=0)
        self.assertEqual(list(self.paths.queue.iterdir()), [])

    def test_unknown_project_falls_back_to_default(self):
        jobs.enqueue(self.paths, make_job(project="deleted-project"))
        fl = FakeLauncher()
        self.disp(fl).run(linger=0)
        self.assertEqual(fl.seen[0][0], "inbox")
        st = jobs.read_status(jobs.job_dirs(self.paths)[0])
        self.assertIn("no longer configured", st["detail"])

    def test_launcher_crash_is_contained(self):
        jobs.enqueue(self.paths, make_job())
        jobs.enqueue(self.paths, make_job(task="second"))
        self.disp(FakeLauncher(exc=RuntimeError("boom"))).run(linger=0)
        self.assertEqual(jobs.list_queue(self.paths), [])
        st = jobs.read_status(jobs.job_dirs(self.paths)[0])
        self.assertEqual(st["status"], "failed")
        self.assertIn("boom", st["detail"])
        self.assertTrue(any("task not started" in " ".join(a) for a in self.notifications()))

    def test_launch_failure_notifies(self):
        jobs.enqueue(self.paths, make_job())
        self.disp(FakeLauncher(LaunchResult(False, "project folder not found: /x"))).run(linger=0)
        st = jobs.read_status(jobs.job_dirs(self.paths)[0])
        self.assertEqual((st["status"], st["detail"]), ("failed", "project folder not found: /x"))

    def test_second_dispatcher_backs_off_while_locked(self):
        jobs.enqueue(self.paths, make_job())
        fd = os.open(str(self.paths.lock), os.O_RDWR | os.O_CREAT)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            fl = FakeLauncher()
            self.assertEqual(self.disp(fl).run(linger=0), 0)
            self.assertEqual(fl.seen, [])
            self.assertEqual(len(jobs.list_queue(self.paths)), 1)
        finally:
            os.close(fd)

    def test_linger_catches_a_quick_second_tap(self):
        jobs.enqueue(self.paths, make_job(task="first"))
        t = [0.0]
        enqueued = []

        def clock():
            return t[0]

        def sleep(s):
            t[0] += s
            if not enqueued and t[0] >= 2:
                enqueued.append(jobs.enqueue(self.paths, make_job(task="second tap")))

        fl = FakeLauncher()
        Dispatcher(self.paths, launcher=fl, notifier_factory=self.factory, clock=clock, sleep=sleep).run(linger=5)
        self.assertEqual([s[1] for s in fl.seen], ["first", "second tap"])
        self.assertGreaterEqual(t[0], 7)  # waited a full linger period after the second job

    def test_prune_runs(self):
        self.write_config(dict(self.raw, keep_jobs=2))
        for i in range(4):
            jobs.enqueue(self.paths, make_job(task=f"t{i}", job_id=f"2026010{i}T000000-00000{i}"))
        self.disp(FakeLauncher()).run(linger=0)
        self.assertEqual(len(jobs.job_dirs(self.paths)), 2)

    def test_real_launcher_with_missing_folder(self):
        self.cfg().project("orkestra").path.rmdir()
        jobs.enqueue(self.paths, make_job())
        self.disp(Launcher(RecordingRunner())).run(linger=0)
        st = jobs.read_status(jobs.job_dirs(self.paths)[0])
        self.assertIn("project folder not found", st["detail"])

    def test_notifications_disabled(self):
        self.write_config(dict(self.raw, notify=False))
        jobs.enqueue(self.paths, make_job())
        self.disp(FakeLauncher()).run(linger=0)
        self.assertEqual(self.notifications(), [])

    def test_notification_text_is_argv_not_script(self):
        jobs.enqueue(self.paths, make_job(task='say "hi" & end tell; do shell script "rm -rf ~"'))
        self.disp(FakeLauncher()).run(linger=0)
        argv = self.notifications()[0]
        script_parts = [argv[i + 1] for i, a in enumerate(argv) if a == "-e"]
        self.assertFalse(any("rm -rf" in s for s in script_parts))
        self.assertTrue(any("rm -rf" in a for a in argv[-3:]))
