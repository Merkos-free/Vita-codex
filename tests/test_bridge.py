import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import wave
import ssl
import subprocess
import shutil
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
from codex_vita.core import Bridge
from codex_vita.rpc import RpcClient, RpcError
from codex_vita.security import Pairing, Projects
from codex_vita.server import make_server
from codex_vita.voice import pcm16_to_wav
from codex_vita.doctor import literals

class FakeRPC:
    def __init__(self, root):
        self.root = root
        self.calls = []
        self.replies = []
        self.account_type = "chatgpt"
        self.cwd = root
        self.on_message = lambda _: None
    def request(self, method, params):
        self.calls.append((method, copy.deepcopy(params)))
        if method == "account/read":
            return {"account": {"type": self.account_type}}
        if method in ("thread/start", "thread/resume", "thread/read"):
            return {"thread": {"id": "t1", "cwd": self.cwd, "turns": []}}
        if method == "thread/list":
            return {"data": [{"id": "t1", "cwd": self.root}, {"id": "forbidden", "cwd": "/not-allowed"}], "nextCursor": None}
        if method == "turn/start":
            return {"turn": {"id": "turn1"}}
        return {}
    def reply(self, ident, result=None, error=None):
        self.replies.append({"id": ident, "result": result, "error": error})

class PairingTests(unittest.TestCase):
    def test_single_use(self):
        p = Pairing(); token = p.exchange(p.pin)
        self.assertTrue(p.check(token)); self.assertFalse(p.check("wrong"))
        with self.assertRaises(PermissionError): p.exchange(p.pin)
    def test_rate_limit(self):
        p = Pairing()
        wrong = "000000" if p.pin != "000000" else "111111"
        for _ in range(5):
            with self.assertRaises(PermissionError): p.exchange(wrong)
        with self.assertRaises(PermissionError): p.exchange(p.pin)
    def test_expiry(self):
        now = [1.0]; p = Pairing(lambda: now[0]); now[0] = 122
        with self.assertRaises(PermissionError): p.exchange(p.pin)
    def test_session_expiry(self):
        now = [1.0]; p = Pairing(lambda: now[0]); token = p.exchange(p.pin)
        now[0] = 86402; self.assertFalse(p.check(token))
    def test_unicode_pin_rejected(self):
        p = Pairing()
        with self.assertRaises(PermissionError): p.exchange("１２３４５６")
    def test_revoke(self):
        p=Pairing(); t=p.exchange(p.pin); p.revoke_all(); self.assertFalse(p.check(t))

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.rpc = FakeRPC(self.temp.name)
        self.projects = Projects([{"id": "p1", "path": self.temp.name}])
        self.bridge = Bridge(self.rpc, self.projects)
    def open(self):
        return self.bridge.dispatch("newThread", {"project": "p1"})
    def approval(self):
        self.open()
        self.bridge.on_message({"id": 99, "method": "item/commandExecution/requestApproval", "params": {"threadId": "t1", "command": "npm test"}})
        return next(iter(self.bridge.pending))
    def test_new_thread_policy(self):
        self.assertEqual(self.open(), {"threadId": "t1"})
        params = self.rpc.calls[-1][1]
        self.assertEqual(params["sandbox"], "readOnly")
        self.assertEqual(params["approvalPolicy"], "onRequest")
    def test_api_key_account_rejected(self):
        self.rpc.account_type = "apiKey"
        with self.assertRaises(PermissionError): self.open()
        self.assertFalse(any(m == "thread/start" for m,_ in self.rpc.calls))
    def test_forbidden_project(self):
        with self.assertRaises(PermissionError): self.bridge.dispatch("newThread", {"project": "../outside"})
    def test_foreign_thread_not_resumed(self):
        self.rpc.cwd = str(Path(self.temp.name).parent)
        with self.assertRaises(PermissionError): self.bridge.dispatch("resume", {"project": "p1", "thread": "t1"})
        self.assertFalse(any(m == "thread/resume" for m,_ in self.rpc.calls))
    def test_unopened_thread(self):
        with self.assertRaises(PermissionError): self.bridge.dispatch("send", {"project":"p1", "thread":"outside", "text":"x"})
    def test_thread_list_filtered(self):
        result=self.bridge.dispatch("threads", {"project":"p1"})
        self.assertEqual([x["id"] for x in result["threads"]], ["t1"])
    def test_unknown_method_never_forwarded(self):
        with self.assertRaises(ValueError): self.bridge.dispatch("process/spawn", {"command": ["whoami"]})
        self.assertEqual(self.rpc.calls, [])
    def test_prompt_limit(self):
        self.open()
        with self.assertRaises(ValueError): self.bridge.dispatch("send", {"project":"p1", "thread":"t1", "text":"я"*9000})
    def test_send_real_params(self):
        self.open(); r=self.bridge.dispatch("send", {"project":"p1", "thread":"t1", "text":"Проверь тесты"})
        self.assertEqual(r["turnId"], "turn1")
        p=self.rpc.calls[-1][1]
        self.assertEqual(p["input"], [{"type":"text","text":"Проверь тесты"}])
        self.assertEqual(p["sandboxPolicy"], {"type": "readOnly"})
    def test_no_duplicate_active_turn(self):
        self.test_send_real_params()
        with self.assertRaises(ValueError): self.bridge.dispatch("send", {"project":"p1", "thread":"t1", "text":"again"})
    def test_stream_bounded(self):
        self.open()
        self.bridge.on_message({"method":"item/agentMessage/delta", "params":{"threadId":"t1", "delta":"x"*70000}})
        self.assertEqual(len(self.bridge.views["t1"]["text"]), 65536)
        self.assertTrue(self.bridge.views["t1"]["truncated"])
    def test_approval_replay_rejected(self):
        key=self.approval(); args={"project":"p1", "thread":"t1", "approvalId":key, "decision":"accept"}
        self.bridge.dispatch("approval", args)
        self.assertEqual(self.rpc.replies[-1]["result"], {"decision":"accept"})
        with self.assertRaises(PermissionError): self.bridge.dispatch("approval", args)
    def test_session_approval_not_allowed(self):
        key=self.approval()
        with self.assertRaises(ValueError): self.bridge.dispatch("approval", {"project":"p1", "thread":"t1", "approvalId":key, "decision":"acceptForSession"})
    def test_expired_approval_declined(self):
        key=self.approval(); self.bridge.pending[key]["deadline"] = time.monotonic()-1
        self.bridge.expire_approvals()
        self.assertEqual(self.rpc.replies[-1]["result"], {"decision":"decline"})
    def test_unhandled_server_request_fails_closed(self):
        self.bridge.on_message({"id":1,"method":"account/chatgptAuthTokens/refresh","params":{}})
        self.assertEqual(self.rpc.replies[-1]["error"]["code"], -32601)
    def test_event_for_unknown_thread_ignored(self):
        self.bridge.on_message({"method":"item/agentMessage/delta","params":{"threadId":"other","delta":"private"}})
        self.assertEqual(self.bridge.views,{})
    def test_raw_voice_disabled(self):
        self.assertFalse(self.bridge.dispatch("status", {})["voice"]["enabled"])
        with self.assertRaises(ValueError): self.bridge.dispatch("transcribe", {})
    def test_unknown_turn_not_retried(self):
        self.open(); self.bridge.views["t1"]["status"]="unknown"
        with self.assertRaises(ValueError): self.bridge.dispatch("send", {"project":"p1","thread":"t1","text":"again"})
    def test_provider_fixed(self):
        self.open(); self.assertEqual(self.rpc.calls[-1][1]["modelProvider"],"openai")
    def test_fast_completion_not_overwritten(self):
        self.open(); original=self.rpc.request
        def req(m,p):
            if m=="turn/start":
                self.bridge.on_message({"method":"turn/completed","params":{"threadId":"t1","turn":{"id":"turn1","status":"completed"}}})
            return original(m,p)
        self.rpc.request=req
        self.bridge.dispatch("send",{"project":"p1","thread":"t1","text":"test"})
        self.assertEqual(self.bridge.views["t1"]["status"],"completed")

