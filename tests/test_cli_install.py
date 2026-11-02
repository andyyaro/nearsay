import contextlib
import io
import json
import os
import plistlib
import shutil
import sys
import unittest

from helpers import ROOT, TapTestCase, have, run

from nearsay import cli, jobs

INSTALL_PY = os.environ.get("NEARSAY_TEST_PYTHON") or shutil.which("python3.9") or sys.executable


class CliTests(TapTestCase):
    def setUp(self):
        super().setUp()
        self.home = self.tmp / "home"
        self.old_env = {k: os.environ.get(k) for k in ("HOME", "NEARSAY_HOME", "FAKE_CLAUDE_LOG")}
        os.environ["HOME"] = str(self.home)
        os.environ["NEARSAY_HOME"] = str(self.paths.root)
        os.environ["FAKE_CLAUDE_LOG"] = str(self.claude_log)
        self.addCleanup(self.restore_env)

    def restore_env(self):
        for k, v in self.old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = cli.main(list(argv))
            except SystemExit as e:
                code = e.code
        return code, out.getvalue() + err.getvalue()

    def test_init_creates_config_and_inbox(self):
        self.paths.config.unlink()
        code, out = self.cli("init", "--default-path", str(self.tmp / "my-inbox"), "--claude-path", "/opt/x/claude")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.tmp / "my-inbox" / "README.md").exists())
        raw = json.loads(self.paths.config.read_text())
        self.assertEqual(raw["claude_path"], "/opt/x/claude")
        self.assertTrue(raw["path_env"].startswith("/opt/x:"))
        code, out = self.cli("init")
        self.assertIn("already exists", out)

    def test_project_lifecycle(self):
        newdir = self.tmp / "proj" / "chess bot"
        newdir.mkdir(parents=True)
        code, out = self.cli("project", "add", "chess", str(newdir), "--alias", "chess bot", "--alias", "chest",
                             "--permission-mode", "plan", "--worktree", "--default")
        self.assertEqual(code, 0, out)
        cfg = self.cfg()
        self.assertEqual(cfg.default_project, "chess")
        self.assertEqual(cfg.project("chess").aliases, ["chess bot", "chest"])
        self.assertEqual(cfg.project("chess").permission_mode, "plan")
        code, out = self.cli("project", "list")
        self.assertIn("* chess", out)
        self.assertIn("worktree", out)
        code, out = self.cli("project", "remove", "chess")
        self.assertEqual(code, 1)
        self.assertIn("default project", out)
        self.cli("project", "default", "inbox")
        code, out = self.cli("project", "remove", "chess")
        self.assertEqual(code, 0, out)
        self.assertNotIn("chess", self.cfg().projects)

    def test_bad_project_name_and_missing_folder_warning(self):
        code, out = self.cli("project", "add", "Bad Name", "/tmp")
        self.assertEqual(code, 1)
        code, out = self.cli("project", "add", "later", str(self.tmp / "not-yet"))
        self.assertEqual(code, 0)
        self.assertIn("does not exist yet", out)

    def test_stickers(self):
        code, out = self.cli("sticker", "add", "Lab", "provalume")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.cfg().stickers["lab"], "provalume")
        code, out = self.cli("sticker", "add", "x", "ghost")
        self.assertEqual(code, 1)
        self.assertIn("unknown project", out)
        code, out = self.cli("sticker", "remove", "lab")
        self.assertEqual(code, 0)

    def test_set(self):
        self.assertEqual(self.cli("set", "mode", "review")[0], 0)
        self.assertEqual(self.cfg().mode, "review")
        self.assertEqual(self.cli("set", "notify", "off")[0], 0)
        self.assertFalse(self.cfg().notify)
        self.assertEqual(self.cli("set", "linger_seconds", "3.5")[0], 0)
        code, out = self.cli("set", "mode", "warp")
        self.assertEqual(code, 1)
        code, out = self.cli("set", "projects", "x")
        self.assertIn("Unknown setting", out)
        self.assertEqual(self.cli("set", "terminal", "custom")[0], 1)  # custom needs terminal_command first
        self.assertEqual(self.cli("set", "terminal_command", '["myterm","{script}"]')[0], 0)
        self.assertEqual(self.cli("set", "terminal", "custom")[0], 0)
        self.assertEqual(self.cli("set", "terminal_command", "not json")[0], 1)

    def test_route(self):
        code, out = self.cli("route", "In orchestra, add tests")
        self.assertIn("project : orkestra", out)
        self.assertIn("heard “In orchestra”", out)
        code, out = self.cli("route", "add tests", "--sticker", "desk")
        self.assertIn("why     : sticker", out)

    @unittest.skipUnless(have("zsh"), "zsh missing")
    def test_full_local_test_command(self):
        self.write_config(dict(self.raw, terminal="custom", terminal_command=["/bin/zsh", "{script}"], keep_shell=False))
        code, out = self.cli("test", "In provalume, write a changelog entry", "--now")
        self.assertEqual(code, 0, out)
        self.assertIn("Phone would show: ✓ provalume", out)
        self.assertIn("Mac result: ✓ launched", out)
        call = self.claude_calls()[-1]
        self.assertEqual(call["argv"][-1], "write a changelog entry")
        code, out = self.cli("log")
        self.assertIn("launched", out)
        self.assertIn("provalume", out)
        jid = jobs.job_dirs(self.paths)[-1].name
        code, out = self.cli("show", jid[-6:])
        self.assertIn('"status": "launched"', out)

    def test_no_launch(self):
        code, out = self.cli("test", "anything", "--no-launch")
        self.assertEqual(code, 0)
        self.assertEqual(jobs.list_queue(self.paths), [])
        self.assertEqual(self.claude_calls(), [])

    @unittest.skipUnless(have("ssh-keygen"), "ssh-keygen missing")
    def test_add_key_and_keys(self):
        run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(self.tmp / "k")])
        pub = (self.tmp / "k.pub").read_text().strip()
        code, out = self.cli("add-key", *pub.split(), "--allow-from", "192.168.1.0/24")
        self.assertEqual(code, 0, out)
        ak = (self.home / ".ssh" / "authorized_keys").read_text()
        self.assertIn(f'command="{self.paths.receive_cmd}",restrict,from="192.168.1.0/24"', ak)
        code, out = self.cli("keys")
        self.assertIn("iphone", out)
        code, out = self.cli("add-key", "not", "a", "key")
        self.assertEqual(code, 1)
        code, out = self.cli("remove-key")
        self.assertIn("Removed 1", out)

    def test_help_lists_commands(self):
        code, out = self.cli("--help")
        for c in ("init", "project", "add-key", "doctor", "phone", "test", "route"):
            self.assertIn(c, out)


