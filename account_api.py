"""Local management operations; no school submission endpoint."""
import json
import subprocess
import sys
import time

from account_store import StoreError, atomic_json
from moonuestc.state import execution_lock


def dispatch(fields, store):
    action = fields.get("action")
    if action == "get":
        return {"account": store.editable(fields.get("id"))}
    if action == "save":
        return {"account": store.save(fields.get("account"))}
    if action == "delete":
        store.delete(fields.get("id"))
        return {}
    if action == "diagnose":
        aid = fields.get("id")
        store.get(aid)
        with execution_lock(store.root / "api-queue"):
            recent = store.root / "api-last-request.json"
            if recent.exists() and time.time() - json.loads(recent.read_text()).get("at", 0) < 20:
                raise StoreError("请间隔20秒再检查", 429)
            with execution_lock(store.root / "scheduler"):
                pass
            atomic_json(recent, {"at": time.time()})
            path = store.status_path(aid)
            state = json.loads(path.read_text()) if path.exists() else {}
            state["busy"] = True
            atomic_json(path, state, 0o644)
            try:
                subprocess.Popen([sys.executable, str(store.root / "multi.py"), "diagnose", "--account", aid],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except OSError:
                state.pop("busy", None)
                atomic_json(path, state, 0o644)
                raise StoreError("检查未启动，请重试", 503) from None
        return {"queued": True}
    raise StoreError("接口不存在", 404)
