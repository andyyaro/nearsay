"""End to end through a real OpenSSH server, exactly as the iPhone connects.

    ssh client (stands in for Shortcuts' "Run Script Over SSH")
      -> sshd with our authorized_keys line (command=…,restrict)
      -> installed tapclaude-receive wrapper (Python 3.9, -I)
      -> queue -> installed tapclaude-dispatch wrapper
      -> generated run.command executed by zsh -> fake `claude` records its argv

Skipped automatically where sshd/ssh/zsh are not installed.
"""

import getpass
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from helpers import FAKE_CLAUDE, ROOT, have, run

sys.path.insert(0, str(ROOT))
from tapclaude import keys  # noqa: E402

SSHD = shutil.which("sshd") or "/usr/sbin/sshd"
PY = os.environ.get("TAPCLAUDE_TEST_PYTHON") or shutil.which("python3.9") or sys.executable
CAN_RUN = all(have(x) for x in (SSHD, "ssh", "ssh-keygen", "zsh"))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@unittest.skipUnless(CAN_RUN, "needs sshd, ssh, ssh-keygen and zsh")
class SshEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="tapclaude-e2e-"))
        cls.home = cls.tmp / "home"
        cls.home.mkdir()
        cls.tap = cls.home / ".tapclaude"
        cls.marker = cls.tmp / "PWNED"
        cls.claude_log = cls.tmp / "claude.jsonl"

        fake = cls.tmp / "bin" / "claude"
        fake.parent.mkdir()
        fake.write_text(FAKE_CLAUDE.format(python=sys.executable))
        fake.chmod(0o755)

        env = dict(os.environ, HOME=str(cls.home), TAPCLAUDE_ALLOW_NON_MACOS="1", TAPCLAUDE_SKIP_LAUNCHD="1",
                   TAPCLAUDE_PYTHON=PY, TAPCLAUDE_CLAUDE=str(fake), PATH="/usr/bin:/bin")
        env.pop("TAPCLAUDE_HOME", None)
        cp = run(["bash", str(ROOT / "install.sh")], env=env, timeout=120)
        assert cp.returncode == 0, cp.stdout + cp.stderr

        cfg = json.loads((cls.tap / "config.json").read_text())
        cls.proj = cls.tmp / "projects" / "orkestra"
        cls.proj.mkdir(parents=True)
        cfg["projects"]["orkestra"] = {"path": str(cls.proj), "aliases": ["orchestra runtime"]}
        cfg["stickers"] = {"desk": "orkestra"}
        cfg.update(terminal="custom", terminal_command=["/bin/zsh", "{script}"], keep_shell=False,
                   linger_seconds=0, notify=False, dedupe_seconds=0)
        (cls.tap / "config.json").write_text(json.dumps(cfg))

        run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(cls.tmp / "hostkey")])
        run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "shortcuts", "-f", str(cls.tmp / "phone")])
        run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(cls.tmp / "fenced")])
        cls.ak = cls.tmp / "authorized_keys"
        receive_cmd = cls.tap / "bin" / "tapclaude-receive"
        keys.add_key(cls.ak, receive_cmd, keys.parse_public_key((cls.tmp / "phone.pub").read_text()), "iphone")
        keys.add_key(cls.ak, receive_cmd, keys.parse_public_key((cls.tmp / "fenced.pub").read_text()), "fenced",
                     sources=["10.99.99.99/32"])

        cls.port = free_port()
        cfgfile = cls.tmp / "sshd_config"
        cfgfile.write_text("\n".join([
            f"Port {cls.port}", "ListenAddress 127.0.0.1", f"HostKey {cls.tmp / 'hostkey'}",
            f"PidFile {cls.tmp / 'sshd.pid'}", f"AuthorizedKeysFile {cls.ak}",
            "PasswordAuthentication no", "KbdInteractiveAuthentication no", "PubkeyAuthentication yes",
            "PermitRootLogin prohibit-password", "StrictModes no", "UsePAM no", "LogLevel VERBOSE",
            "AllowTcpForwarding yes", "PermitTTY yes",  # server would allow these; the key's `restrict` must block them
        ]) + "\n")
        Path("/run/sshd").mkdir(parents=True, exist_ok=True)
        cls.sshd_log = open(cls.tmp / "sshd.log", "w")
        cls.sshd = subprocess.Popen([SSHD, "-D", "-e", "-f", str(cfgfile)], stdout=cls.sshd_log, stderr=subprocess.STDOUT)
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                socket.create_connection(("127.0.0.1", cls.port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("sshd did not start: " + (cls.tmp / "sshd.log").read_text())

    @classmethod
    def tearDownClass(cls):
        cls.sshd.terminate()
        cls.sshd.wait(5)
        cls.sshd_log.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def ssh(self, script, stdin="", key="phone", extra=()):
        argv = ["ssh", "-p", str(self.port), "-i", str(self.tmp / key), "-o", "IdentitiesOnly=yes",
                "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                "-o", "LogLevel=ERROR", *extra, f"{getpass.getuser()}@127.0.0.1", script]
        return run(argv, input=stdin, timeout=30)

    def dispatch(self):
        env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin", "FAKE_CLAUDE_LOG": str(self.claude_log)}
        return run([str(self.tap / "bin" / "tapclaude-dispatch")], env=env, timeout=60)

    def calls(self):
        if not self.claude_log.exists():
            return []
        return [json.loads(x) for x in self.claude_log.read_text().splitlines() if x.strip()]

    def queue(self):
        return sorted((self.tap / "queue").glob("*.json"))

    def test_1_ping(self):
        cp = self.ssh("ping")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("is reachable", cp.stdout)

    def test_2_full_pipeline_with_hostile_text(self):
        task = "add tests; touch {m} && echo $(touch {m}) `touch {m}` 'quoted' \"double\" éè \U0001f680".format(m=self.marker)
        cp = self.ssh("tap desk", stdin=task + "\n")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("✓ orkestra", cp.stdout)
        self.assertEqual(len(self.queue()), 1)
        d = self.dispatch()
        self.assertEqual(d.returncode, 0, d.stdout + d.stderr)
        self.assertEqual(self.queue(), [])
        call = self.calls()[-1]
        self.assertEqual(call["argv"][-1], task)
        self.assertEqual(Path(call["cwd"]).resolve(), self.proj.resolve())
        self.assertIn("--remote-control", call["argv"])
        self.assertFalse(self.marker.exists())

    def test_3_spoken_routing_over_ssh(self):
        cp = self.ssh("tap", stdin="In Orchestra runtime, refactor the scheduler")
        self.assertIn("✓ orkestra", cp.stdout)
        self.dispatch()
        self.assertEqual(self.calls()[-1]["argv"][-1], "refactor the scheduler")

    def test_4_script_field_cannot_run_commands(self):
        for script in (f"touch {self.marker}", f"tap; touch {self.marker}", f"$(touch {self.marker})",
                       f"tap && touch {self.marker}", f"tap `touch {self.marker}`", "id", "bash -i", "cat /etc/passwd"):
            cp = self.ssh(script, stdin="x")
            self.assertTrue(cp.stdout.startswith("✗"), (script, cp.stdout, cp.stderr))
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.queue(), [])

    def test_5_no_terminal_and_no_forwarding(self):
        cp = self.ssh("ping", extra=["-tt"])
        self.assertIn("PTY allocation request failed", cp.stderr)  # no interactive terminal for this key
        self.assertNotIn("$", cp.stdout)
        log = (self.tmp / "sshd.log").read_text()
        self.assertIn("forced-command (key-option)", log)  # sshd confirms the key is pinned to the receiver
        cp = self.ssh("ping", extra=["-o", "ExitOnForwardFailure=yes", "-R", "0:127.0.0.1:22"])
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("forwarding failed", cp.stderr.lower())

    def test_6_from_restriction_blocks_other_addresses(self):
        cp = self.ssh("ping", key="fenced")
        self.assertEqual(cp.returncode, 255)
        self.assertIn("Permission denied", cp.stderr)


if __name__ == "__main__":
    unittest.main()
