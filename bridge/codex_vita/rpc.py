"""Bounded bidirectional JSONL RPC. No OpenAI HTTP calls or credential parsing."""
from __future__ import annotations
import json
import os
import subprocess
import threading
from concurrent.futures import Future
from typing import Any, Callable
from .launcher import resolve_command

MAX_LINE = 2 * 1024 * 1024

class RpcError(RuntimeError):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code

class RpcClient:
    def __init__(self, command: list[str], on_message: Callable[[dict], None] | None = None):
        if not command or not all(isinstance(x, str) and x for x in command):
            raise ValueError("command must be a nonempty argv list")
        self.command = resolve_command(command)
        self.on_message = on_message or (lambda _: None)
        self._pending: dict[str, Future] = {}
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._seq = 0
        self._closed = False
        self.process: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None

    def start(self) -> dict:
        env = os.environ.copy()
        for key in ("OPENAI_API_KEY", "CODEX_API_KEY"):
            env.pop(key, None)
        # Command is locally configured; remote prompts only travel over stdin.
        self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, shell=False)
        self._reader = threading.Thread(target=self._read_loop, name="codex-rpc", daemon=True)
        self._reader.start()
        try:
            result = self.request("initialize", {"clientInfo": {
                "name": "codex_vita", "title": "Codex Vita (unofficial personal client)",
                "version": "0.1.0"}, "capabilities": {"experimentalApi": False}})
            self.notify("initialized", {})
            return result
        except BaseException:
            self.close()
            raise

    def _send(self, message: dict) -> None:
        data = (json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        if len(data) > MAX_LINE:
            raise ValueError("RPC message too large")
        with self._write_lock:
            if self._closed or not self.process or not self.process.stdin:
                raise RpcError(-32000, "Codex connection is closed")
            self.process.stdin.write(data)
            self.process.stdin.flush()

    def request(self, method: str, params: dict, timeout: float = 30) -> Any:
        with self._lock:
            if self._closed:
                raise RpcError(-32000, "Codex connection is closed")
            self._seq += 1
            ident = f"vita-{self._seq}"
            future: Future = Future()
            self._pending[ident] = future
        try:
            self._send({"id": ident, "method": method, "params": params})
            return future.result(timeout=timeout)
        finally:
            with self._lock:
                self._pending.pop(ident, None)

    def notify(self, method: str, params: dict) -> None:
        self._send({"method": method, "params": params})

    def reply(self, ident: str | int, result: dict | None = None, error: dict | None = None) -> None:
        self._send({"id": ident, "error": error} if error is not None
                   else {"id": ident, "result": result or {}})

    def _read_loop(self) -> None:
        assert self.process and self.process.stdout
        try:
            while True:
                line = self.process.stdout.readline(MAX_LINE + 1)
                if not line:
                    break
                if len(line) > MAX_LINE or not line.endswith(b"\n"):
                    raise ValueError("Oversized or incomplete Codex JSONL frame")
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise ValueError("RPC frames must be objects")
                if "method" in message:
                    # Server requests have BOTH method and id: never match them to a Future.
                    self.on_message(message)
                elif "id" in message:
                    with self._lock:
                        future = self._pending.get(message["id"])
                        if future is not None and not future.done():
                            if "error" in message:
                                err = message["error"]
                                future.set_exception(RpcError(err.get("code", -32000),
                                                              err.get("message", "RPC error")))
                            else:
                                future.set_result(message.get("result"))
        except Exception:
            # Raw protocol and stderr can contain code, paths or credentials. Don't log them.
            pass
        finally:
            self._fail_pending()

    def _fail_pending(self) -> None:
        with self._lock:
            self._closed = True
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(RpcError(-32000, "Codex process exited or protocol failed"))

    def close(self) -> None:
        self._fail_pending()
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=3)
            for pipe in (self.process.stdin, self.process.stdout):
                if pipe:
                    pipe.close()
        if self._reader and self._reader is not threading.current_thread():
            self._reader.join(timeout=3)
