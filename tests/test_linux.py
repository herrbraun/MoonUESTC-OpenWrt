"""POSIX permissions, systemd units and real loopback HTTP; synthetic accounts only."""
import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from account_store import AccountStore, atomic_json
from desktop import LocalServer
from tools.install_platform import protect_directories
import linux_schedule as schedule
import run_task
import multi
import lite


class ScheduleTests(unittest.TestCase):
    def test_distinct_slot_services_and_beijing_calendars(self):
        accounts = [dict(run_at=t,automation_enabled=on) for t,on in
                    [('21:01',True),('21:01',True),('22:03',True),('23:04',False)]]
        units = schedule.render_units(accounts, ROOT / 'space & percent% dollar$', python='/usr/bin/python3')
        self.assertEqual(len(units),4)
        timers = [value for name,value in units.items() if name.endswith('.timer')]
        self.assertTrue(any('21:01:00 Asia/Shanghai' in value for value in timers))
        self.assertTrue(any('22:03:00 Asia/Shanghai' in value for value in timers))
        services = [value for name,value in units.items() if name.endswith('.service')]
        self.assertTrue(all('Type=oneshot' in value and 'UMask=0077' in value for value in services))
        self.assertTrue(all('%%' in value and '$$' in value for value in services))
        self.assertTrue(all('Persistent=false' in value for value in timers))

    def test_empty_install_needs_no_user_bus(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            with patch.object(schedule,'run_systemctl') as call:
                schedule.sync_schedule([],Path(directory),Path(directory)/'units')
            call.assert_not_called()

    def test_updates_preserve_unrelated_units_and_running_services(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            root=Path(directory);units=root/'units';units.mkdir()
            other=units/'unrelated.timer';other.write_text('unchanged')
            calls=[]
            def run(args,check=True):
                calls.append(args)
                return subprocess.CompletedProcess(args,0)
            with patch.object(schedule,'run_systemctl',side_effect=run):
                schedule.sync_schedule([dict(run_at='21:01',automation_enabled=True)],root,units)
                schedule.sync_schedule([dict(run_at='22:03',automation_enabled=True)],root,units)
                self.assertTrue(any(p.name.endswith('2203.timer') for p in units.iterdir()))
                self.assertFalse(any(p.name.endswith('2101.timer') for p in units.iterdir()))
                schedule.sync_schedule([],root,units)
            self.assertEqual(list(units.iterdir()),[other])
            self.assertEqual(other.read_text(),'unchanged')
            self.assertFalse(any(args[0]=='stop' and any(a.endswith('.service') for a in args) for args in calls))

    def test_failed_update_restores_previous_units(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            root=Path(directory);units=root/'units'
            def ok(args,check=True): return subprocess.CompletedProcess(args,0)
            with patch.object(schedule,'run_systemctl',side_effect=ok):
                schedule.sync_schedule([dict(run_at='21:01',automation_enabled=True)],root,units)
            previous={p.name:p.read_text() for p in units.iterdir()}
            failed=[]
            def run(args,check=True):
                if args[:2]==['enable','--now'] and not failed:
                    failed.append(True);raise OSError('synthetic')
                return subprocess.CompletedProcess(args,0)
            with patch.object(schedule,'run_systemctl',side_effect=run),self.assertRaises(OSError):
                schedule.sync_schedule([dict(run_at='22:03',automation_enabled=True)],root,units)
            self.assertEqual({p.name:p.read_text() for p in units.iterdir()},previous)

    def test_unowned_unit_is_never_overwritten(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            root=Path(directory);units=root/'units';units.mkdir()
            target=units/(schedule.identity(root)[0]+'2101.timer');target.write_text('unrelated owner')
            with patch.object(schedule,'run_systemctl') as call,self.assertRaises(OSError):
                schedule.sync_schedule([dict(run_at='21:01',automation_enabled=True)],root,units)
            call.assert_not_called();self.assertEqual(target.read_text(),'unrelated owner')


class LocalServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.root = Path(self.temp.name)
        self.store = AccountStore(self.root, schedule_callback=lambda _:None)
        self.store.migrate()
        self.server = LocalServer(self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def post(self, value, **headers):
        common = {'Origin':self.server.origin, 'Content-Type':'application/json',
                  'X-MoonUESTC-Key':self.server.access_key}
        common.update(headers)
        request = urllib.request.Request(self.server.origin+'/api', data=json.dumps(value).encode(), headers=common)
        try:
            response = self.opener.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def fields(self):
        return dict(label='Synthetic', student_id='2099999999999',password='Synthetic-Only-Password',
                    browser_fingerprint='a'*32, run_at='21:01',automation_enabled=False,
                    location=dict(name='Synthetic location',latitude=30.6,longitude=104.0))

    def test_loopback_and_request_guards(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')
        for headers, status in [({'X-MoonUESTC-Key':''},401),({'Origin':'https://example.com'},403),
                                ({'Host':'example.com'},403),({'Content-Type':'text/plain'},415),
                                ({'Content-Length':'16385'},413)]:
            with self.subTest(headers=headers):
                self.assertEqual(self.post({'action':'get'}, **headers)[0], status)

    def test_real_crud_dto_and_private_profiles(self):
        status, value = self.post({'action':'save','account':self.fields()})
        self.assertEqual(status,200)
        aid = value['account']['id']
        raw = self.store.path(aid).read_text()
        if __import__('os').name == 'posix':
            self.assertEqual(__import__('stat').S_IMODE(self.store.path(aid).stat().st_mode),0o600)
        self.assertEqual(self.store.get(aid)['password'], self.fields()['password'])
        with patch.object(lite, 'DirectTransport') as transport, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(multi.run_profile(self.store, aid, 'scheduled'), 0)
            transport.assert_not_called()
        self.assertEqual(json.loads(self.store.status_path(aid).read_text())['lastRun']['reason'], 'automation_disabled')
        status, value = self.post({'action':'get','id':aid})
        self.assertNotIn('password',value['account'])
        self.assertNotIn('browser_fingerprint',value['account'])
        self.assertTrue(value['account']['password_saved'])
        edit = self.fields() | dict(id=aid,password='',browser_fingerprint='')
        self.assertEqual(self.post({'action':'save','account':edit})[0],200)
        self.assertEqual(self.store.get(aid)['password'],self.fields()['password'])
        self.assertEqual(self.post({'action':'delete','id':aid})[0],200)
        self.assertEqual(self.store.ids(),[])

    def test_no_web_submission_or_private_file_access(self):
        self.assertEqual(self.post({'action':'checkin'})[0],404)
        for path in ('/profiles/index.json','/../config.json','/secret_store.py'):
            with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as error:
                self.opener.open(self.server.origin+path)
            self.assertEqual(error.exception.code,404)
            error.exception.close()


class TaskEntryTests(unittest.TestCase):
    def test_one_shot_arguments_private_log_and_argv_restoration(self):
        original = sys.argv
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            root = Path(directory)
            def worker():
                self.assertEqual(sys.argv, ['multi.py','checkin','--due','--submit'])
                print('Synthetic event')
                return 0
            with patch.object(run_task, 'HERE', root), patch.object(run_task.multi, 'main', side_effect=worker):
                self.assertEqual(run_task.main(), 0)
            self.assertIs(sys.argv, original)
            self.assertEqual((root/'runtime'/'last-run.log').read_text().strip(), 'Synthetic event')
            self.assertEqual(list((root/'runtime').glob('task-*.log')), [])

    def test_exception_text_never_enters_task_log(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            root = Path(directory)
            with patch.object(run_task, 'HERE', root), patch.object(run_task.multi, 'main', side_effect=RuntimeError('Synthetic-Secret-Never-Log')):
                self.assertEqual(run_task.main(), 2)
            raw = (root/'runtime'/'last-run.log').read_text()
            self.assertNotIn('Synthetic-Secret-Never-Log', raw)
            self.assertIn('local_runtime_error', raw)


if __name__ == '__main__':
    unittest.main()
