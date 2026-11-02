import os
import stat
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from helpers import RecordingRunner, TapTestCase, have, run
from test_config_jobs import make_job

from nearsay import config as config_mod
from nearsay.launcher import (DEEP_LINK_MAX_Q, Launcher, claude_args, opener_argv, render_run_script,
                                review_url, session_name)

HOSTILE = [
    "add tests; touch {marker}",
    "$(touch {marker})",
    "`touch {marker}`",
    "it's a \"quoted\" task with \\backslashes\\ and $HOME and ${{PATH}}",
    "multi\nline\ntask with 'single' quotes",
    "émoji 🚀 and Ünïcödé — and a tab\there",
    "'; touch {marker}; echo '",
    "\" ; touch {marker} ; \"",
    "!! history !$ and %1 job",
]


class LauncherUnitTests(TapTestCase):
    def test_session_name(self):
        n = session_name("orkestra", 'add "fast" tests ' * 10)
        self.assertLessEqual(len(n), 60)
        self.assertTrue(n.startswith("orkestra: add 'fast' tests"))

    def test_claude_args(self):
        cfg = self.cfg()
        job = make_job()
        self.assertEqual(claude_args(cfg, cfg.project("orkestra"), job, "N"),
                         [str(self.fake_claude), "--name", "N", "--remote-control", "N"])
        self.assertEqual(claude_args(cfg, cfg.project("provalume"), job, "N")[-2:], ["--permission-mode", "acceptEdits"])
        self.assertEqual(claude_args(cfg, cfg.project("ev-model"), job, "N")[-2:], ["--model", "sonnet"])
        wt = claude_args(cfg, cfg.project("olympus"), job, "N")
        self.assertEqual(wt[-2], "--worktree")
        self.assertTrue(wt[-1].startswith("tap-"))
        bg = claude_args(cfg, cfg.project("orkestra"), job, "N", background=True)
        self.assertNotIn("--remote-control", bg)

    def test_remote_control_can_be_turned_off(self):
        raw = dict(self.raw)
        raw["projects"] = dict(raw["projects"])
        raw["projects"]["orkestra"] = dict(raw["projects"]["orkestra"], remote_control=False)
        cfg = config_mod.parse(raw)
        self.assertNotIn("--remote-control", claude_args(cfg, cfg.project("orkestra"), make_job(), "N"))

    def test_opener_argv_for_every_terminal(self):
        script = Path("/Users/andy/.nearsay/jobs/x/run.command")
        expect = {
            "Terminal": ["open", "-a", "Terminal", str(script)],
            "Ghostty": ["open", "-na", "Ghostty", "--args", "-e", str(script)],
            "kitty": ["open", "-na", "kitty", "--args", str(script)],
            "Alacritty": ["open", "-na", "Alacritty", "--args", "-e", str(script)],
            "WezTerm": ["open", "-na", "WezTerm", "--args", "start", "--", str(script)],
        }
        for term, argv in expect.items():
            cfg = config_mod.parse(dict(self.raw, terminal=term))
            self.assertEqual(opener_argv(cfg, script), argv)
        cfg = config_mod.parse(dict(self.raw, terminal="iTerm"))
        it = opener_argv(cfg, script)
        self.assertEqual(it[0], "osascript")
        self.assertEqual(it[-1], str(script))  # passed as argv, not spliced into AppleScript
        self.assertNotIn(str(script), " ".join(it[:-1]))
        cfg = config_mod.parse(dict(self.raw, terminal="custom", terminal_command=["myterm", "--run={script}"]))
        self.assertEqual(opener_argv(cfg, script), ["myterm", f"--run={script}"])

    def test_review_url_round_trips_and_truncates(self):
        path = Path("/Users/andy/My Projects/orkestra")
        task = "fix A&B #3?\nthen ünïcode + 100% = done"
        u = urlparse(review_url(path, task))
        self.assertEqual((u.scheme, u.netloc), ("claude-cli", "open"))
        q = parse_qs(u.query)
        self.assertEqual(q["cwd"], [str(path)])
        self.assertEqual(q["q"], [task])
        long = parse_qs(urlparse(review_url(path, "z" * 9000)).query)["q"][0]
        self.assertLessEqual(len(long), DEEP_LINK_MAX_Q)
        self.assertIn("truncated", long)


