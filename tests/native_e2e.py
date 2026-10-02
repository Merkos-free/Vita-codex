"""Real native C++ Session -> libcurl HTTPS -> Python bridge -> JSONL test process.
No OpenAI account, model request, Vita hardware or operating-system command execution.
Run explicitly: CV_NATIVE_PROBE=/path/to/probe python tests/native_e2e.py
"""
import json
import os
from pathlib import Path
import shutil
import ssl
import socket
from unittest.mock import patch
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'bridge'))
from codex_vita.core import Bridge
from codex_vita.rpc import RpcClient
from codex_vita.security import Pairing, Projects
from codex_vita.server import make_server, Handler


class NativeEndToEnd(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.cert,self.key=self.root/'ca.pem',self.root/'key.pem'
        self.make_cert(self.cert,self.key,'127.0.0.1')
        self.rpc=RpcClient([sys.executable,str(ROOT/'tests/fixtures/codex_scenario.py'),str(self.root)])
        self.bridge=Bridge(self.rpc,Projects([{'id':'p1','path':str(self.root),'name':'ТЕСТОВЫЙ ПРОЕКТ'}]))
        self.rpc.start();self.addCleanup(self.rpc.close)
        self.pairing=Pairing()
        self.server=make_server('127.0.0.1',0,self.bridge,self.pairing,str(self.cert),str(self.key))
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True);self.worker.start()
        self.addCleanup(self.stop_server)
        self.url=f'https://127.0.0.1:{self.server.server_port}'
        self.client=None
        self.addCleanup(self.stop_client)

    def make_cert(self,cert,key,ip):
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-keyout',str(key),'-out',str(cert),'-subj','/CN=fixture','-addext',f'subjectAltName=IP:{ip}'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=15)

    def stop_server(self):
        self.server.shutdown();self.server.server_close();self.worker.join(timeout=2)

    def stop_client(self):
        if self.client:
            self.client.terminate()
            try:self.client.wait(timeout=3)
            except subprocess.TimeoutExpired:self.client.kill();self.client.wait(timeout=3)
            self.client.stdin.close();self.client.stdout.close()
            self.client=None

    def start_client(self,ca=None):
        self.client=subprocess.Popen([os.environ['CV_NATIVE_PROBE'],self.url,str(ca or self.cert)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)

    def command(self,op,**data):
        self.client.stdin.write((json.dumps({'op':op,**data},ensure_ascii=False)+'\n').encode());self.client.stdin.flush()
        # Worker timeout means a native crash/hang fails the test, not a claimed success.
        results=[]
        reader=threading.Thread(target=lambda:results.append(self.client.stdout.readline()),daemon=True);reader.start();reader.join(timeout=8)
        self.assertFalse(reader.is_alive(),'C++ probe stopped responding')
        self.assertTrue(results[0], 'C++ probe exited')
        return json.loads(results[0])

    def connect(self):
        self.start_client()
        result=self.command('pair',pin=self.pairing.pin);self.assertTrue(result['ready'],result)
        self.command('project');result=self.command('new');self.assertTrue(result['thread'],result)

    def post(self,token,operation,data=None,request_id=None):
        body={'operation':operation,'data':data or {}}
        if request_id:body['requestId']=request_id
        request=urllib.request.Request(self.url+'/v1/action',json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=self.cert)))
        try:
            with opener.open(request,timeout=5) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:return error.code,json.load(error)

    def test_native_chat_history_and_diff(self):
        self.connect();self.assertTrue(self.command('send',text='Проверь тесты')['accepted'])
        result=self.command('snapshot')
        messages=result['view']['messages']
        self.assertEqual([x['role'] for x in messages],['user','assistant'])
        self.assertEqual(messages[0]['text'],'Проверь тесты')
        self.assertIn('+fixture',result['view']['diff'])
        self.assertTrue(result['canSend'])

    def test_approval_and_one_time_decision(self):
        self.connect();self.command('send',text='approval')
        result=self.command('snapshot');ticket=result['view']['approvals'][0]['id']
        self.assertTrue(self.command('decline',ticket=ticket)['accepted'])
        result=self.command('snapshot');self.assertEqual(result['view']['status'],'interrupted')
        self.assertFalse(self.command('accept',ticket=ticket)['accepted'])

    def test_stop_and_duplicate_busy_send(self):
        self.connect();self.command('send',text='slow')
        self.assertFalse(self.command('send',text='duplicate')['accepted'])
        self.assertTrue(self.command('stop')['accepted'])
        result=self.command('snapshot');self.assertEqual(result['view']['status'],'interrupted')
        self.assertEqual(self.rpc.request('test/statistics',{})['sendCount'],1)

    def test_untrusted_certificate_refused(self):
        wrong=self.root/'wrong.pem';self.make_cert(wrong,self.root/'wrong-key.pem','127.0.0.1')
        self.start_client(wrong);result=self.command('pair',pin=self.pairing.pin)
        self.assertFalse(result['ready']);self.assertFalse(self.pairing.used)

    def test_ip_mismatch_refused(self):
        self.stop_server();self.make_cert(self.cert,self.key,'127.0.0.2')
        self.server=make_server('127.0.0.1',0,self.bridge,self.pairing,str(self.cert),str(self.key))
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True);self.worker.start();self.url=f'https://127.0.0.1:{self.server.server_port}'
        self.start_client();result=self.command('pair',pin=self.pairing.pin)
        self.assertFalse(result['ready']);self.assertFalse(self.pairing.used)

    def test_revoked_token_fails_closed(self):
        self.connect();self.pairing.revoke_all()
        self.assertFalse(self.command('snapshot')['ready'])

    def test_same_http_send_never_executes_twice(self):
        token=self.pairing.exchange(self.pairing.pin)
        code,result=self.post(token,'newThread',{'project':'p1'},'create-1');self.assertEqual(code,200)
        data={'project':'p1','thread':result['threadId'],'text':'short'}
        first=self.post(token,'send',data,'send-1');second=self.post(token,'send',data,'send-1')
        self.assertEqual(first,second);self.assertEqual(first[0],200)
        self.assertEqual(self.rpc.request('test/statistics',{})['sendCount'],1)
        self.assertEqual(self.post(token,'send',{**data,'text':'different'},'send-1')[0],409)
        status=self.post(token,'requestStatus',{'requestId':'send-1'})[1];self.assertEqual(status['state'],'done')

    def test_lost_creation_response_recovered_without_resend(self):
        original = Handler._json
        dropped = []
        def drop_once(handler, status, value):
            if not dropped and status == 200 and set(value) == {'threadId'}:
                dropped.append(value['threadId'])
                handler.close_connection = True
                handler.connection.shutdown(socket.SHUT_RDWR)
                return
            original(handler, status, value)
        self.start_client()
        self.assertTrue(self.command('pair', pin=self.pairing.pin)['ready'])
        self.command('project')
        with patch.object(Handler, '_json', drop_once):
            result = self.command('new')
        self.assertTrue(dropped)
        self.assertFalse(result['thread'])
        result = self.command('reconcile')
        self.assertEqual(result['thread'], dropped[0])
        self.assertTrue(result['canSend'], result)

    def test_mutation_without_request_id_refused(self):
        token=self.pairing.exchange(self.pairing.pin)
        self.assertEqual(self.post(token,'newThread',{'project':'p1'})[0],400)

    def test_native_suspend_refresh_does_not_resend(self):
        self.connect();self.command('send',text='slow');self.command('suspend')
        result=self.command('snapshot');self.assertFalse(result['canSend'])
        self.assertEqual(self.rpc.request('test/statistics',{})['sendCount'],1)


if __name__=='__main__':
    if not os.environ.get('CV_NATIVE_PROBE') or not shutil.which('openssl'):
        raise SystemExit('CV_NATIVE_PROBE and OpenSSL required; tests must not silently skip')
    unittest.main()
