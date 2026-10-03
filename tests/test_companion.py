"""Desktop lifecycle tests: real TLS/files, explicit fake Codex. No account/model."""
import hashlib
import json
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
from codex_vita.companion import Companion, export_public_bundle, private_ipv4, read_config, read_small
from codex_vita.security import Pairing

REPORT = {'requiredMethods': {'thread/start': True}, 'threadApprovalPolicies': ['on-request'],
          'turnApprovalPolicies': ['on-request'], 'threadSandboxModes': ['read-only']}


class FakeRPC:
    """Not an authenticated Codex. Restrict requests to the account check only."""
    instances = []
    def __init__(self, command):
        self.command = command; self.alive = False; self.requests = []; self.on_message = None
        self.__class__.instances.append(self)
    def start(self): self.alive = True
    def request(self, method, params):
        self.requests.append(method)
        if method != 'account/read': raise AssertionError('Unexpected model or other request')
        return {'account': {'type': 'chatgpt'}}
    def close(self): self.alive = False


class LocalStatusTests(unittest.TestCase):
    def test_pin_hidden_after_success_and_revocation(self):
        p = Pairing(); self.assertEqual(p.local_status()['pin'], p.pin)
        token = p.exchange(p.pin)
        self.assertEqual(p.local_status()['pin'], '')
        self.assertTrue(p.local_status()['paired']); self.assertTrue(p.check(token))
        p.revoke_all(); self.assertFalse(p.local_status()['paired'])
    def test_expired_pin_hidden(self):
        clock = [0.0]; p = Pairing(clock=lambda: clock[0]); clock[0] = 121
        self.assertEqual(p.local_status(), {'pin': '', 'seconds': 0, 'paired': False})
    def test_lockout_hides_pin(self):
        p = Pairing()
        for _ in range(5):
            with self.assertRaises(PermissionError): p.exchange('bad')
        self.assertFalse(p.local_status()['pin'])
    def test_public_address_rejected(self):
        for host in ['8.8.8.8', '0.0.0.0', '224.0.0.1', 'localhost', '127.1', '127.0.0.1;echo']:
            with self.subTest(host=host), self.assertRaises(ValueError): private_ipv4(host)
    def test_private_addresses(self):
        for host in ['127.0.0.1', '10.2.3.4', '172.16.0.1', '192.168.1.10']:
            self.assertEqual(private_ipv4(host), host)
    def test_constructor_does_not_start_anything(self):
        c = Companion(); self.assertFalse(c.busy); self.assertEqual(c.snapshot().phase, 'idle')
        c.stop(); self.assertTrue(c.wait()); self.assertEqual(c.snapshot().pin, '')
    def test_private_setup_cannot_be_inside_project(self):
        with tempfile.TemporaryDirectory() as tmp, patch('codex_vita.companion.prepare') as prepare:
            c = Companion(); self.assertTrue(c.prepare('127.0.0.1', Path(tmp), Path(tmp)/'state'))
            self.assertTrue(c.wait()); self.assertEqual(c.snapshot().phase, 'error'); prepare.assert_not_called()


