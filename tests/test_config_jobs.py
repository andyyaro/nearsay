import json
import os
import stat

from helpers import TapTestCase

from tapclaude import config as config_mod
from tapclaude import jobs
from tapclaude.config import ConfigError


class ConfigTests(TapTestCase):
    def bad(self, mutate, needle):
        raw = json.loads(json.dumps(self.raw))
        mutate(raw)
        with self.assertRaises(ConfigError) as ctx:
            config_mod.parse(raw)
        joined = " | ".join(ctx.exception.problems)
        self.assertIn(needle, joined)

    def test_defaults_are_valid(self):
        cfg = config_mod.parse(config_mod.default_raw())
        self.assertEqual(cfg.default_project, "inbox")
        self.assertEqual(cfg.mode, "run")
        self.assertTrue(str(cfg.projects["inbox"].path).endswith("tapclaude-inbox"))

    def test_project_overrides_inherit_globals(self):
        cfg = self.cfg()
        self.assertEqual(cfg.projects["provalume"].permission_mode, "acceptEdits")
        self.assertEqual(cfg.projects["orkestra"].permission_mode, "default")
        self.assertEqual(cfg.projects["ev-model"].model, "sonnet")
        self.assertTrue(cfg.projects["olympus"].worktree)

    def test_validation_messages(self):
        self.bad(lambda r: r.update(nonsense=1), "unknown setting")
        self.bad(lambda r: r.update(mode="yolo"), "mode must be one of")
        self.bad(lambda r: r.update(terminal="Hyper"), "terminal must be one of")
        self.bad(lambda r: r.update(terminal="custom", terminal_command=["open", "x"]), "{script}")
        self.bad(lambda r: r.update(permission_mode="godmode"), "permission_mode")
        self.bad(lambda r: r.update(notify="yes"), "notify must be true or false")
        self.bad(lambda r: r.update(linger_seconds=-1), "linger_seconds")
        self.bad(lambda r: r.update(max_task_chars=True), "max_task_chars")
        self.bad(lambda r: r.update(default_project="ghost"), "default_project")
        self.bad(lambda r: r["projects"].update(Bad_Name={"path": "/x"}), "name must be lowercase")
        self.bad(lambda r: r["projects"].update(rel={"path": "relative/path"}), "must be absolute")
        self.bad(lambda r: r["projects"].update(nopath={}), '"path" is required')
        self.bad(lambda r: r["projects"]["orkestra"].update(colour="red"), "unknown key")
        self.bad(lambda r: r["projects"]["orkestra"].update(aliases=["scratch"]), "used by both")
        self.bad(lambda r: r["stickers"].update(desk="ghost"), "unknown project")
        self.bad(lambda r: r.update(projects={}), "at least one project")

    def test_all_problems_reported_at_once(self):
        raw = dict(self.raw, mode="x", terminal="y")
        with self.assertRaises(ConfigError) as ctx:
            config_mod.parse(raw)
        self.assertGreaterEqual(len(ctx.exception.problems), 2)

    def test_save_is_private_and_round_trips(self):
        config_mod.save(self.paths.config, self.raw)
        self.assertEqual(stat.S_IMODE(os.stat(self.paths.config).st_mode), 0o600)
        self.assertEqual(config_mod.load(self.paths.config).raw["projects"].keys(), self.raw["projects"].keys())

    def test_invalid_json_points_at_the_line(self):
        self.paths.config.write_text('{\n  "mode": "run",\n  oops\n}', encoding="utf-8")
        with self.assertRaises(ConfigError) as ctx:
            config_mod.load(self.paths.config)
        self.assertIn("line 3", ctx.exception.problems[0])

    def test_documented_example_config_is_valid(self):
        from helpers import ROOT
        raw = json.loads((ROOT / "examples" / "config.example.json").read_text(encoding="utf-8"))
        cfg = config_mod.parse(raw)
        self.assertEqual(cfg.stickers, {"desk": "orkestra", "lab": "provalume"})

    def test_save_refuses_invalid(self):
        before = self.paths.config.read_text(encoding="utf-8")
        with self.assertRaises(ConfigError):
            config_mod.save(self.paths.config, dict(self.raw, mode="nope"))
        self.assertEqual(self.paths.config.read_text(encoding="utf-8"), before)


def make_job(project="orkestra", task="add tests", mode="run", job_id=None):
    return jobs.Job(id=job_id or jobs.new_job_id(), created_at=jobs.now_utc().isoformat(), source="local",
                    client=None, hint="", project=project, task=task, matched_by="default", heard_as=None, mode=mode)


class JobTests(TapTestCase):
    def test_enqueue_is_atomic_and_private(self):
        job = make_job()
        q = jobs.enqueue(self.paths, job)
        self.assertEqual(q.parent, self.paths.queue)
        self.assertEqual(list(self.paths.incoming.iterdir()), [])
        self.assertEqual(stat.S_IMODE(os.stat(q).st_mode), 0o600)
        self.assertEqual(json.loads(q.read_text(encoding="utf-8"))["task"], "add tests")
        self.assertRegex(job.id, r"^\d{8}T\d{12}-[0-9a-f]{6}$")

    def test_rapid_jobs_stay_in_arrival_order(self):
        ids = [jobs.enqueue(self.paths, make_job(task=str(i))).stem for i in range(200)]
        self.assertEqual([q.stem for q in jobs.list_queue(self.paths)], ids)

    def test_claim_once(self):
        q = jobs.enqueue(self.paths, make_job())
        d = jobs.claim(self.paths, q)
        self.assertTrue((d / "job.json").exists())
        self.assertIsNone(jobs.claim(self.paths, q))
        self.assertEqual(jobs.list_queue(self.paths), [])

    def test_sweep_strays_empties_queue(self):
        (self.paths.queue / ".DS_Store").write_text("x")
        (self.paths.queue / "notes.txt").write_text("x")
        (self.paths.queue / "folder").mkdir()
        jobs.enqueue(self.paths, make_job())
        moved = jobs.sweep_strays(self.paths)
        self.assertEqual(len(moved), 3)
        self.assertEqual([p.suffix for p in self.paths.queue.iterdir()], [".json"])

    def test_status_and_recent_and_prune(self):
        ids = []
        for i in range(5):
            jid = f"2026101{i}T000000-00000{i}"
            ids.append(jid)
            d = jobs.claim(self.paths, jobs.enqueue(self.paths, make_job(job_id=jid)))
            jobs.write_status(d, "launched", "ok")
        self.assertEqual([d.name for d in jobs.recent(self.paths, 2)], [ids[4], ids[3]])
        self.assertEqual(jobs.read_status(self.paths.jobs / ids[0])["status"], "launched")
        self.assertEqual(jobs.prune(self.paths, 2), 3)
        self.assertEqual([d.name for d in jobs.job_dirs(self.paths)], ids[3:])

    def test_from_dict_requires_fields(self):
        with self.assertRaises(ValueError):
            jobs.Job.from_dict({"id": "x"})
