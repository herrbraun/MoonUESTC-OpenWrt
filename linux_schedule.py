"""Native systemd user timers; one oneshot service per configured time slot."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def identity(root):
    suffix = hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:12]
    return "moonuestc-" + suffix + "-", "# MoonUESTC-Linux owner=" + suffix


def unit_arg(value):
    value = str(value)
    if any(char in value for char in ("\n", "\r", "\0")):
        raise ValueError("Installation paths must not contain control characters")
    value = value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$")
    return '"' + value + '"'


def render_units(accounts, root=HERE, python=None):
    root = Path(root).resolve()
    prefix, marker = identity(root)
    times = sorted({a.get("run_at", "21:01") for a in accounts if a.get("automation_enabled") is True})
    units = {}
    for clock in times:
        if not isinstance(clock, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", clock):
            raise ValueError("Invalid scheduled time")
        stem = prefix + clock.replace(":", "")
        units[stem + ".service"] = (
            marker + "\n[Unit]\nDescription=MoonUESTC lightweight check-in\n\n[Service]\nType=oneshot\n"
            + "ExecStart=" + unit_arg(python or sys.executable) + " " + unit_arg(root / "run_task.py")
            + "\nEnvironment=PYTHONUTF8=1\nUMask=0077\nNoNewPrivileges=true\nTimeoutStartSec=1h\n")
        units[stem + ".timer"] = (
            marker + "\n[Unit]\nDescription=MoonUESTC Beijing-time schedule\n\n[Timer]\n"
            + "OnCalendar=*-*-* " + clock + ":00 Asia/Shanghai\nAccuracySec=1s\nRandomizedDelaySec=0\n"
            + "Persistent=false\nUnit=" + stem + ".service\n\n[Install]\nWantedBy=timers.target\n")
    return units


def run_systemctl(arguments, check=True):
    result = subprocess.run(["systemctl", "--user", *arguments], capture_output=True, text=True, timeout=30)
    if check and result.returncode:
        raise OSError("systemd 用户定时器更新失败；请确认 systemctl --user 可用")
    return result


def write_unit(path, text):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def sync_schedule(accounts, root=HERE, unit_dir=None):
    root = Path(root)
    prefix, marker = identity(root)
    if unit_dir is None:
        config = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        if not config.is_absolute():
            raise OSError("XDG_CONFIG_HOME must be an absolute path")
        unit_dir = config / "systemd" / "user"
    unit_dir = Path(unit_dir)
    desired = render_units(accounts, root)
    previous = {}
    if unit_dir.exists():
        for path in unit_dir.glob(prefix + "*"):
            if path.suffix not in (".service", ".timer"):
                continue
            if path.is_symlink():
                raise OSError("Refusing to replace a manually linked systemd unit")
            text = path.read_text(encoding="utf-8")
            if text.splitlines()[:1] != [marker]:
                raise OSError("Unit name belongs to another application")
            previous[path.name] = text
    if not desired and not previous:
        return
    unit_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    timers = {name for name in desired if name.endswith(".timer")}
    old_timers = {name for name in previous if name.endswith(".timer")}
    states = {name: (run_systemctl(["is-enabled", name], False).returncode == 0,
                     run_systemctl(["is-active", name], False).returncode == 0) for name in old_timers}
    try:
        for name, text in desired.items():
            write_unit(unit_dir / name, text)
        run_systemctl(["daemon-reload"])
        if timers:
            run_systemctl(["enable", "--now", *sorted(timers)])
        if old_timers - timers:
            run_systemctl(["disable", "--now", *sorted(old_timers - timers)])
        for name in previous.keys() - desired.keys():
            (unit_dir / name).unlink()
        run_systemctl(["daemon-reload"])
    except Exception:
        # Restore only this install's timer definitions/states; never stop an in-flight service.
        if timers - old_timers:
            run_systemctl(["disable", "--now", *sorted(timers - old_timers)], False)
        for name in desired.keys() - previous.keys():
            (unit_dir / name).unlink(missing_ok=True)
        for name, text in previous.items():
            write_unit(unit_dir / name, text)
        run_systemctl(["daemon-reload"], False)
        for name, (enabled, active) in states.items():
            run_systemctl(["enable" if enabled else "disable", name], False)
            run_systemctl(["start" if active else "stop", name], False)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--remove", action="store_true", required=True)
    parser.parse_args()
    sync_schedule([], HERE)
    print("This installation's timers have been removed; account data is retained.")