@unittest.skipUnless(shutil.which('openssl'), 'OpenSSL is required for real local TLS tests')
class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared = tempfile.TemporaryDirectory(); cls.addClassCleanup(cls.shared.cleanup)
        root = Path(cls.shared.name)
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-keyout', str(root/'key.pem'), '-out', str(root/'cert.pem'), '-subj', '/CN=fixture',
                        '-addext', 'subjectAltName=IP:127.0.0.1'], check=True, timeout=15,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.cert, cls.key = (root/'cert.pem').read_bytes(), (root/'key.pem').read_bytes()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name)
        self.project = self.root/'project'; self.project.mkdir()
        self.state = self.root/'state'; self.state.mkdir()
        (self.state/'server.pem').write_bytes(self.cert); (self.state/'server-key.pem').write_bytes(self.key)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); self.port = sock.getsockname()[1]
        self.config = {'host':'127.0.0.1', 'port':self.port, 'codexCommand':['explicit-fixture'],
                       'sandbox':'read-only', 'approvalPolicy':'on-request',
                       'projects':[{'id':'scratch', 'name':'FIXTURE', 'path':str(self.project)}],
                       'tlsCert':str(self.state/'server.pem'), 'tlsKey':str(self.state/'server-key.pem')}
        self.path = self.state/'config.json'; self.save_config()
        self.vita = self.state/'vita'; self.vita.mkdir(); (self.vita/'ca.pem').write_bytes(self.cert)
        (self.vita/'connection.json').write_text(json.dumps({'endpoint':f'https://127.0.0.1:{self.port}'}))
        der = ssl.PEM_cert_to_DER_cert(self.cert.decode('ascii'))
        (self.vita/'CERTIFICATE_SHA256.txt').write_text(hashlib.sha256(der).hexdigest()+'\n')
        self.controller = Companion(); self.addCleanup(self.cleanup_runtime)
        FakeRPC.instances.clear()

    def cleanup_runtime(self):
        self.controller.stop(); self.assertTrue(self.controller.wait(5), 'Owned worker leaked')

    def save_config(self): self.path.write_text(json.dumps(self.config), encoding='utf-8')

    def await_phase(self, phase):
        deadline = time.monotonic()+4
        while time.monotonic() < deadline:
            state = self.controller.snapshot()
            if state.phase == phase: return state
            time.sleep(.02)
        self.fail(f'Expected {phase}, got {self.controller.snapshot().phase}')

    def test_valid_read_only_config(self): self.assertEqual(read_config(self.path), self.config)
    def test_duplicate_keys_rejected(self):
        self.path.write_text('{"host":"127.0.0.1","host":"8.8.8.8"}')
        with self.assertRaises(ValueError): read_config(self.path)
    def test_write_mode_rejected(self):
        self.config['sandbox']='workspace-write'; self.save_config()
        with self.assertRaises(ValueError): read_config(self.path)
    def test_automatic_approval_rejected(self):
        self.config['approvalPolicy']='never'; self.save_config()
        with self.assertRaises(ValueError): read_config(self.path)
    def test_boolean_or_privileged_port_rejected(self):
        for value in (True, 0, 80, 65536):
            self.config['port']=value; self.save_config()
            with self.subTest(value=value), self.assertRaises(ValueError): read_config(self.path)
    def test_no_projects_rejected(self):
        self.config['projects']=[]; self.save_config()
        with self.assertRaises(ValueError): read_config(self.path)
    def test_config_under_project_rejected(self):
        self.config['projects'][0]['path']=str(self.root); self.save_config()
        with self.assertRaises(ValueError): read_config(self.path)
    def test_wrong_certificate_key_rejected(self):
        (self.state/'server-key.pem').write_text('not a key')
        with self.assertRaises(ssl.SSLError): read_config(self.path)
    def test_bounded_config_read(self):
        self.path.write_bytes(b' '*65537)
        with self.assertRaises(ValueError): read_small(self.path)
    def test_missing_config(self):
        with self.assertRaises(ValueError): read_config(self.root/'absent')
    def test_export_contains_exactly_public_files(self):
        dest = self.root/'public.zip'; export_public_bundle(self.path, dest)
        with zipfile.ZipFile(dest) as z:
            self.assertEqual(set(z.namelist()), {'ca.pem','connection.json','CERTIFICATE_SHA256.txt'})
            self.assertTrue(all(b'PRIVATE KEY' not in z.read(name) for name in z.namelist()))
    def test_export_does_not_overwrite(self):
        dest=self.root/'existing.zip'; dest.write_bytes(b'keep')
        with self.assertRaises(FileExistsError): export_public_bundle(self.path,dest)
        self.assertEqual(dest.read_bytes(), b'keep')
    def test_export_rejects_secret(self):
        (self.vita/'ca.pem').write_bytes(self.key)
        with self.assertRaises(ValueError): export_public_bundle(self.path,self.root/'public.zip')
        self.assertFalse((self.root/'public.zip').exists())
    def test_export_rejects_wrong_fingerprint(self):
        (self.vita/'CERTIFICATE_SHA256.txt').write_text('0'*64)
        with self.assertRaises(ValueError): export_public_bundle(self.path,self.root/'public.zip')
    def test_export_rejects_wrong_endpoint(self):
        (self.vita/'connection.json').write_text('{"endpoint":"https://8.8.8.8:8765"}')
        with self.assertRaises(ValueError): export_public_bundle(self.path,self.root/'public.zip')
    def test_stop_during_inspection_never_opens_server(self):
        entered, release = threading.Event(), threading.Event()
        def inspect(_): entered.set(); release.wait(3); return REPORT
        with patch('codex_vita.companion.inspect', side_effect=inspect), patch('codex_vita.companion.make_server') as server:
            self.assertTrue(self.controller.start(self.path)); self.assertTrue(entered.wait(2))
            self.assertFalse(self.controller.start(self.path))
            self.controller.stop(); release.set(); self.assertTrue(self.controller.wait())
            server.assert_not_called(); self.assertEqual(self.controller.snapshot().phase, 'stopped')
    def test_schema_error_is_sanitized(self):
        with patch('codex_vita.companion.inspect', side_effect=RuntimeError('secret-marker')):
            self.controller.start(self.path); self.assertTrue(self.controller.wait())
        self.assertEqual(self.controller.snapshot().phase, 'error')
        self.assertNotIn('secret-marker', self.controller.snapshot().message)
    def test_login_failure_never_listens(self):
        with patch('codex_vita.companion.inspect', return_value=REPORT), patch('codex_vita.companion.RpcClient', FakeRPC), \
             patch.object(FakeRPC, 'request', return_value={'account':None}), patch('codex_vita.companion.make_server') as server:
            self.controller.start(self.path); self.assertTrue(self.controller.wait())
            server.assert_not_called(); self.assertFalse(FakeRPC.instances[0].alive)
        self.assertEqual(self.controller.snapshot().phase, 'error')
    def test_real_listener_pair_stop_and_no_model_requests(self):
        pairs=[]
        def factory():
            p=Pairing(); pairs.append(p); return p
        with patch('codex_vita.companion.inspect', return_value=REPORT), patch('codex_vita.companion.RpcClient', FakeRPC), \
             patch('codex_vita.companion.Pairing', side_effect=factory):
            self.controller.start(self.path); state=self.await_phase('running'); self.assertEqual(len(state.pin),6)
            request=urllib.request.Request(state.endpoint+'/v1/pair',json.dumps({'pin':state.pin}).encode(),headers={'Content-Type':'application/json'})
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=self.state/'server.pem')))
            with opener.open(request,timeout=3) as response: token=json.load(response)['token']
            self.assertTrue(pairs[0].check(token)); self.assertEqual(FakeRPC.instances[0].requests,['account/read'])
            self.controller.stop(); self.assertTrue(self.controller.wait())
            self.assertFalse(pairs[0].check(token)); self.assertFalse(FakeRPC.instances[0].alive)
            self.assertEqual(self.controller.snapshot().pin,'')
    def test_codex_death_stops_owned_listener(self):
        with patch('codex_vita.companion.inspect',return_value=REPORT), patch('codex_vita.companion.RpcClient',FakeRPC):
            self.controller.start(self.path); self.await_phase('running'); FakeRPC.instances[0].alive=False
            self.await_phase('error'); self.assertTrue(self.controller.wait())
            self.assertEqual(self.controller.snapshot().pin,'')

if __name__=='__main__': unittest.main()
