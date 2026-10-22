"""Initialize current-user private folders and the native schedule."""
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from account_store import AccountStore
from moonuestc.state import execution_lock


def protect_directories(root):
    if os.name != "nt":
        raise OSError("Windows 10/11 is required")
    hidden = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(["whoami.exe", "/user", "/fo", "csv", "/nh"], capture_output=True, check=True, creationflags=hidden)
    match = re.search(rb"S-1-5-[0-9-]+", result.stdout)
    if match is None:
        raise OSError("Cannot determine the current Windows user")
    sid = "*" + match.group().decode("ascii")
    for name in ("profiles", "state", "runtime", "scheduler", "api-queue"):
        target = Path(root) / name
        target.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(["icacls.exe", str(target), "/inheritance:r", "/grant:r",
            sid + ":(OI)(CI)F", "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F"],
            capture_output=True, creationflags=hidden)
        if result.returncode:
            raise OSError("Cannot protect the private application directory")


def main():
    protect_directories(ROOT)
    store = AccountStore(ROOT)
    with execution_lock(ROOT / "scheduler"), execution_lock(ROOT / "state"):
        store.migrate()
        store.schedule_callback(store.all())
        store.publish()
    print("Ready. Open the launcher to manage accounts. No school requests were made.")


if __name__ == "__main__":
    main()