@unittest.skipUnless(have("zsh"), "zsh not installed")
class RunScriptExecutionTests(TapTestCase):
    """Generate real run.command scripts and execute them with zsh and a fake claude."""

    def launch_and_run(self, project_name, task, exit_code=0, project_path=None):
        raw = dict(self.raw)
        if project_path is not None:
            raw["projects"] = dict(raw["projects"])
            project_path.mkdir(parents=True, exist_ok=True)
            raw["projects"][project_name] = dict(raw["projects"][project_name], path=str(project_path))
        raw["keep_shell"] = False
        cfg = self.write_config(raw)
        job = make_job(project=project_name, task=task)
        job_dir = self.paths.jobs / job.id
        job_dir.mkdir(parents=True)
        runner = RecordingRunner()
        res = Launcher(runner).launch(cfg, cfg.project(project_name), job, job_dir)
        self.assertTrue(res.ok, res.detail)
        script = job_dir / "run.command"
        self.assertEqual(runner.calls[0]["argv"], ["open", "-a", "Terminal", str(script)])
        self.assertEqual(stat.S_IMODE(os.stat(script).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(job_dir / "prompt.txt").st_mode), 0o600)
        body = script.read_text(encoding="utf-8")
        # The full task reaches claude only through prompt.txt -> "$NEARSAY_TASK" (one argv item).
        # Short previews appear in the window title and session name, always shell-quoted.
        self.assertEqual(sum(ln.endswith('"$NEARSAY_TASK"') for ln in body.splitlines()), 1)
        syntax = run(["zsh", "-n", str(script)])
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        env = dict(os.environ, FAKE_CLAUDE_LOG=str(self.claude_log), FAKE_CLAUDE_EXIT=str(exit_code))
        cp = run([str(script)], env=env, input="x", cwd=str(self.tmp))
        return cp, cfg, job

    def test_hostile_tasks_arrive_byte_for_byte(self):
        marker = self.tmp / "pwned"
        for template in HOSTILE:
            task = template.format(marker=marker)
            cp, cfg, job = self.launch_and_run("orkestra", task)
            self.assertEqual(cp.returncode, 0, cp.stderr)
            call = self.claude_calls()[-1]
            self.assertEqual(call["argv"][-1], task)
            self.assertEqual(call["argv"][:5], ["--name", call["argv"][1], "--remote-control", call["argv"][1], task][:5])
            self.assertEqual(Path(call["cwd"]).resolve(), cfg.project("orkestra").path.resolve())
            self.assertEqual(call["job"], job.id)
        self.assertFalse(marker.exists(), "a task was interpreted by the shell")

    def test_awkward_project_paths(self):
        weird = self.tmp / "proj" / "it's a \"weird\" $dir with spaces"
        cp, cfg, job = self.launch_and_run("orkestra", "list files", project_path=weird)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertEqual(Path(self.claude_calls()[-1]["cwd"]).resolve(), weird.resolve())

    def test_failure_exit_code_is_reported(self):
        cp, _, _ = self.launch_and_run("provalume", "will fail", exit_code=3)
        self.assertEqual(cp.returncode, 3)
        self.assertIn("claude exited with status 3", cp.stdout)
        self.assertEqual(self.claude_calls()[-1]["argv"][-3:], ["--permission-mode", "acceptEdits", "will fail"])

    def test_missing_folder_after_script_written(self):
        cfg = self.cfg()
        job = make_job(project="orkestra", task="x")
        job_dir = self.paths.jobs / job.id
        job_dir.mkdir(parents=True)
        Launcher(RecordingRunner()).launch(cfg, cfg.project("orkestra"), job, job_dir)
        cfg.project("orkestra").path.rename(self.tmp / "moved")
        cp = run([str(job_dir / "run.command")], input="x",
                 env=dict(os.environ, FAKE_CLAUDE_LOG=str(self.claude_log)))
        self.assertEqual(cp.returncode, 1)
        self.assertIn("cannot open", cp.stdout)
        self.assertEqual(self.claude_calls(), [])


class LaunchModesTests(TapTestCase):
    def launch(self, project="orkestra", mode="run", runner=None, task="add tests"):
        cfg = self.cfg()
        job = make_job(project=project, task=task, mode=mode)
        job_dir = self.paths.jobs / job.id
        job_dir.mkdir(parents=True)
        runner = runner or RecordingRunner()
        return Launcher(runner).launch(cfg, cfg.project(project), job, job_dir), runner, job_dir

    def test_review_mode_opens_deep_link(self):
        res, runner, job_dir = self.launch(mode="review", task="draft notes & ship")
        self.assertTrue(res.ok)
        argv = runner.calls[0]["argv"]
        self.assertEqual(argv[0], "open")
        self.assertTrue(argv[1].startswith("claude-cli://open?cwd="))
        self.assertEqual(parse_qs(urlparse(argv[1]).query)["q"], ["draft notes & ship"])
        self.assertFalse((job_dir / "run.command").exists())

    def test_background_mode(self):
        runner = RecordingRunner(stdout="Started background session 7c5dcf5d\nmore")
        res, runner, _ = self.launch(project="provalume", mode="background", runner=runner)
        self.assertTrue(res.ok)
        call = runner.calls[0]
        self.assertEqual(call["argv"][-2:], ["--bg", "add tests"])
        self.assertIn("--permission-mode", call["argv"])
        self.assertNotIn("--remote-control", call["argv"])
        self.assertEqual(call["cwd"], str(self.cfg().project("provalume").path))
        self.assertIn("7c5dcf5d", res.detail)
        self.assertIn(str(self.fake_claude.parent), call["env"]["PATH"].split(":")[0])

    def test_failures_are_reported_not_raised(self):
        res, _, _ = self.launch(runner=RecordingRunner(returncode=1, stderr="LSOpenURLs failed\nNo app"))
        self.assertFalse(res.ok)
        self.assertIn("No app", res.detail)
        res, _, _ = self.launch(runner=RecordingRunner(raise_exc=FileNotFoundError(2, "nf", "open")))
        self.assertFalse(res.ok)
        self.assertIn("command not found", res.detail)

    def test_missing_project_folder(self):
        self.cfg().project("orkestra").path.rmdir()
        res, runner, _ = self.launch()
        self.assertFalse(res.ok)
        self.assertIn("project folder not found", res.detail)
        self.assertEqual(runner.calls, [])

    def test_keep_shell_line(self):
        cfg = self.cfg()
        job = make_job()
        body = render_run_script(job, cfg.project("orkestra"), ["claude"], Path("/x/prompt.txt"), "t", True)
        self.assertTrue(body.rstrip().endswith('exec "${SHELL:-/bin/zsh}" -l'))
        body = render_run_script(job, cfg.project("orkestra"), ["claude"], Path("/x/prompt.txt"), "t", False)
        self.assertNotIn("exec", body)


if __name__ == "__main__":
    unittest.main()