@unittest.skipUnless(have("bash"), "bash missing")
class InstallTests(TapTestCase):
    """Run the real install.sh into a throwaway home (launchd step skipped off macOS)."""

    def install(self, home):
        env = dict(os.environ, HOME=str(home), NEARSAY_ALLOW_NON_MACOS="1", NEARSAY_SKIP_LAUNCHD="1",
                   NEARSAY_PYTHON=INSTALL_PY, NEARSAY_CLAUDE=str(self.fake_claude), PATH="/usr/bin:/bin")
        env.pop("NEARSAY_HOME", None)
        return run(["bash", str(ROOT / "install.sh")], env=env, timeout=120)

    def test_install_upgrade_and_wrappers(self):
        home = self.tmp / "fresh-home"
        home.mkdir()
        cp = self.install(home)
        self.assertEqual(cp.returncode, 0, cp.stdout + cp.stderr)
        tap = home / ".nearsay"
        for f in ("bin/nearsay", "bin/nearsay-receive", "bin/nearsay-dispatch", "app/nearsay_entry.py",
                  "app/nearsay/cli.py", "config.json"):
            self.assertTrue((tap / f).exists(), f)
        self.assertTrue((home / ".local" / "bin" / "nearsay").is_symlink())
        with open(home / "Library" / "LaunchAgents" / "com.nearsay.dispatch.plist", "rb") as f:
            plist = plistlib.load(f)
        self.assertEqual(plist["QueueDirectories"], [str(tap / "queue")])
        self.assertEqual(plist["ProgramArguments"], [str(tap / "bin" / "nearsay-dispatch")])
        self.assertIn(str(self.fake_claude.parent), plist["EnvironmentVariables"]["PATH"])
        cfg = json.loads((tap / "config.json").read_text())
        self.assertEqual(cfg["claude_path"], str(self.fake_claude))
        self.assertIn("Next steps", cp.stdout)
        wrapper = (tap / "bin" / "nearsay-receive").read_text()
        self.assertIn(f"'{INSTALL_PY}' -I", wrapper)

        # Wrapper works and reports its version.
        v = run([str(tap / "bin" / "nearsay"), "--version"], env=dict(os.environ, HOME=str(home)))
        self.assertIn("nearsay 1.", v.stdout)

        # Re-running keeps the user's config.
        cfg["projects"]["inbox"]["aliases"] = ["kept"]
        (tap / "config.json").write_text(json.dumps(cfg))
        cp = self.install(home)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("Kept existing config", cp.stdout)
        self.assertEqual(json.loads((tap / "config.json").read_text())["projects"]["inbox"]["aliases"], ["kept"])

        # Receiver wrapper end to end (no SSH): queue a task from stdin.
        r = run([str(tap / "bin" / "nearsay-receive")], input="In inbox, hello from the wrapper",
                env={"HOME": str(home), "PATH": "/usr/bin:/bin", "SSH_ORIGINAL_COMMAND": "tap"})
        self.assertIn("✓ inbox", r.stdout, r.stderr)
        self.assertEqual(len(list((tap / "queue").glob("*.json"))), 1)

    def test_refuses_spaces_in_install_folder(self):
        home = self.tmp / "h"
        home.mkdir()
        env = dict(os.environ, HOME=str(home), NEARSAY_ALLOW_NON_MACOS="1", NEARSAY_SKIP_LAUNCHD="1",
                   NEARSAY_HOME=str(self.tmp / "with space"))
        cp = run(["bash", str(ROOT / "install.sh")], env=env)
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("must not contain spaces", cp.stderr)
