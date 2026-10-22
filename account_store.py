"""Private account profiles; sanitized static index; no school requests."""
import copy
import json
import math
import os
from pathlib import Path
import re
import secrets
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "vendor"))
from moonuestc.state import execution_lock
from secret_store import protect_account, read_account
from windows_schedule import sync_schedule

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"


class StoreError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def atomic_json(path, value, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + ".tmp")
    fd = os.open(temp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temp, mode)
    os.replace(temp, path)


class AccountStore:
    def __init__(self, root=HERE, public=None, schedule_callback=None):
        self.root = Path(root)
        self.public = Path(public) if public is not None else self.root / "runtime" / "public"
        self.profiles = self.root / "profiles"
        self.index = self.profiles / "index.json"
        self.schedule_callback = schedule_callback if schedule_callback is not None else lambda accounts: sync_schedule(accounts, self.root)

    @staticmethod
    def valid_id(value):
        return isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,32}", value)

    def path(self, aid):
        if not self.valid_id(aid):
            raise StoreError("账号不存在", 404)
        return self.profiles / (aid + ".json")

    def ids(self):
        value = json.loads(self.index.read_text(encoding="utf-8"))
        if not isinstance(value, list) or not all(self.valid_id(item) for item in value):
            raise StoreError("账号索引异常", 500)
        return value

    def get(self, aid):
        if aid not in self.ids():
            raise StoreError("账号不存在", 404)
        return read_account(self.path(aid))

    def all(self):
        return [self.get(aid) for aid in self.ids()]

    def migrate(self):
        if self.index.exists():
            return
        if not (self.root / "config.json").exists():
            atomic_json(self.index, [])
            self.publish()
            return
        original = json.loads((self.root / "config.json").read_text(encoding="utf-8-sig"))
        original["id"] = "me"
        original.setdefault("label", "我的账号")
        original.setdefault("run_at", "21:01")
        original.setdefault("automation_enabled", False)
        self.write_profile("me", original)
        atomic_json(self.index, ["me"])
        old = self.public / "status.json"
        if old.exists():
            atomic_json(self.status_path("me"), json.loads(old.read_text(encoding="utf-8")), 0o644)
        self.publish()

    def write_profile(self, aid, account):
        atomic_json(self.path(aid), protect_account(account))

    def status_path(self, aid):
        self.path(aid)
        return self.public / ("status-" + aid + ".json")

    def public_account(self, account):
        student = account["student_id"]
        return {"id": account["id"], "label": account["label"],
                "studentMask": student[:2] + "••••" + student[-2:],
                "runAt": account.get("run_at", "21:01"),
                "enabled": account.get("automation_enabled") is True,
                "locationName": account.get("location", {}).get("name", "未配置")}

    def publish(self):
        value = {"accounts": [self.public_account(a) for a in self.all()]}
        atomic_json(self.public / "accounts.json", value, 0o644)

    def editable(self, aid=None):
        if aid:
            source = self.get(aid)
        else:
            sources = self.all()
            source = {"run_at": "21:01", "automation_enabled": False,
                      "location": copy.deepcopy((sources[0] if sources else {}).get("location", {}))}
        return {key: source.get(key) for key in ("id", "label", "student_id", "run_at", "automation_enabled", "location")} | {
            "password_saved": bool(source.get("password")),
            "fingerprint_saved": bool(source.get("browser_fingerprint"))}

    def save(self, fields):
        allowed = {"id", "label", "student_id", "password", "browser_fingerprint", "run_at", "automation_enabled", "location"}
        if not isinstance(fields, dict) or set(fields) - allowed:
            raise StoreError("参数不正确")
        with execution_lock(self.root / "scheduler"), execution_lock(self.root / "state"):
            ids = self.ids()
            aid = fields.get("id") or secrets.token_hex(8)
            old = self.get(aid) if fields.get("id") else None
            if old is None and len(ids) >= 20:
                raise StoreError("最多添加20个账号")
            account = copy.deepcopy(old or {"id": aid, "user_agent": UA})
            for key, value in fields.items():
                if key in ("password", "browser_fingerprint") and old and value == "":
                    continue
                account[key] = copy.deepcopy(value)
            account["id"] = aid
            label = account.get("label")
            if not isinstance(label, str) or not 1 <= len(label.strip()) <= 40:
                raise StoreError("请填写账号名称")
            account["label"] = label.strip()
            if not isinstance(account.get("student_id"), str) or not re.fullmatch(r"\d{8,20}", account["student_id"]):
                raise StoreError("请填写正确学号")
            if not isinstance(account.get("password"), str) or not 1 <= len(account["password"]) <= 256:
                raise StoreError("请填写学校密码")
            if not isinstance(account.get("browser_fingerprint"), str) or not re.fullmatch(r"[a-fA-F0-9]{32}", account["browser_fingerprint"]):
                raise StoreError("浏览器指纹需要32位十六进制字符")
            if not isinstance(account.get("run_at"), str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", account["run_at"]):
                raise StoreError("执行时间不正确")
            if type(account.get("automation_enabled")) is not bool:
                raise StoreError("计划开关不正确")
            location = account.get("location")
            if not isinstance(location, dict) or set(location) - {"mode", "name", "latitude", "longitude", "coordinate_system", "reverse_geocode"}:
                raise StoreError("位置格式不正确")
            for key, limit in (("latitude", 90), ("longitude", 180)):
                value = location.get(key)
                if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > limit:
                    raise StoreError("经纬度不正确")
            if not isinstance(location.get("name"), str) or not 1 <= len(location["name"]) <= 40:
                raise StoreError("请填写位置名称")
            location.update(mode="fixed", coordinate_system="gcj02", reverse_geocode="")
            for other in self.all():
                if other["id"] != aid and other["student_id"] == account["student_id"]:
                    raise StoreError("这个学号已经添加", 409)
            previous_ids = list(ids)
            if old is None:
                ids.append(aid)
            self.write_profile(aid, account)
            atomic_json(self.index, ids)
            try:
                self.schedule_callback(self.all())
            except Exception:
                atomic_json(self.index, previous_ids)
                if old:
                    self.write_profile(aid, old)
                else:
                    self.path(aid).unlink(missing_ok=True)
                raise StoreError("Windows 定时任务保存失败，修改已撤回", 500) from None
            status = self.status_path(aid)
            snapshot = json.loads(status.read_text(encoding="utf-8")) if status.exists() else {"schema": 1, "history": []}
            if old and old["student_id"] != account["student_id"]:
                snapshot = {"schema": 1, "history": []}
            elif old and any(old.get(key) != account.get(key) for key in ("password", "browser_fingerprint")):
                snapshot.pop("auth", None)
            snapshot.update(runAt=account["run_at"], automationEnabled=account["automation_enabled"],
                            location={"name": location["name"], "radiusMeter": account.get("location_radius_meter")})
            atomic_json(status, snapshot, 0o644)
            self.publish()
            return self.editable(aid)

    def delete(self, aid):
        with execution_lock(self.root / "scheduler"), execution_lock(self.root / "state"):
            self.get(aid)
            ids = self.ids()
            remaining = [item for item in ids if item != aid]
            accounts = [self.get(item) for item in remaining]
            self.schedule_callback(accounts)
            atomic_json(self.index, remaining)
            self.path(aid).unlink()
            self.status_path(aid).unlink(missing_ok=True)
            self.publish()
