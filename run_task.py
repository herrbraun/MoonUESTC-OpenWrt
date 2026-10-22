"""Hidden one-shot task entry; no web server and no restart loop."""
import contextlib
import json
import os
from pathlib import Path
import sys
import tempfile

import multi

HERE = Path(__file__).resolve().parent


def main():
    runtime = HERE / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="task-", suffix=".log", dir=runtime)
    saved_argv = sys.argv
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as log:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                sys.argv = ["multi.py", "checkin", "--due", "--submit"]
                try:
                    code = multi.main()
                except Exception:
                    print(json.dumps({"result":"error", "reason":"local_runtime_error"}))
                    code = 2
    finally:
        sys.argv = saved_argv
        os.replace(temporary, runtime / "last-run.log")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
