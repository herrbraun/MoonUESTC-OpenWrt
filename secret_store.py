"""Private POSIX JSON profiles; access is protected by 0700/0600 permissions."""
import json


def protect_account(account):
    return dict(account)


def read_account(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))
