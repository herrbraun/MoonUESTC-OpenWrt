"""On-demand CGI. Native rpcd admin sessions, same-origin JSON-only writes."""
import http.cookies
from http import HTTPStatus
import ipaddress
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

from account_store import AccountStore, StoreError, atomic_json
from moonuestc.errors import ToolError
from moonuestc.state import execution_lock

COOKIE = "moonuestc_admin"
COOKIE_PATH = "/cgi-bin/moonuestc-api"


def rpc(token, method, fields):
    data = {"jsonrpc": "2.0", "id": 1, "method": "call", "params": [token, "session", method, fields]}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request("http://127.0.0.1/ubus", data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
    try:
        with opener.open(request, timeout=5) as response:
            result = json.load(response).get("result", [])
    except (OSError, ValueError):
        raise StoreError("管理认证暂不可用", 503) from None
    return result[1] if len(result) > 1 and result[0] == 0 else None


def request_fields(env, data):
    host = env.get("HTTP_HOST", "")
    parsed = urllib.parse.urlsplit("http://" + host)
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
        if not address.is_private:
            raise ValueError()
    except ValueError:
        raise StoreError("请使用路由器IP访问", 403) from None
    if env.get("REQUEST_METHOD") == "GET":
        if urllib.parse.parse_qs(env.get("QUERY_STRING", "")).get("action") == ["session"]:
            return {"action": "session"}
        raise StoreError("不支持的请求", 405)
    if env.get("REQUEST_METHOD") != "POST":
        raise StoreError("不支持的请求", 405)
    scheme = "https" if env.get("HTTPS") == "on" or env.get("SERVER_PORT") == "443" else "http"
    if env.get("HTTP_ORIGIN") != scheme + "://" + host:
        raise StoreError("请求来源不匹配", 403)
    if env.get("CONTENT_TYPE", "").split(";", 1)[0].strip() != "application/json":
        raise StoreError("需要JSON请求", 415)
    try:
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError()
    except (ValueError, UnicodeError):
        raise StoreError("请求格式不正确") from None
    return value


def authenticated(env):
    cookies = http.cookies.SimpleCookie()
    try:
        cookies.load(env.get("HTTP_COOKIE", ""))
        token = cookies[COOKIE].value if COOKIE in cookies else ""
    except http.cookies.CookieError:
        return None
    if not re.fullmatch(r"[a-f0-9]{32}", token):
        return None
    access = rpc(token, "access", {"scope": "access-group", "object": "luci-base", "function": "write"})
    return token if access and access.get("access") is True else None


def dispatch(fields, env, store, auth=authenticated):
    action = fields.get("action")
    secure = "; Secure" if env.get("HTTPS") == "on" or env.get("SERVER_PORT") == "443" else ""
    if action == "login":
        password = fields.get("password")
        if not isinstance(password, str) or not 1 <= len(password) <= 256:
            raise StoreError("请填写管理密码")
        result = rpc("0" * 32, "login", {"username": "root", "password": password, "timeout": 900})
        token = result.get("ubus_rpc_session") if result else None
        if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{32}", token):
            raise StoreError("管理密码不正确", 401)
        return {"authenticated": True}, f"{COOKIE}={token}; Path={COOKIE_PATH}; HttpOnly; SameSite=Strict; Max-Age=900{secure}"
    token = auth(env)
    if action == "session":
        return {"authenticated": bool(token)}, None
    if not token:
        raise StoreError("请先验证管理密码", 401)
    if action == "logout":
        rpc(token, "destroy", {})
        return {}, f"{COOKIE}=; Path={COOKIE_PATH}; HttpOnly; SameSite=Strict; Max-Age=0{secure}"
    if action == "get":
        return {"account": store.editable(fields.get("id"))}, None
    if action == "save":
        return {"account": store.save(fields.get("account"))}, None
    if action == "delete":
        store.delete(fields.get("id"))
        return {}, None
    if action == "diagnose":
        aid = fields.get("id")
        store.get(aid)
        with execution_lock(store.root / "api-queue"):
            recent = store.root / "api-last-request.json"
            if recent.exists() and time.time() - json.loads(recent.read_text(encoding="utf-8")).get("at", 0) < 20:
                raise StoreError("请间隔20秒再检查", 429)
            with execution_lock(store.root / "scheduler"):
                pass
            atomic_json(recent, {"at": time.time()})
            path = store.status_path(aid)
            state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            state["busy"] = True
            atomic_json(path, state, 0o644)
            try:
                subprocess.Popen([sys.executable, str(store.root / "multi.py"), "diagnose", "--account", aid],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    close_fds=True, start_new_session=True)
            except OSError:
                state.pop("busy", None)
                atomic_json(path, state, 0o644)
                raise StoreError("检查未启动，请重试", 503) from None
        return {"queued": True}, None
    raise StoreError("接口不存在", 404)


def cgi_main():
    status, value, cookie = 200, {}, None
    try:
        length = int(os.environ.get("CONTENT_LENGTH", "0"))
        if not 0 <= length <= 16384:
            raise StoreError("请求过大", 413)
        fields = request_fields(os.environ, sys.stdin.buffer.read(length))
        value, cookie = dispatch(fields, os.environ, AccountStore())
        value = {"ok": True, **value}
    except StoreError as error:
        status, value = error.status, {"ok": False, "message": str(error)}
    except ToolError:
        status, value = 409, {"ok": False, "message": "任务执行中，请稍后操作"}
    except Exception:
        status, value = 500, {"ok": False, "message": "操作失败"}
    headers = [f"Status: {status} {HTTPStatus(status).phrase}", "Content-Type: application/json; charset=utf-8", "Cache-Control: no-store", "X-Content-Type-Options: nosniff"]
    if cookie:
        headers.append("Set-Cookie: " + cookie)
    sys.stdout.buffer.write(("\r\n".join(headers) + "\r\n\r\n" + json.dumps(value, ensure_ascii=False)).encode())
