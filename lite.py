"""Small one-shot CLI. Standard library + PyCryptodome; no web server."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import ssl
import sys
import urllib.request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "vendor"))
from moonuestc.client import LOGIN, School, encrypt_password, login_fields
from moonuestc.errors import ToolError
from moonuestc.diagnostics import error_details
from moonuestc.policy import clock_minutes, now
from moonuestc.runner import run_account
from moonuestc.state import State, execution_lock
from moonuestc.transport import NoRedirect, Transport

EVENTS = []
STATUS_PATH = None
PUBLIC_PROFILE = {}


def emit(event, **values):
    item = {"time": now().isoformat(timespec="seconds"), "event": event, **values}
    EVENTS.append(item)
    print(json.dumps(item, ensure_ascii=False, allow_nan=False), flush=True)


def write_public_status():
    """Publish only allowlisted status metadata, never config, cookies, or school bodies."""
    if STATUS_PATH is None:
        return
    previous = {}
    try:
        if STATUS_PATH.exists() and STATUS_PATH.stat().st_size < 65536:
            previous = json.loads(STATUS_PATH.read_text())
    except (OSError, ValueError):
        pass
    snapshot = {key: previous[key] for key in (
        "lastRecord", "auth", "firstConfirmedAt", "history", "window") if key in previous}
    stamp = now().isoformat(timespec="seconds")
    snapshot.update(schema=1, updatedAt=stamp, runAt=PUBLIC_PROFILE.get("runAt", "21:01"),
                    automationEnabled=PUBLIC_PROFILE.get("automationEnabled", False),
                    location=PUBLIC_PROFILE.get("location", {}))
    for event in EVENTS:
        if event["event"] == "stage_ok" and event.get("stage") in ("cas_authenticated", "session_reused"):
            snapshot["auth"] = {"ok": True, "checkedAt": event["time"]}
        if event["event"] == "record_read":
            snapshot["lastRecord"] = {key: event[key] for key in ("businessDate", "status", "abnormalFlag") if key in event}
            snapshot["lastRecord"]["observedAt"] = event["time"]
        if event["event"] == "result":
            result = {key: event[key] for key in ("time", "result", "reason", "stage", "status", "businessDate") if key in event}
            result["kind"] = PUBLIC_PROFILE.get("kind", "diagnose")
            snapshot["lastRun"] = result
            snapshot["history"] = (snapshot.get("history", []) + [result])[-8:]
            if isinstance(event.get("checkinWindow"), dict):
                snapshot["window"] = {key: event["checkinWindow"][key] for key in ("start", "end") if key in event["checkinWindow"]}
            if event.get("result") == "confirmed":
                snapshot.setdefault("firstConfirmedAt", event["time"])
            if event.get("result") in ("confirmed", "already_recorded") and event.get("status"):
                snapshot["lastRecord"] = {"businessDate": event.get("businessDate"),
                    "status": event["status"], "observedAt": event["time"],
                    "abnormalFlag": event.get("abnormalFlag", snapshot.get("lastRecord", {}).get("abnormalFlag"))}
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATUS_PATH.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(snapshot, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    os.chmod(temporary, 0o644)
    os.replace(temporary, STATUS_PATH)


class DirectTransport(Transport):
    def __init__(self, user_agent, cookie_path):
        super().__init__(user_agent, cookie_path, timeout=12)
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect(),
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()))

    def fingerprint(self, value):
        # No fabricated trusted-browser value. A missing value is an actual no-cookie trial.
        if value:
            super().fingerprint(value)


def main():
    global STATUS_PATH
    parser = argparse.ArgumentParser(description="晚安成电精简版；默认只读诊断")
    parser.add_argument("command", choices=("selftest", "probe", "diagnose", "locations", "prepare", "checkin", "scheduled"), nargs="?", default="diagnose")
    parser.add_argument("--config", type=Path, default=HERE / "config.json")
    parser.add_argument("--data-dir", type=Path, default=HERE / "state")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--status-path", type=Path, help="Write a sanitized static dashboard snapshot")
    args = parser.parse_args()
    STATUS_PATH = args.status_path
    PUBLIC_PROFILE["kind"] = args.command
    os.umask(0o077)
    if args.command == "selftest":
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
        salt, pwd = "0123456789ABCDEF", "Synthetic-Test-Only"
        cipher = base64.b64decode(encrypt_password(pwd, salt))
        result = unpad(AES.new(salt.encode(), AES.MODE_CBC, b"\0" * 16).decrypt(cipher), 16)
        assert result[64:] == pwd.encode()
        emit("selftest", result="passed", schoolRequests=0, webDependencies=False,
             python=sys.version.split()[0])
        return 0
    if args.command == "probe":
        transport = DirectTransport("Mozilla/5.0", args.data_dir / "unused.lwp")
        response = transport.request("GET", LOGIN, stage="cas_page")
        fields = login_fields(response.text)
        emit("probe", result="passed", httpStatus=response.status,
             loginFieldsPresent=bool(fields), credentialSubmissions=0)
        return 0
    if args.command in ("checkin", "scheduled") and not args.submit:
        raise ToolError("explicit_submit_flag_required", "local")
    try:
        account = json.loads(args.config.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise ToolError("account_configuration_missing", "config") from None
    if not isinstance(account, dict):
        raise ToolError("account_configuration_invalid", "config")
    clock_minutes(account.get("run_at", "21:01"))
    if type(account.get("automation_enabled", False)) is not bool:
        raise ToolError("invalid_automation_flag", "config")
    location = account.get("location") or {}
    if not isinstance(location, dict):
        raise ToolError("account_configuration_invalid", "config")
    PUBLIC_PROFILE.update(runAt=account.get("run_at", "21:01"),
                          automationEnabled=account.get("automation_enabled") is True,
                          location={"name": location.get("name", "未配置"),
                                    "radiusMeter": account.get("location_radius_meter")})
    if args.command == "scheduled" and account.get("automation_enabled") is not True:
        emit("result", result="skipped", reason="automation_disabled")
        return 0
    student = account.get("student_id")
    if (not isinstance(student, str) or not re.fullmatch(r"\d{8,20}", student)
            or not isinstance(account.get("password"), str) or not account["password"]):
        raise ToolError("account_configuration_invalid", "config")
    account.setdefault("id", "me")
    account.setdefault("browser_fingerprint", "")
    account.setdefault("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36")
    with execution_lock(args.data_dir):
        state = State(args.data_dir)
        try:
            if args.command == "locations":
                from moonuestc.runner import account_key, cookie_path
                transport = DirectTransport(account["user_agent"], cookie_path(args.data_dir, account))
                school = School(transport, account,
                                budget=lambda: state.login_budget(account_key(account), now().date().isoformat()), emit=emit)
                try:
                    school.connect()
                    rows = school.locations()
                    safe = [{key: row.get(key) for key in ("locationName", "latitude", "longitude", "radiusMeter")}
                            for row in rows if isinstance(row, dict)]
                    emit("locations", locations=safe, submitted=False)
                finally:
                    transport.save()
                return 0
            mode = "checkin" if args.command == "scheduled" else args.command
            result = run_account(account, mode, state, args.data_dir,
                                 emit=emit, transport_factory=DirectTransport)
        except ToolError as error:
            emit("result", result="error", **error_details(error, account))
            return 2
        finally:
            state.close()
    emit("result", **result)
    return 0 if result["result"] in {"auth_ready", "dry_run_ready", "confirmed", "already_recorded"} else 2


if __name__ == "__main__":
    exit_code = 2
    try:
        exit_code = main()
    except ToolError as error:
        emit("result", result="error", reason=error.reason, stage=error.stage)
    except Exception as error:
        # Do not emit exception text, request URLs, bodies, or login secrets.
        emit("result", result="error", reason="local_runtime_error", errorType=type(error).__name__)
    try:
        write_public_status()
    except OSError:
        emit("status_publish_failed", result="error")
        exit_code = exit_code or 2
    sys.exit(exit_code)
