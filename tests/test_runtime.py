"""Offline checks for submission gates, public status and installation safety."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


lite = module("lite_subject", ROOT / "lite.py")
installer = module("installer_subject", ROOT / "tools" / "install.py")


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.root = Path(self.temp.name)
        lite.EVENTS.clear()
        lite.PUBLIC_PROFILE.clear()
        lite.STATUS_PATH = self.root / "status.json"

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, *args):
        with patch("sys.argv", ["lite.py", *args]), contextlib.redirect_stdout(io.StringIO()):
            return lite.main()

    def test_submission_requires_explicit_flag(self):
        for command in ("checkin", "scheduled"):
            with self.subTest(command=command), self.assertRaises(lite.ToolError) as error:
                self.invoke(command)
            self.assertEqual(error.exception.reason, "explicit_submit_flag_required")

    def test_disabled_schedule_never_opens_state_or_transport(self):
        config = self.root / "config.json"
        config.write_text(json.dumps({"automation_enabled": False}), encoding="utf-8")
        with patch.object(lite, "DirectTransport") as transport, patch.object(lite, "State") as state:
            self.assertEqual(self.invoke("scheduled", "--submit", "--config", str(config)), 0)
            transport.assert_not_called()
            state.assert_not_called()
        self.assertEqual(lite.EVENTS[-1]["reason"], "automation_disabled")

    def test_enabled_schedule_uses_upstream_checkin_mode(self):
        config = self.root / "config.json"
        config.write_text(json.dumps({"automation_enabled": True,
            "student_id": "2099999999999", "password": "Synthetic-Only"}), encoding="utf-8")
        with patch.object(lite, "run_account", return_value={"result": "confirmed"}) as runner:
            self.assertEqual(self.invoke("scheduled", "--submit", "--config", str(config),
                                         "--data-dir", str(self.root / "state")), 0)
        self.assertEqual(runner.call_args.args[1], "checkin")

    def test_public_status_excludes_secrets(self):
        lite.PUBLIC_PROFILE.update(kind="prepare", automationEnabled=True)
        secrets = ["Synthetic-Password", "2099999999999", "Synthetic-Fingerprint", "Synthetic-Cookie"]
        lite.EVENTS.append(dict(time="2026-10-22T00:30:00+08:00", event="result",
            result="dry_run_ready", **dict(zip(("password", "student_id", "browser_fingerprint", "cookies"), secrets))))
        lite.write_public_status()
        raw = lite.STATUS_PATH.read_text(encoding="utf-8")
        for secret in secrets:
            self.assertNotIn(secret, raw)
        self.assertNotIn("firstConfirmedAt", json.loads(raw))

    def test_confirmation_replaces_pending_record_and_caps_history(self):
        lite.STATUS_PATH.write_text(json.dumps({"history": [{"result": "auth_ready"}] * 8}), encoding="utf-8")
        lite.EVENTS.extend([
            dict(time="2026-10-22T21:01:00+08:00", event="record_read",
                 businessDate="2026-10-22", status="PENDING", abnormalFlag=False),
            dict(time="2026-10-22T21:01:05+08:00", event="result", result="confirmed",
                 businessDate="2026-10-22", status="CHECKED_IN", abnormalFlag=False)])
        lite.write_public_status()
        result = json.loads(lite.STATUS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(result["lastRecord"]["status"], "CHECKED_IN")
        self.assertIs(result["lastRecord"]["abnormalFlag"], False)
        self.assertEqual(result["firstConfirmedAt"], "2026-10-22T21:01:05+08:00")
        self.assertEqual(len(result["history"]), 8)


class InstallerTests(unittest.TestCase):
    def test_installer_preserves_cron_and_does_not_enable_on_failed_prepare(self):
        for ready in (False, True):
            with self.subTest(ready=ready), tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
                root = Path(directory)
                (root / "web").mkdir()
                (root / "web" / "index.html").write_text('<html data-app="moonuestc-openwrt">')
                (root / "run.sh").touch()
                (root / "config.json").write_text(json.dumps({"run_at": "21:01", "automation_enabled": False,
                    "student_id": "2099999999999", "password": "Synthetic-Only"}))
                old = "0 4 * * * /usr/bin/other-job\n0 22 * * * /old/run.sh # uestc-night-checkin-lite\n"
                installed = []

                def run(argv, **kwargs):
                    if argv == ["crontab", "-l"]:
                        return subprocess.CompletedProcess(argv, 0, old, "")
                    if "prepare" in argv:
                        if not ready:
                            raise subprocess.CalledProcessError(2, argv)
                        target = Path(argv[argv.index("--status-path") + 1])
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(json.dumps({"lastRun": {"result": "dry_run_ready"}}))
                    if argv[0] == "crontab":
                        installed.append(kwargs["input"])
                    return subprocess.CompletedProcess(argv, 0)

                original_exists = Path.exists

                def exists(path):
                    return str(path) in {str(Path("/etc/init.d/uhttpd")), str(Path("/etc/init.d/rpcd"))} or original_exists(path)

                with patch.object(installer, "ROOT", root), patch.object(installer, "WEB", root / "www"), \
                     patch.object(installer, "CGI", root / "cgi-bin" / "moonuestc-api"), \
                     patch.object(installer.subprocess, "run", side_effect=run), \
                     patch.object(Path, "exists", exists), contextlib.redirect_stdout(io.StringIO()):
                    if ready:
                        installer.main()
                    else:
                        with self.assertRaises(subprocess.CalledProcessError):
                            installer.main()
                config = json.loads((root / "config.json").read_text())
                self.assertIs(config["automation_enabled"], False)
                if ready:
                    self.assertIn("0 4 * * * /usr/bin/other-job\n", installed[0])
                    self.assertNotIn("# moonuestc-openwrt", installed[0])
                    self.assertNotIn("/old/run.sh", installed[0])
                    self.assertFalse(json.loads((root / "profiles" / "me.json").read_text())["automation_enabled"])
                    cgi = (root / "cgi-bin" / "moonuestc-api").read_text()
                    self.assertIn(repr(str(root)), cgi)
                    self.assertIn("from account_api import cgi_main", cgi)
                else:
                    self.assertEqual(installed, [])

    def test_upgrade_preserves_profiles_and_does_not_request_school(self):
        import account_store
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            root = Path(directory)
            (root / "web").mkdir()
            (root / "web" / "index.html").write_text('<html data-app="moonuestc-openwrt">')
            (root / "run.sh").touch()
            profile = {"id": "me", "label": "Synthetic", "student_id": "2099999999999",
                       "run_at": "21:01", "automation_enabled": True}
            account_store.atomic_json(root / "profiles" / "index.json", ["me"])
            account_store.atomic_json(root / "profiles" / "me.json", profile)
            account_store.atomic_json(root / "state" / "sentinel.json", {"keep": True})
            calls = []

            def run(argv, **kwargs):
                calls.append((argv, kwargs))
                self.assertNotIn("prepare", argv)
                if argv == ["crontab", "-l"]:
                    return subprocess.CompletedProcess(argv, 0, "0 5 * * * unrelated\n", "")
                return subprocess.CompletedProcess(argv, 0)

            exists = Path.exists
            def available(path):
                return str(path) in {str(Path("/etc/init.d/uhttpd")), str(Path("/etc/init.d/rpcd"))} or exists(path)

            with patch.object(installer, "ROOT", root), patch.object(installer, "WEB", root / "www"), \
                 patch.object(installer, "CGI", root / "cgi-bin" / "moonuestc-api"), \
                 patch.object(installer.subprocess, "run", side_effect=run), \
                 patch.object(Path, "exists", available), contextlib.redirect_stdout(io.StringIO()):
                installer.main()
            self.assertEqual(json.loads((root / "profiles" / "me.json").read_text()), profile)
            self.assertEqual(json.loads((root / "state" / "sentinel.json").read_text()), {"keep": True})
            cron = next(kwargs["input"] for argv, kwargs in calls if argv == ["crontab", "-"])
            self.assertIn("1 21 * * *", cron)
            self.assertIn("0 5 * * * unrelated", cron)


if __name__ == "__main__":
    unittest.main()
