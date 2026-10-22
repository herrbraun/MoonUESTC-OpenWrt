"""Sequential one-shot runner. Existing per-student claims and cookies stay isolated."""
import argparse
import contextlib
import json
import os
import sys
import time
from pathlib import Path

import lite
from account_store import AccountStore, StoreError, atomic_json
from moonuestc.errors import ToolError
from moonuestc.policy import now
from moonuestc.state import execution_lock

HERE = Path(__file__).resolve().parent


@contextlib.contextmanager
def scheduler_lock(root, wait_seconds):
    """A nearby scheduled batch waits for the current batch instead of losing its run."""
    deadline = time.monotonic() + wait_seconds
    while True:
        lock = execution_lock(root / "scheduler")
        try:
            lock.__enter__()
            break
        except ToolError as error:
            if error.reason != "another_run_active" or time.monotonic() >= deadline:
                raise
            time.sleep(1)
    try:
        yield
    finally:
        lock.__exit__(None, None, None)


def run_profile(store, aid, mode):
    account = store.get(aid)
    lite.EVENTS.clear()
    lite.PUBLIC_PROFILE.clear()
    lite.STATUS_PATH = store.status_path(aid)
    lite.PUBLIC_PROFILE.update(kind=mode, runAt=account.get("run_at", "21:01"),
        automationEnabled=account.get("automation_enabled") is True,
        location={"name": account.get("location", {}).get("name", "未配置"), "radiusMeter": account.get("location_radius_meter")})
    saved_argv = sys.argv
    sys.argv = ["lite.py", mode, "--config", str(store.path(aid)), "--data-dir", str(store.root / "state"),
                "--status-path", str(store.status_path(aid))] + (["--submit"] if mode in ("checkin", "scheduled") else [])
    try:
        return lite.main()
    except ToolError as error:
        lite.emit("result", result="error", reason=error.reason, stage=error.stage)
        return 2
    except Exception:
        lite.emit("result", result="error", reason="local_runtime_error", stage="local")
        return 2
    finally:
        sys.argv = saved_argv
        try:
            lite.write_public_status()
        except (OSError, ValueError):
            lite.emit("status_publish_failed", result="error")


def clear_busy(store, aid):
    path = store.status_path(aid)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.pop("busy", None):
            atomic_json(path, state, 0o644)
    except (OSError, ValueError):
        pass


def run_selected(store, accounts, mode, pause=time.sleep):
    failed = False
    for index, account in enumerate(accounts):
        if index:
            pause(20)
        try:
            code = run_profile(store, account["id"], mode)
        except Exception:
            code = 2
        finally:
            clear_busy(store, account["id"])
        failed = failed or bool(code)
    return 2 if failed else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("diagnose", "prepare", "checkin"))
    parser.add_argument("--account")
    parser.add_argument("--due", action="store_true")
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()
    if args.mode == "checkin" and not args.submit:
        raise StoreError("explicit_submit_flag_required")
    os.umask(0o077)
    store = AccountStore()
    stamp = now()
    try:
        with scheduler_lock(store.root, 1800 if args.due else 5):
            accounts = [a for a in store.all() if (not args.account or a["id"] == args.account)]
            if args.account and not accounts:
                raise StoreError("账号不存在", 404)
            if args.due:
                accounts = [a for a in accounts if a.get("automation_enabled") is True and a.get("run_at") == stamp.strftime("%H:%M")]
            mode = "scheduled" if args.due and args.mode == "checkin" else args.mode
            code = run_selected(store, accounts, mode)
            store.publish()
            return code
    finally:
        if args.mode == "diagnose" and args.account:
            clear_busy(store, args.account)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (StoreError, ToolError) as error:
        print(json.dumps({"result": "error", "reason": str(error)}))
        raise SystemExit(2)
