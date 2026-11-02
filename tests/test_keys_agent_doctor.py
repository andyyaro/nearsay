import os
import plistlib
import stat
import unittest
from pathlib import Path

from helpers import RecordingRunner, TapTestCase, have, run

from nearsay import doctor, keys, launchagent
from nearsay.keys import KeyError_


def gen_key(tmp: Path, kind: str = "ed25519") -> str:
    path = tmp / f"k_{kind}"
    args = ["ssh-keygen", "-q", "-t", kind, "-N", "", "-C", "iphone@shortcuts", "-f", str(path)]
    if kind == "rsa":
        args[4:4] = ["-b", "2048"]
    cp = run(args)
    assert cp.returncode == 0, cp.stderr
    return (tmp / f"k_{kind}.pub").read_text().strip()


@unittest.skipUnless(have("ssh-keygen"), "ssh-keygen missing")
class KeyTests(TapTestCase):
    def setUp(self):
        super().setUp()
        self.ak = self.tmp / "home" / ".ssh" / "authorized_keys"
        self.pub = gen_key(self.tmp)

    def test_parse_valid_keys(self):
        k = keys.parse_public_key(self.pub)
        self.assertEqual(k.type, "ssh-ed25519")
        self.assertEqual(keys.parse_public_key(gen_key(self.tmp, "rsa")).type, "ssh-rsa")
        self.assertEqual(keys.parse_public_key("\n  " + self.pub + "  \n").blob, k.blob)

    def test_rejects_bad_input(self):
        priv = (self.tmp / "k_ed25519").read_text()
        cases = {
            priv: "PRIVATE key",
            "": "No key given",
            "ssh-ed25519": "looks like",
            "ssh-dss AAAAB3NzaC1kc3MAAACBAP": "Unsupported key type",
            "ssh-ed25519 !!!notbase64": "damaged",
            "ssh-rsa " + self.pub.split()[1]: "Key data says",
            "ssh-ed25519 " + self.pub.split()[1][:28]: "cut off",
            self.pub + "\n" + self.pub: "exactly one",
        }
        for text, needle in cases.items():
            with self.assertRaises(KeyError_, msg=text[:30]) as ctx:
                keys.parse_public_key(text)
            self.assertIn(needle, str(ctx.exception))

    def test_line_format(self):
        k = keys.parse_public_key(self.pub)
        line = keys.build_line(Path("/Users/a/.nearsay/bin/nearsay-receive"), k, "iphone", ["192.168.1.7/24"])
        self.assertTrue(line.startswith('command="/Users/a/.nearsay/bin/nearsay-receive",restrict,'
                                        'from="192.168.1.0/24" ssh-ed25519 '))
        self.assertTrue(line.endswith(" nearsay:iphone"))
        with self.assertRaises(KeyError_):
            keys.build_line(Path('/bad"path'), k, "iphone")
        with self.assertRaises(KeyError_):
            keys.build_line(Path("/ok"), k, "bad label")
        with self.assertRaises(KeyError_):
            keys.validate_sources(["home-network"])

    def test_add_is_idempotent_and_preserves_other_lines(self):
        self.ak.parent.mkdir(parents=True)
        other = gen_key(self.tmp, "rsa")
        self.ak.write_text("# my laptop\n" + other + " laptop\n")
        k = keys.parse_public_key(self.pub)
        keys.add_key(self.ak, Path("/r"), k, "iphone")
        keys.add_key(self.ak, Path("/r"), k, "iphone")
        lines = self.ak.read_text().splitlines()
        self.assertEqual(lines[:2], ["# my laptop", other + " laptop"])
        self.assertEqual(sum("nearsay:iphone" in ln for ln in lines), 1)
        self.assertEqual(stat.S_IMODE(os.stat(self.ak).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.ak.parent).st_mode), 0o700)
        self.assertEqual(keys.list_keys(self.ak)[0][:2], ("iphone", "ssh-ed25519"))

    def test_refuses_to_shadow_an_unrestricted_copy(self):
        self.ak.parent.mkdir(parents=True)
        self.ak.write_text(self.pub + "\n")
        k = keys.parse_public_key(self.pub)
        with self.assertRaises(KeyError_) as ctx:
            keys.add_key(self.ak, Path("/r"), k)
        self.assertIn("WITHOUT restrictions", str(ctx.exception))
        _, warnings = keys.add_key(self.ak, Path("/r"), k, force=True)
        self.assertTrue(warnings)
        self.assertEqual(len(self.ak.read_text().splitlines()), 1)
        self.assertIn("restrict", self.ak.read_text())

    def test_relabel_moves_key(self):
        k = keys.parse_public_key(self.pub)
        keys.add_key(self.ak, Path("/r"), k, "old")
        _, warnings = keys.add_key(self.ak, Path("/r"), k, "new")
        self.assertEqual([e[0] for e in keys.list_keys(self.ak)], ["new"])
        self.assertTrue(warnings)

    def test_remove(self):
        k = keys.parse_public_key(self.pub)
        keys.add_key(self.ak, Path("/r"), k, "iphone")
        keys.add_key(self.ak, Path("/r"), keys.parse_public_key(gen_key(self.tmp, "rsa")), "ipad")
        self.assertEqual(keys.remove_keys(self.ak, "ipad"), 1)
        self.assertEqual(keys.remove_keys(self.ak), 1)
        self.assertEqual(keys.list_keys(self.ak), [])


