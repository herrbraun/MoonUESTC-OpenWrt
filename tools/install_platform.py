"""Initialize private Linux data directories and native user timers."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from account_store import AccountStore
from moonuestc.state import execution_lock


def protect_directories(root):
    os.umask(0o077)
    for name in ("profiles", "state", "runtime", "scheduler", "api-queue"):
        target = Path(root) / name
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(target, 0o700)


def main():
    protect_directories(ROOT)
    store = AccountStore(ROOT)
    with execution_lock(ROOT / "scheduler"), execution_lock(ROOT / "state"):
        store.migrate()
        store.schedule_callback(store.all())
        store.publish()
    print("Ready. Run sh start.sh to manage accounts. No school requests were made.")


if __name__ == "__main__":
    main()
