"""One native per-install task with deduplicated Beijing-time daily triggers."""
import argparse
import datetime as dt
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"
ET.register_namespace("", NS)
HIDDEN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def identity(root):
    suffix = hashlib.sha256(str(Path(root).resolve()).casefold().encode()).hexdigest()[:12]
    return "MoonUESTC-Windows-" + suffix, "MoonUESTC Windows light; owner=" + suffix


def enabled_times(accounts):
    times = sorted({a.get("run_at", "21:01") for a in accounts if a.get("automation_enabled") is True})
    if any(not isinstance(t, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", t) for t in times):
        raise ValueError("Invalid scheduled time")
    return times


def render_xml(accounts, root=HERE, python=None, date=None):
    root = Path(root).resolve()
    python = Path(python or sys.executable)
    hidden_python = python.with_name("pythonw.exe")
    if hidden_python.exists():
        python = hidden_python
    date = date or dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    task = ET.Element("{" + NS + "}Task", version="1.2")
    def child(parent, name, value=None, **attrs):
        node = ET.SubElement(parent, "{" + NS + "}" + name, attrs)
        if value is not None:
            node.text = str(value)
        return node
    registration = child(task, "RegistrationInfo")
    child(registration, "Description", identity(root)[1])
    triggers = child(task, "Triggers")
    for index, clock in enumerate(enabled_times(accounts)):
        trigger = child(triggers, "CalendarTrigger", id="time" + str(index))
        child(trigger, "StartBoundary", date.isoformat() + "T" + clock + ":00+08:00")
        child(trigger, "Enabled", "true")
        child(child(trigger, "ScheduleByDay"), "DaysInterval", "1")
    principal = child(child(task, "Principals"), "Principal", id="current-user")
    child(principal, "UserId", "CURRENT_USER_SID")
    child(principal, "LogonType", "InteractiveToken")
    child(principal, "RunLevel", "LeastPrivilege")
    settings = child(task, "Settings")
    # Start each slot on time; multi.py records that minute before waiting for its lock.
    for key, value in {"MultipleInstancesPolicy":"Parallel", "DisallowStartIfOnBatteries":"false",
                       "StopIfGoingOnBatteries":"false", "StartWhenAvailable":"false",
                       "Enabled":"true", "Hidden":"true", "WakeToRun":"true",
                       "ExecutionTimeLimit":"PT1H"}.items():
        child(settings, key, value)
    action = child(child(task, "Actions", Context="current-user"), "Exec")
    child(action, "Command", python)
    child(action, "Arguments", subprocess.list2cmdline([str(root / "run_task.py")]))
    child(action, "WorkingDirectory", root)
    return ET.tostring(task, encoding="unicode", xml_declaration=False)


SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$task = Get-ScheduledTask -TaskName $env:MOON_TASK_NAME -ErrorAction SilentlyContinue
if ($task -and $task.Description -ne $env:MOON_TASK_OWNER) { throw 'Task name belongs to another application' }
if ($env:MOON_TASK_MODE -eq 'remove') {
    if ($task) { Unregister-ScheduledTask -TaskName $env:MOON_TASK_NAME -Confirm:$false }
} else {
    [xml]$xml = Get-Content -LiteralPath $env:MOON_TASK_XML -Raw -Encoding UTF8
    $ns = [Xml.XmlNamespaceManager]::new($xml.NameTable)
    $ns.AddNamespace('t', 'http://schemas.microsoft.com/windows/2004/02/mit/task')
    $xml.SelectSingleNode('//t:UserId', $ns).InnerText = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    Register-ScheduledTask -TaskName $env:MOON_TASK_NAME -Xml $xml.OuterXml -Force | Out-Null
}
'''


def apply_xml(root, xml):
    if os.name != "nt":
        raise OSError("Windows Task Scheduler is required")
    root = Path(root)
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    name, owner = identity(root)
    env = dict(os.environ, MOON_TASK_NAME=name, MOON_TASK_OWNER=owner,
               MOON_TASK_MODE="register" if xml is not None else "remove")
    temporary = None
    try:
        if xml is not None:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".xml", dir=runtime, delete=False) as stream:
                stream.write(xml)
                temporary = Path(stream.name)
                env["MOON_TASK_XML"] = str(temporary)
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", SCRIPT],
            env=env, capture_output=True, timeout=45, creationflags=HIDDEN)
        if result.returncode:
            raise OSError("Windows 任务计划更新失败，请确认当前用户有创建任务的权限且任务计划服务可用")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def sync_schedule(accounts, root=HERE):
    apply_xml(root, render_xml(accounts, root) if enabled_times(accounts) else None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--remove", action="store_true", required=True)
    parser.parse_args()
    sync_schedule([], HERE)
    print("本安装目录的定时任务已移除。")