class LaunchAgentTests(TapTestCase):
    def test_plist_contents(self):
        d = launchagent.build(self.paths, "/a:/b")
        self.assertEqual(d["Label"], "com.nearsay.dispatch")
        self.assertEqual(d["QueueDirectories"], [str(self.paths.queue)])
        self.assertTrue(os.path.isabs(d["ProgramArguments"][0]))
        self.assertNotIn("~", d["QueueDirectories"][0])
        out = self.tmp / "agent.plist"
        launchagent.write(out, d)
        with open(out, "rb") as f:
            self.assertEqual(plistlib.load(f), d)

    def test_rejects_relative_paths(self):
        d = launchagent.build(self.paths, "/a")
        d["QueueDirectories"] = ["~/.nearsay/queue"]
        with self.assertRaises(ValueError):
            launchagent.write(self.tmp / "x.plist", d)

    def test_launchctl_calls(self):
        r = RecordingRunner()
        launchagent.load(r, Path("/p.plist"))
        uid = os.getuid()
        self.assertEqual([c["argv"] for c in r.calls], [
            ["launchctl", "bootout", f"gui/{uid}/com.nearsay.dispatch"],
            ["launchctl", "bootstrap", f"gui/{uid}", "/p.plist"],
        ])
        self.assertTrue(launchagent.is_loaded(RecordingRunner(returncode=0)))
        self.assertFalse(launchagent.is_loaded(RecordingRunner(returncode=113)))

    def test_path_env_dedup(self):
        parts = launchagent.default_path_env(["/x", "/usr/bin"]).split(":")
        self.assertEqual(parts[0], "/x")
        self.assertEqual(parts.count("/usr/bin"), 1)
        self.assertIn("/opt/homebrew/bin", parts)


class DoctorTests(TapTestCase):
    def checks(self, port=True, runner=None):
        home = self.tmp / "home"
        return {c.title: c for c in doctor.run_checks(self.paths, runner or RecordingRunner(stdout="2.1.300 (Claude Code)"),
                                                     home=home, is_macos=True, port_probe=lambda h, p: port)}

    def test_reports_the_setup_gaps(self):
        c = self.checks(port=False)
        self.assertEqual(c["Remote Login (SSH)"].status, doctor.FAIL)
        self.assertEqual(c["Phone key"].status, doctor.FAIL)
        self.assertIn("add-key", c["Phone key"].fix)
        self.assertEqual(c["Claude Code"].status, doctor.OK)
        self.assertEqual(c["Project olympus"].status, doctor.OK)
        text = doctor.format_checks(list(c.values()))
        self.assertIn("fix: System Settings", text)

    def test_project_problems(self):
        raw = dict(self.raw)
        raw["projects"] = dict(raw["projects"])
        raw["projects"]["orkestra"] = dict(raw["projects"]["orkestra"], permission_mode="bypassPermissions")
        raw["projects"]["provalume"] = dict(raw["projects"]["provalume"], worktree=True)
        self.write_config(raw)
        self.cfg().project("ev-model").path.rmdir()
        c = self.checks()
        self.assertEqual(c["Project orkestra"].status, doctor.WARN)
        self.assertEqual(c["Project provalume"].status, doctor.FAIL)
        self.assertIn("not a git repository", c["Project provalume"].detail)
        self.assertEqual(c["Project ev-model"].status, doctor.FAIL)

    @unittest.skipUnless(have("ssh-keygen"), "ssh-keygen missing")
    def test_key_present_and_permissions(self):
        home = self.tmp / "home"
        ak = home / ".ssh" / "authorized_keys"
        keys.add_key(ak, self.paths.receive_cmd, keys.parse_public_key(gen_key(self.tmp)))
        c = self.checks()
        self.assertEqual(c["Phone key"].status, doctor.OK)
        self.assertNotIn("Phone key target", c)
        os.chmod(ak, 0o666)
        c = self.checks()
        self.assertEqual(c["Permissions on authorized_keys"].status, doctor.FAIL)

    def test_missing_claude(self):
        self.fake_claude.unlink()
        self.assertEqual(self.checks()["Claude Code"].status, doctor.FAIL)

    def test_config_missing(self):
        self.paths.config.unlink()
        c = self.checks()
        self.assertEqual(c["Config"].status, doctor.FAIL)
        self.assertIn("nearsay init", c["Config"].fix)
