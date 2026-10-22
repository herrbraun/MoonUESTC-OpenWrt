"""Offline syntax validation only; never installs or starts a service."""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from linux_schedule import render_units

with tempfile.TemporaryDirectory(prefix="moonuestc-unit-check-") as directory:
    root = Path(directory)
    units = render_units([{"run_at":"21:01","automation_enabled":True},
                          {"run_at":"22:03","automation_enabled":True}], ROOT)
    for name, value in units.items():
        (root / name).write_text(value, encoding="utf-8")
    subprocess.run(["systemd-analyze", "verify", "--man=no", *[str(root / name) for name in units]], check=True)
    subprocess.run(["systemd-analyze", "calendar", "*-*-* 21:01:00 Asia/Shanghai"], check=True, stdout=subprocess.DEVNULL)
print("systemd unit and Beijing-time calendar validation passed; nothing installed.")
