"""Synthetic account/API tests. Never contact the school or router."""
import copy
import contextlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from account_store import AccountStore, StoreError, atomic_json
import account_api
import multi


class AccountsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent.parent.parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = dict(student_id="209900000001", password="synthetic-secret",
            browser_fingerprint="f" * 32, run_at="21:01", automation_enabled=True,
            location=dict(name="测试位置", latitude=30.6, longitude=104.0))
        atomic_json(self.root / "config.json", self.original)
        self.public = self.root / "public"
        atomic_json(self.public / "status.json", {"auth": {"ok": True}, "history": [{"result": "confirmed"}]})
        self.crons = []
        self.store = AccountStore(self.root, self.public, self.crons.append)
        self.store.migrate()

    def fields(self, **extra):
        return dict(label="测试账号", **self.original) | extra

    def test_new_account_draft_starts_paused(self):
        self.assertIs(self.store.editable()["automation_enabled"], False)

    def test_migration_and_secret_redaction(self):
        self.store.migrate()
        self.assertEqual(self.store.ids(), ["me"])
        self.assertEqual(self.store.get("me")["password"], self.original["password"])
        self.assertEqual(json.loads(self.store.status_path("me").read_text(encoding="utf-8"))["history"][0]["result"], "confirmed")
        public = (self.public / "accounts.json").read_text(encoding="utf-8")
        for secret in (self.original["password"], self.original["browser_fingerprint"], self.original["student_id"]):
            self.assertNotIn(secret, public)
        dto = self.store.editable("me")
        self.assertNotIn("password", dto)
        self.assertNotIn("browser_fingerprint", dto)

    def test_crud_blank_secrets_and_identity_isolation(self):
        self.store.save(self.fields(id="me", password="", browser_fingerprint=""))
        self.assertEqual(self.store.get("me")["password"], self.original["password"])
        with self.assertRaises(StoreError):
            self.store.save(self.fields())
        created = self.store.save(self.fields(student_id="209900000002", automation_enabled=False))
        self.assertEqual(len(self.store.ids()), 2)
        self.assertFalse(json.loads(self.store.status_path(created["id"]).read_text(encoding="utf-8")).get("auth"))
        self.store.save(self.fields(id="me", student_id="209900000003"))
        status = json.loads(self.store.status_path("me").read_text(encoding="utf-8"))
        self.assertEqual(status["history"], [])
        self.assertNotIn("auth", status)
        self.store.delete(created["id"])
        self.assertEqual(self.store.ids(), ["me"])
        self.assertFalse(self.store.status_path(created["id"]).exists())

    def test_credential_change_invalidates_auth(self):
        self.store.save(self.fields(id="me", password="new-synthetic"))
        state = json.loads(self.store.status_path("me").read_text(encoding="utf-8"))
        self.assertNotIn("auth", state)
        self.assertEqual(len(state["history"]), 1)

    def test_schedule_update_rollback(self):
        before = self.store.get("me")
        def fail(_):
            raise OSError("synthetic")
        self.store.schedule_callback = fail
        with self.assertRaises(StoreError):
            self.store.save(self.fields(id="me", label="changed"))
        self.assertEqual(self.store.get("me"), before)
        with self.assertRaises(StoreError):
            self.store.save(self.fields(student_id="209900000004"))
        self.assertEqual(self.store.ids(), ["me"])

    def test_runner_failure_does_not_skip_later_accounts(self):
        accounts = [{"id": "me"}, {"id": "other"}]
        with patch.object(multi, "run_profile", side_effect=[OSError("synthetic"), 0]) as worker:
            pauses = []
            self.assertEqual(multi.run_selected(self.store, accounts, "diagnose", pauses.append), 2)
        self.assertEqual(worker.call_count, 2)
        self.assertEqual(pauses, [20])

    def test_spawn_failure_clears_busy(self):
        with patch.object(account_api.subprocess, "Popen", side_effect=OSError("synthetic")):
            with self.assertRaises(StoreError):
                account_api.dispatch({"action": "diagnose", "id": "me"}, self.store)
        self.assertNotIn("busy", json.loads(self.store.status_path("me").read_text(encoding="utf-8")))

    def test_nearby_schedule_waits_for_active_batch(self):
        attempts = []
        @contextlib.contextmanager
        def lock(_):
            attempts.append(1)
            if len(attempts) < 3:
                from moonuestc.errors import ToolError
                raise ToolError("another_run_active", "lock")
            yield
        with patch.object(multi, "execution_lock", lock), patch.object(multi.time, "sleep") as pause:
            with multi.scheduler_lock(self.root, 30):
                self.assertEqual(len(attempts), 3)
        self.assertEqual(pause.call_count, 2)

    def test_due_batch_uses_start_minute_and_scheduled_gate(self):
        import datetime
        stamp = datetime.datetime(2026, 10, 22, 21, 1)
        with patch.object(multi, "AccountStore", return_value=self.store), \
             patch.object(multi, "now", return_value=stamp), \
             patch.object(multi, "run_selected", return_value=0) as run, \
             patch.object(sys, "argv", ["multi.py", "checkin", "--due", "--submit"]):
            self.assertEqual(multi.main(), 0)
        self.assertEqual([a["id"] for a in run.call_args.args[1]], ["me"])
        self.assertEqual(run.call_args.args[2], "scheduled")
        self.store.save(self.fields(id="me", automation_enabled=False))
        with patch.object(multi, "AccountStore", return_value=self.store), \
             patch.object(multi, "now", return_value=stamp), \
             patch.object(multi, "run_selected", return_value=0) as run, \
             patch.object(sys, "argv", ["multi.py", "checkin", "--due", "--submit"]):
            self.assertEqual(multi.main(), 0)
        self.assertEqual(run.call_args.args[1], [])

    def test_empty_install_does_not_require_a_legacy_account(self):
        store = AccountStore(self.root / "empty", self.public / "empty", lambda _: None)
        store.migrate()
        self.assertEqual(store.ids(), [])
        self.assertEqual(json.loads((store.public / "accounts.json").read_text(encoding="utf-8")), {"accounts": []})

    def test_multi_checkin_requires_explicit_submit(self):
        with patch.object(sys, "argv", ["multi.py", "checkin", "--due"]), self.assertRaises(StoreError):
            multi.main()


if __name__ == "__main__":
    unittest.main()
