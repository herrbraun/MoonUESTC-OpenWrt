"""Offline checks for submission gates and sanitized public status."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