class RpcTests(unittest.TestCase):
    def setUp(self):
        self.messages=[]
        self.rpc=RpcClient([sys.executable, str(Path(__file__).parent/"fixtures/fake_codex.py")], self.messages.append)
        self.addCleanup(self.rpc.close)
        with patch.dict(os.environ, {"OPENAI_API_KEY":"fake-test-key-never-valid", "CODEX_API_KEY":"fake-test-key-never-valid"}):
            self.rpc.start()
    def test_unicode_and_bidirectional_id(self):
        self.assertEqual(self.rpc.request("test/roundtrip", {"text":"Русский текст"}), {"text":"Русский текст"})
        self.assertTrue(any(m.get("method")=="test/serverRequest" for m in self.messages))
    def test_error(self):
        with self.assertRaises(RpcError): self.rpc.request("test/error", {})
    def test_timeout(self):
        with self.assertRaises(TimeoutError): self.rpc.request("test/wait", {}, timeout=0.05)
        self.assertFalse(self.rpc._pending)
    def test_exit_fails_pending(self):
        with self.assertRaises(RpcError): self.rpc.request("test/exit", {})
    def test_no_paid_key_environment(self):
        self.assertFalse(self.rpc.request("test/env", {})["apiKeyPresent"])

class AudioTests(unittest.TestCase):
    def test_valid_wav(self):
        data=pcm16_to_wav(b"\0\0"*16000)
        with wave.open(io.BytesIO(data), "rb") as f:
            self.assertEqual((f.getnchannels(),f.getsampwidth(),f.getframerate(),f.getnframes()),(1,2,16000,16000))
    def test_reject_invalid_audio(self):
        for pcm in (b"",b"x",b"\0"*(16000*2*31)):
            with self.assertRaises(ValueError): pcm16_to_wav(pcm)
    def test_schema_symbols(self):
        result=set(); literals({"anyOf":[{"const":"thread/start"},{"enum":["workspaceWrite",2]}]},result)
        self.assertEqual(result,{"thread/start","workspaceWrite"})

