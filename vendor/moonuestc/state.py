"""One shared execution lock; durable per-account/day POST claims."""
import contextlib
import os
import json
import sqlite3
from pathlib import Path

from .errors import ToolError
from .diagnostics import submission_details


@contextlib.contextmanager
def execution_lock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    handle = (directory / "execution.lock").open("a+b")
    acquired = False
    try:
        if os.name == "nt":
            import msvcrt
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b"1")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                acquired = True
            except OSError:
                raise ToolError("another_run_active", "lock") from None
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError:
                raise ToolError("another_run_active", "lock") from None
        yield
    finally:
        if acquired:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


class State:
    def __init__(self, directory):
        Path(directory).mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(Path(directory) / "state.sqlite3"), timeout=5)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS claims (
                account TEXT, day TEXT, outcome TEXT NOT NULL,
                PRIMARY KEY (account, day));
            CREATE TABLE IF NOT EXISTS submission_diagnostics (
                account TEXT, day TEXT, details TEXT NOT NULL,
                PRIMARY KEY (account, day));
            CREATE TABLE IF NOT EXISTS logins (
                account TEXT, day TEXT, count INTEGER NOT NULL,
                PRIMARY KEY (account, day));
            CREATE TABLE IF NOT EXISTS readiness (account TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS daily (
                account TEXT, day TEXT, result TEXT NOT NULL,
                PRIMARY KEY (account, day));
        """)

    def login_budget(self, account, day):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT count FROM logins WHERE account=? AND day=?",
                                  (account, day)).fetchone()
            if row and row[0] >= 3:
                raise ToolError("daily_login_limit", "cas_submit")
            self.db.execute("INSERT INTO logins VALUES (?,?,1) ON CONFLICT(account,day) "
                            "DO UPDATE SET count=count+1", (account, day))

    def claim(self, account, day, submission=None):
        with self.db:
            row = self.db.execute("INSERT OR IGNORE INTO claims VALUES (?,?,?)",
                                  (account, day, "started"))
            if row.rowcount == 1 and submission is not None:
                safe=submission_details(submission)
                self.db.execute("INSERT INTO submission_diagnostics VALUES (?,?,?)",(account,day,json.dumps(safe,ensure_ascii=False,allow_nan=False)))
        return row.rowcount == 1

    def record_submission(self,account,day,details):
        safe=submission_details(details)
        with self.db:
            self.db.execute("UPDATE submission_diagnostics SET details=? WHERE account=? AND day=?",(json.dumps(safe,ensure_ascii=False,allow_nan=False),account,day))

    def submission(self,account,day):
        row=self.db.execute("SELECT details FROM submission_diagnostics WHERE account=? AND day=?",(account,day)).fetchone()
        return submission_details(json.loads(row[0])) if row else None

    def claimed(self, account, day):
        return self.db.execute("SELECT outcome FROM claims WHERE account=? AND day=?",
                               (account, day)).fetchone() is not None

    def outcome(self, account, day, outcome):
        with self.db:
            self.db.execute("UPDATE claims SET outcome=? WHERE account=? AND day=?",
                            (outcome, account, day))
            if outcome == "confirmed":
                self.db.execute("INSERT OR IGNORE INTO readiness VALUES (?)", (account,))

    def ready(self, account):
        return self.db.execute("SELECT 1 FROM readiness WHERE account=?", (account,)).fetchone() is not None

    def daily_done(self, account, day):
        return self.db.execute("SELECT 1 FROM daily WHERE account=? AND day=?", (account, day)).fetchone() is not None

    def save_daily(self, account, day, result):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO daily VALUES (?,?,?)", (account, day, result))

    def close(self):
        self.db.close()
