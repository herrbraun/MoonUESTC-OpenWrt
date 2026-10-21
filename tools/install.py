"""Install static assets and a daily cron entry after a read-only school check."""
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
WEB = Path("/www/moonuestc")
sys.path.insert(0, str(ROOT / "vendor"))
from moonuestc.policy import clock_minutes


def atomic_json(path, value, mode=0o600):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def main():
    os.umask(0o077)
    config = ROOT / "config.json"
    account = json.loads(config.read_text(encoding="utf-8-sig"))
    minute = clock_minutes(account.get("run_at", "21:01"))
    if not Path("/etc/init.d/uhttpd").exists():
        raise SystemExit("uhttpd is required.")
    existing = WEB / "index.html"
    if existing.exists() and 'data-app="moonuestc-openwrt"' not in existing.read_text(encoding="utf-8"):
        raise SystemExit("The web directory belongs to another installation; no files changed.")
    old_cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if old_cron.returncode not in (0, 1):
        raise SystemExit("Cannot read existing crontab.")
    backup = ROOT / "backups" / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup.mkdir(parents=True, mode=0o700)
    shutil.copyfile(config, backup / "config.json")
    (backup / "crontab.txt").write_text(old_cron.stdout, encoding="utf-8")
    # Validate the real account, location and school window without submitting attendance.
    status_path = ROOT / "state" / "installation-status.json"
    status_path.parent.mkdir(exist_ok=True, mode=0o700)
    subprocess.run([sys.executable, str(ROOT / "lite.py"), "prepare", "--status-path", str(status_path)], check=True)
    status = json.loads(status_path.read_text(encoding="utf-8"))
    if status.get("lastRun", {}).get("result") != "dry_run_ready":
        raise SystemExit("School preparation did not pass; schedule not installed.")
    WEB.mkdir(parents=True, exist_ok=True, mode=0o755)
    os.chmod(WEB, 0o755)
    shutil.copyfile(ROOT / "web" / "index.html", WEB / "index.html")
    os.chmod(WEB / "index.html", 0o644)
    os.chmod(ROOT / "run.sh", 0o700)
    tags = ("# moonuestc-openwrt", "# uestc-night-checkin-lite")
    lines = [line for line in old_cron.stdout.splitlines() if not any(tag in line for tag in tags)]
    lines.append(f"{minute % 60} {minute // 60} * * * {ROOT}/run.sh # moonuestc-openwrt")
    temporary = ROOT / "crontab.tmp"
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    subprocess.run(["crontab", str(temporary)], check=True)
    temporary.unlink()
    subprocess.run(["/etc/init.d/cron", "enable"], check=True)
    subprocess.run(["/etc/init.d/cron", "start"], check=True, stdout=subprocess.DEVNULL)
    account["automation_enabled"] = True
    atomic_json(config, account)
    status.update(automationEnabled=True, runAt=account.get("run_at", "21:01"))
    atomic_json(WEB / "status.json", status, 0o644)
    print("Installed. Dashboard: http://<router>/moonuestc/")
    print("Daily time: " + status["runAt"] + " Asia/Shanghai")


if __name__ == "__main__":
    main()