class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.pairing=Pairing()
        self.bridge=Bridge(FakeRPC(self.temp.name),Projects([{"id":"p1","path":self.temp.name}]))
        self.server=make_server("127.0.0.1",0,self.bridge,self.pairing)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.url=f"http://127.0.0.1:{self.server.server_port}"
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)
    def post(self,path,body,headers=None):
        h={"Content-Type":"application/json"};h.update(headers or {})
        req=urllib.request.Request(self.url+path,json.dumps(body).encode(),headers=h)
        # Ignore ambient HTTP proxies for localhost test fixtures.
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req,timeout=5) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as r:return r.code,json.load(r)
    def test_unauthenticated(self):
        self.assertEqual(self.post("/v1/action",{"operation":"projects"})[0],401)
    def test_browser_origin_rejected(self):
        self.assertEqual(self.post("/v1/pair",{"pin":self.pairing.pin},{"Origin":"http://evil.test"})[0],403)
    def test_pair_and_projects(self):
        code,result=self.post("/v1/pair",{"pin":self.pairing.pin});self.assertEqual(code,200)
        code,result=self.post("/v1/action",{"operation":"projects"},{"Authorization":"Bearer "+result["token"]})
        self.assertEqual(code,200);self.assertEqual(result["projects"][0]["id"],"p1")
    @unittest.skipUnless(shutil.which("openssl"), "openssl needed for local test certificate")
    def test_real_tls_roundtrip(self):
        cert=str(Path(self.temp.name)/"cert.pem"); key=str(Path(self.temp.name)/"key.pem")
        subprocess.run(["openssl","req","-x509","-newkey","rsa:2048","-nodes","-days","1",
            "-keyout",key,"-out",cert,"-subj","/CN=localhost","-addext","subjectAltName=IP:127.0.0.1"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        tls=make_server("127.0.0.1",0,self.bridge,self.pairing,cert,key)
        worker=threading.Thread(target=tls.serve_forever,daemon=True); worker.start()
        try:
            context=ssl.create_default_context(cafile=cert)
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
            with opener.open(f"https://127.0.0.1:{tls.server_port}/healthz",timeout=5) as r:
                self.assertEqual(json.load(r),{"ok":True})
        finally:
            tls.shutdown(); tls.server_close(); worker.join(2)
    def test_no_insecure_lan(self):
        with self.assertRaises(ValueError): make_server("0.0.0.0",0,self.bridge,self.pairing)

if __name__=="__main__":unittest.main()
