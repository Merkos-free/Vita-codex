"""Setup regression uses a fake schema and real local OpenSSL; no Codex account."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bridge'))
from codex_vita.setup import prepare

REPORT={'requiredMethods':{'thread/start':True},'threadApprovalPolicies':['on-request'],
        'turnApprovalPolicies':['on-request'],'threadSandboxModes':['read-only']}

class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
    def test_public_host_rejected_before_any_command(self):
        with patch('codex_vita.setup.inspect') as inspect:
            with self.assertRaises(ValueError):prepare('8.8.8.8',self.root,self.root/'out')
            inspect.assert_not_called()
    def test_existing_destination_not_overwritten(self):
        with self.assertRaises(FileExistsError):prepare('127.0.0.1',self.root,self.root)
    def test_invalid_ip(self):
        with self.assertRaises(ValueError):prepare('127.0.0.1; echo bad',self.root,self.root/'out')
    def test_missing_project(self):
        with self.assertRaises(FileNotFoundError):prepare('127.0.0.1',self.root/'absent',self.root/'out')
    @unittest.skipUnless(shutil.which('openssl'),'OpenSSL unavailable on this host')
    def test_schema_failure_creates_no_setup(self):
        with patch('codex_vita.setup.inspect',return_value={**REPORT,'threadSandboxModes':['dangerFullAccess']}):
            with self.assertRaises(ValueError):prepare('127.0.0.1',self.root,self.root/'out')
        self.assertFalse((self.root/'out').exists())
    @unittest.skipUnless(shutil.which('openssl'),'OpenSSL unavailable on this host')
    def test_real_certificate_public_only_bundle(self):
        with patch('codex_vita.setup.inspect',return_value=REPORT):
            config=prepare('127.0.0.1',self.root,self.root/'out')
        data=json.loads(config.read_text(encoding='utf-8'))
        self.assertEqual(data['sandbox'],'read-only')
        self.assertEqual(data['approvalPolicy'],'on-request')
        vita=config.parent/'vita'
        self.assertEqual({p.name for p in vita.iterdir()},{'ca.pem','connection.json','CERTIFICATE_SHA256.txt'})
        self.assertNotIn('PRIVATE KEY',(vita/'ca.pem').read_text())
        self.assertEqual(len((vita/'CERTIFICATE_SHA256.txt').read_text().strip()),64)
