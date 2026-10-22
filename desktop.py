"""On-demand loopback-only management page using Python's standard library."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
import secrets
import webbrowser

from account_store import AccountStore, StoreError
from account_api import dispatch
from moonuestc.errors import ToolError
from moonuestc.state import execution_lock
from tools.install_platform import protect_directories

HERE = Path(__file__).resolve().parent


class LocalServer(HTTPServer):
    def __init__(self, store, port=0):
        self.store = store
        self.access_key = secrets.token_urlsafe(32)
        super().__init__(("127.0.0.1", port), Handler)
        self.origin = "http://127.0.0.1:" + str(self.server_port)


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *args):
        pass

    def reply(self, status, data, kind="application/json; charset=utf-8"):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(data)

    def valid_host(self):
        return self.headers.get("Host") == self.server.origin.removeprefix("http://")

    def do_GET(self):
        if not self.valid_host():
            return self.reply(403, {"ok":False,"message":"访问地址不匹配"})
        if self.path == "/":
            return self.reply(200, (HERE / "web" / "index.html").read_bytes(), "text/html; charset=utf-8")
        if self.path == "/platform.js":
            return self.reply(200, (HERE / "web" / "platform.js").read_bytes(), "application/javascript; charset=utf-8")
        if self.path == "/accounts.json" or re.fullmatch(r"/status-[a-zA-Z0-9_-]{1,32}\.json", self.path):
            path = self.server.store.public / self.path[1:]
            if path.is_file():
                return self.reply(200, path.read_bytes())
        self.reply(404, {"ok":False,"message":"文件不存在"})

    def do_POST(self):
        if not self.valid_host() or self.headers.get("Origin") != self.server.origin:
            return self.reply(403, {"ok":False,"message":"请求来源不匹配"})
        if self.path != "/api":
            return self.reply(404, {"ok":False,"message":"接口不存在"})
        key = self.headers.get("X-MoonUESTC-Key", "")
        if not hmac.compare_digest(key.encode("utf-8"), self.server.access_key.encode("ascii")):
            return self.reply(401, {"ok":False,"message":"请通过“启动管理页.cmd”重新打开管理页"})
        if self.headers.get("Content-Type", "").split(";",1)[0].strip() != "application/json":
            return self.reply(415, {"ok":False,"message":"需要JSON请求"})
        try:
            size = int(self.headers.get("Content-Length", "-1"))
            if not 0 <= size <= 16384:
                raise StoreError("请求过大或缺少长度", 413)
            fields = json.loads(self.rfile.read(size))
            if not isinstance(fields, dict):
                raise StoreError("请求格式不正确")
            self.reply(200, {"ok":True, **dispatch(fields, self.server.store)})
        except StoreError as error:
            self.reply(error.status, {"ok":False,"message":str(error)})
        except ToolError:
            self.reply(409, {"ok":False,"message":"任务执行中，请稍后操作"})
        except (ValueError, UnicodeError):
            self.reply(400, {"ok":False,"message":"请求格式不正确"})
        except Exception:
            self.reply(500, {"ok":False,"message":"操作失败"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--print-url", action="store_true", help="Print a private launch URL for an SSH tunnel")
    args = parser.parse_args()
    protect_directories(HERE)
    store = AccountStore()
    with execution_lock(store.root / "scheduler"):
        store.migrate()
        store.publish()
    with LocalServer(store, args.port) as server:
        if args.print_url:
            print(server.origin + "/#key=" + server.access_key, flush=True)
        print("管理页：" + server.origin + "；关闭本窗口结束管理页，系统定时任务继续生效。", flush=True)
        if not args.no_browser:
            webbrowser.open(server.origin + "/#key=" + server.access_key)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
