"""Install the static UI, on-demand CGI and per-time cron entries."""
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
WEB = Path("/www/moonuestc")
CGI = Path("/www/cgi-bin/moonuestc-api")
sys.path.insert(0, str(ROOT))
from account_store import AccountStore, atomic_json, cron_text
from moonuestc.state import execution_lock

MARKER = "# moonuestc-openwrt"


def main():
    os.umask(0o077)
    if not Path("/etc/init.d/uhttpd").exists() or not Path("/etc/init.d/rpcd").exists():
        raise SystemExit("LuCI uhttpd/rpcd with /ubus is required.")
    existing = WEB / "index.html"
    if existing.exists() and 'data-app="moonuestc-openwrt"' not in existing.read_text(encoding="utf-8"):
        raise SystemExit("The web directory belongs to another installation; no files changed.")
    if CGI.exists() and MARKER not in CGI.read_text(encoding="utf-8"):
        raise SystemExit("The CGI path belongs to another installation; no files changed.")
    with execution_lock(ROOT / "scheduler"):
        old_cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if old_cron.returncode not in (0, 1):
            raise SystemExit("Cannot read existing crontab.")
        backup = ROOT / "backups" / datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup.mkdir(parents=True, mode=0o700)
        (backup / "crontab.txt").write_text(old_cron.stdout, encoding="utf-8")
        config = ROOT / "config.json"
        if config.exists():
            shutil.copyfile(config, backup / "config.json")
        profiles = ROOT / "profiles"
        if profiles.exists():
            shutil.copytree(profiles, backup / "profiles")
        if WEB.exists():
            shutil.copytree(WEB, backup / "web")
        if CGI.exists():
            shutil.copyfile(CGI, backup / "moonuestc-api")
        # A legacy single-account bootstrap is checked read-only before migration.
        prepared = None
        if config.exists() and not (profiles / "index.json").exists():
            status_path = ROOT / "state" / "installation-status.json"
            subprocess.run([sys.executable, str(ROOT / "lite.py"), "prepare",
                            "--status-path", str(status_path)], check=True)
            prepared = json.loads(status_path.read_text(encoding="utf-8"))
            if prepared.get("lastRun", {}).get("result") != "dry_run_ready":
                raise SystemExit("School preparation did not pass; schedule not installed.")
        WEB.mkdir(parents=True, exist_ok=True, mode=0o755)
        os.chmod(WEB, 0o755)
        store = AccountStore(ROOT, WEB)
        store.migrate()
        if prepared is not None and not store.status_path("me").exists():
            atomic_json(store.status_path("me"), prepared, 0o644)
        store.publish()
        shutil.copyfile(ROOT / "web" / "index.html", WEB / "index.html")
        os.chmod(WEB / "index.html", 0o644)
        os.chmod(ROOT / "run.sh", 0o700)
        CGI.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        script = "#!/usr/bin/python3\n" + MARKER + "\nimport sys\nsys.path.insert(0, " + repr(str(ROOT)) + ")\nfrom account_api import cgi_main\ncgi_main()\n"
        temporary = CGI.with_suffix(".tmp")
        temporary.write_text(script, encoding="utf-8", newline="\n")
        os.chmod(temporary, 0o755)
        os.replace(temporary, CGI)
        content = cron_text(old_cron.stdout, store.all(), ROOT)
        subprocess.run(["crontab", "-"], input=content, text=True, capture_output=True, check=True)
        subprocess.run(["/etc/init.d/cron", "enable"], check=True)
        subprocess.run(["/etc/init.d/cron", "start"], check=True, stdout=subprocess.DEVNULL)
    print("Installed. Dashboard: http://<router>/moonuestc/")
    print("Existing profiles, state and enable flags preserved. Manage with the router root password.")


if __name__ == "__main__":
    main()
