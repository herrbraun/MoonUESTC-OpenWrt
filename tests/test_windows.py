"""Windows DPAPI, native task XML and real loopback HTTP; synthetic accounts only."""
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
from secret_store import read_account, protect_account
import windows_schedule as schedule
import run_task
import multi
import lite


class ScheduleTests(unittest.TestCase):
    def test_task_xml_uses_beijing_time_current_user_and_hidden_single_run(self):
        accounts = [dict(run_at=t, automation_enabled=on) for t, on in
                    [('21:01', True), ('21:01', True), ('22:03', True), ('23:04', False)]]
        root = ROOT / "包含 空格 & 符号"
        tree = ET.fromstring(schedule.render_xml(accounts, root, date=dt.date(2026,10,22)))
        ns = {'t':schedule.NS}
        boundaries = [n.text for n in tree.findall('.//t:StartBoundary', ns)]
        self.assertEqual(boundaries, ['2026-10-22T21:01:00+08:00','2026-10-22T22:03:00+08:00'])
        self.assertEqual(tree.find('.//t:LogonType', ns).text, 'InteractiveToken')
        self.assertEqual(tree.find('.//t:RunLevel', ns).text, 'LeastPrivilege')
        self.assertEqual(tree.find('.//t:MultipleInstancesPolicy', ns).text, 'Parallel')
        self.assertEqual(tree.find('.//t:WorkingDirectory', ns).text, str(root.resolve()))
        self.assertEqual(tree.find('.//t:Arguments', ns).text, subprocess.list2cmdline([str(root.resolve()/'run_task.py')]))
        self.assertNotIn('desktop.py', ET.tostring(tree, encoding='unicode'))

    def test_unique_install_names_and_disable_removes_only_owned_task(self):
        self.assertNotEqual(schedule.identity(ROOT), schedule.identity(ROOT / 'other'))
        with patch.object(schedule, 'apply_xml') as apply:
            schedule.sync_schedule([{'automation_enabled':False}], ROOT)
        apply.assert_called_once_with(ROOT, None)
        self.assertIn('Task name belongs to another application', schedule.SCRIPT)

    def test_powershell_receives_xml_as_data_and_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            root = Path(directory)
            def run(argv, **kwargs):
                self.assertEqual(argv[-1], schedule.SCRIPT)
                env = kwargs['env']
                self.assertTrue(Path(env['MOON_TASK_XML']).is_file())
                self.assertEqual(env['MOON_TASK_NAME'], schedule.identity(root)[0])
                self.assertNotIn(str(root), argv[-1])
                return subprocess.CompletedProcess(argv, 0)
            with patch.object(schedule.subprocess, 'run', side_effect=run):
                schedule.apply_xml(root, schedule.render_xml([{'run_at':'21:01','automation_enabled':True}], root))
            self.assertEqual(list((root/'runtime').glob('*.xml')), [])

    def test_task_failure_is_reported(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            with patch.object(schedule.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)):
                with self.assertRaises(OSError):
                    schedule.apply_xml(Path(directory), None)


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

    def test_real_crud_dto_and_dpapi_at_rest(self):
        status, value = self.post({'action':'save','account':self.fields()})
        self.assertEqual(status,200)
        aid = value['account']['id']
        raw = self.store.path(aid).read_text(encoding="utf-8")
        self.assertNotIn('Synthetic-Only-Password', raw)
        self.assertNotIn('a'*32, raw)
        self.assertIn('dpapi:v1:', raw)
        self.assertEqual(self.store.get(aid)['password'], self.fields()['password'])
        with patch.object(lite, 'DirectTransport') as transport, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(multi.run_profile(self.store, aid, 'scheduled'), 0)
            transport.assert_not_called()
        self.assertEqual(json.loads(self.store.status_path(aid).read_text(encoding="utf-8"))['lastRun']['reason'], 'automation_disabled')
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
            self.assertEqual((root/'runtime'/'last-run.log').read_text(encoding="utf-8").strip(), 'Synthetic event')
            self.assertEqual(list((root/'runtime').glob('task-*.log')), [])

    def test_exception_text_never_enters_task_log(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            root = Path(directory)
            with patch.object(run_task, 'HERE', root), patch.object(run_task.multi, 'main', side_effect=RuntimeError('Synthetic-Secret-Never-Log')):
                self.assertEqual(run_task.main(), 2)
            raw = (root/'runtime'/'last-run.log').read_text(encoding="utf-8")
            self.assertNotIn('Synthetic-Secret-Never-Log', raw)
            self.assertIn('local_runtime_error', raw)


if __name__ == '__main__':
    unittest.main()
