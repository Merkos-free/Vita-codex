"""Narrow remote operations; no raw RPC tunnel, shell endpoint or paid API fallback."""
from __future__ import annotations
import copy
import json
import secrets
import threading
import time
from collections import deque
from .security import Projects
from . import history

APPROVAL_METHODS = {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}
TEXT_LIMIT = 64 * 1024

class Bridge:
    def __init__(self, rpc, projects: Projects, approval_policy="onRequest", sandbox="readOnly"):
        if approval_policy not in ("onRequest", "on-request"):
            raise ValueError("Only on-request approvals are supported; other modes are intentionally disabled")
        if sandbox not in ("readOnly", "read-only", "workspaceWrite", "workspace-write"):
            raise ValueError("Only read-only or explicitly configured workspace-write is allowed")
        self.rpc, self.projects = rpc, projects
        self.approval_policy, self.sandbox = approval_policy, sandbox
        self._lock = threading.RLock()
        self._op_lock = threading.Lock()
        self.threads: dict[str, str] = {}
        self.views: dict[str, dict] = {}
        self.pending: dict[str, dict] = {}
        self.event_seq = 0
        self.events = deque(maxlen=256)
        self.rpc.on_message = self.on_message

    def require_chatgpt(self) -> None:
        account = (self.rpc.request("account/read", {"refreshToken": False}) or {}).get("account")
        if not account or account.get("type") != "chatgpt":
            raise PermissionError("Sign into official Codex with ChatGPT on the computer; API-key mode is disabled")

    def _scope(self, project: str, thread: str) -> None:
        self.projects.get(project)
        if not isinstance(thread, str) or not thread or len(thread) > 160:
            raise ValueError("Invalid thread id")
        with self._lock:
            if self.threads.get(thread) != project:
                raise PermissionError("Thread was not opened for this project")

    def _remember(self, project: str, thread: dict) -> str:
        ident = thread.get("id")
        if not isinstance(ident, str) or not ident or not self.projects.matches(project, thread.get("cwd")):
            raise PermissionError("Codex returned a thread outside the requested project")
        with self._lock:
            self.threads[ident] = project
            self.views.setdefault(ident, {"threadId": ident, "text": "", "turnId": None,
                "status": "idle", "diff": "", "tools": [], "truncated": False, "messages": [], "historyTruncated": False})
        return ident

    def _settings(self, project: str) -> dict:
        return {"cwd": self.projects.get(project)["path"], "sandbox": self.sandbox, "modelProvider": "openai",
                "approvalPolicy": self.approval_policy}

    def _turn_sandbox(self, root: dict) -> dict:
        if self.sandbox in ("readOnly", "read-only"):
            return {"type": "readOnly"}
        return {"type": "workspaceWrite", "writableRoots": [root["path"]], "networkAccess": False}

    def dispatch(self, operation: str, data: dict) -> dict:
        if not isinstance(data, dict):
            raise ValueError("data must be an object")
        # Snapshots, approvals and interrupt can proceed concurrently with a long RPC.
        if operation == "snapshot":
            self._scope(data.get("project"), data.get("thread"))
            self.expire_approvals()
            with self._lock:
                result = copy.deepcopy(self.views[data["thread"]])
                result["approvals"] = [self._public_approval(k, v) for k, v in self.pending.items()
                                       if v["threadId"] == data["thread"]]
                return result
        if operation == "approval":
            return self.decide(data)
        if operation == "interrupt":
            # Control-plane request must not queue behind turn/start or thread/list.
            self._scope(data.get("project"), data.get("thread"))
            self.require_chatgpt()
            with self._lock:
                turn = self.views[data["thread"]]["turnId"]
            if not turn:
                raise ValueError("No known active turn to interrupt")
            self.rpc.request("turn/interrupt", {"threadId": data["thread"], "turnId": turn})
            return {"requested": True}
        if operation == "status":
            self.require_chatgpt()
            return {"version": "0.1.0-dev", "codex": "connected", "authMode": "chatgpt",
                "voice": {"state": "unverified", "enabled": False, "paidApiFallback": False},
                "nativeHardwareTested": False, "protocolVersion": 2}
        if operation == "projects":
            return {"projects": [{"id": x["id"], "name": x["name"]}
                                 for x in self.projects.entries.values()]}
        # Reject unknown methods BEFORE contacting Codex.
        if operation not in {"threads", "newThread", "resume", "send", "models"}:
            raise ValueError("Unsupported operation")
        with self._op_lock:
            self.require_chatgpt()
            if operation == "models":
                return self.rpc.request("model/list", {})
            project = data.get("project")
            root = self.projects.get(project)
            if operation == "threads":
                params = {"cwd": root["path"], "limit": 30}
                cursor = data.get("cursor")
                if cursor is not None:
                    if not isinstance(cursor, str) or len(cursor) > 2048:
                        raise ValueError("Invalid cursor")
                    params["cursor"] = cursor
                result = self.rpc.request("thread/list", params)
                return {"threads": [{"id": t["id"], "name": t.get("name") or t.get("preview") or t["id"]}
                        for t in result.get("data", []) if self.projects.matches(project, t.get("cwd"))],
                        "nextCursor": result.get("nextCursor")}
            if operation == "newThread":
                result = self.rpc.request("thread/start", self._settings(project))
                ident = self._remember(project, result["thread"])
                return {"threadId": ident}
            thread = data.get("thread")
            if not isinstance(thread, str) or not thread or len(thread) > 160:
                raise ValueError("Invalid thread id")
            if operation == "resume":
                # Read and verify cwd before resuming or overriding any settings.
                with self._lock:
                    fresh_view = thread not in self.views
                stored = self.rpc.request("thread/read", {"threadId": thread, "includeTurns": False})
                self._remember(project, stored["thread"])
                result = self.rpc.request("thread/resume", {"threadId": thread, **self._settings(project)})
                self._remember(project, result["thread"])
                with self._lock:
                    self.views[thread]["text"] = self._history_text(result["thread"])
                    self.views[thread]["messages"], self.views[thread]["historyTruncated"] = history.from_thread(result["thread"])
                    # A newly resumed thread may already have an active turn. Never
                    # present it as idle merely because this bridge just started.
                    view = self.views[thread]
                    if fresh_view and view["status"] == "idle":
                        restored = result["thread"]
                        turns = restored.get("turns", [])
                        last = turns[-1] if turns else {}
                        live = restored.get("status", {})
                        kind = live.get("type") if isinstance(live, dict) else live
                        view["turnId"] = last.get("id")
                        if kind == "active" or last.get("status") == "inProgress":
                            view["status"] = "inProgress"
                        elif kind in ("systemError", "notLoaded"):
                            view["status"] = "unknown"
                        elif not turns:
                            view["status"] = "idle"
                        else:
                            status = last.get("status")
                            view["status"] = status if status in ("completed", "interrupted", "failed") else "unknown"
                    # Existing unknown/running views are intentionally never reset here.
                return {"threadId": thread}
            self._scope(project, thread)
            if operation == "send":
                prompt = data.get("text")
                if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode()) > 16000:
                    raise ValueError("Prompt must contain 1–16000 UTF-8 bytes")
                with self._lock:
                    if self.views[thread]["status"] in ("inProgress", "starting", "awaitingApproval", "unknown"):
                        raise ValueError("A turn is running or its outcome is unknown; inspect the existing thread")
                    self.views[thread].update(text="", diff="", tools=[], turnId=None, status="starting", truncated=False, diffTruncated=False)
                try:
                    result = self.rpc.request("turn/start", {"threadId": thread,
                        "input": [{"type": "text", "text": prompt}],
                        "cwd": root["path"], "approvalPolicy": self.approval_policy,
                        "sandboxPolicy": self._turn_sandbox(root)})
                    with self._lock:
                        self.views[thread]["turnId"] = result["turn"]["id"]
                        # A fast turn may have completed before the RPC response arrived.
                        if self.views[thread]["status"] == "starting":
                            self.views[thread]["status"] = "inProgress"
                    return {"turnId": result["turn"]["id"]}
                except BaseException:
                    with self._lock:
                        self.views[thread]["status"] = "unknown"
                    raise  # Never automatically retry: execution may already have started.
            raise ValueError("Unsupported operation")

    @staticmethod
    def _history_text(thread: dict) -> str:
        messages = []
        for turn in thread.get("turns", []):
            for item in turn.get("items", []):
                if item.get("type") == "agentMessage":
                    messages.append(item.get("text", ""))
        return "\n\n".join(messages)[-TEXT_LIMIT:]

    @staticmethod
    def _public_approval(key: str, item: dict) -> dict:
        return {"id": key, "method": item["method"], "threadId": item["threadId"],
                "details": item["details"], "expiresIn": max(0, int(item["deadline"] - time.monotonic()))}

    def on_message(self, message: dict) -> None:
        method = message.get("method", "")
        params = message.get("params") or {}
        if not isinstance(params, dict):
            if "id" in message:
                self.rpc.reply(message["id"], error={"code": -32602, "message": "Invalid params"})
            return
        tid = params.get("threadId")
        with self._lock:
            if method == "serverRequest/resolved":
                rid = params.get("requestId")
                for key in list(self.pending):
                    if self.pending[key]["rpcId"] == rid:
                        self.pending.pop(key)
                return
            if "id" in message:
                if method not in APPROVAL_METHODS or tid not in self.threads:
                    self.rpc.reply(message["id"], error={"code": -32601,
                        "message": "This client does not support this request or thread"})
                    return
                if len(self.pending) >= 16:
                    self.rpc.reply(message["id"], {"decision": "decline"})
                    return
                # Never truncate the command shown for approval; reject an oversized request.
                details = json.dumps(params, ensure_ascii=False, indent=2)
                if len(details.encode()) > 24000:
                    self.rpc.reply(message["id"], {"decision": "decline"})
                    return
                key = secrets.token_urlsafe(18)
                self.pending[key] = {"rpcId": message["id"], "method": method, "threadId": tid,
                                     "details": details, "deadline": time.monotonic() + 120}
                self.views[tid]["status"] = "awaitingApproval"
                return
            if tid not in self.threads:
                return
            view = self.views[tid]
            if method == "turn/started":
                view["turnId"] = params.get("turn", {}).get("id")
                view["status"] = "inProgress"
            elif method == "turn/completed":
                view["status"] = params.get("turn", {}).get("status", "unknown")
                for key in list(self.pending):
                    if self.pending[key]["threadId"] == tid:
                        self.pending.pop(key)  # Stale approval is never reused.
            elif method == "item/agentMessage/delta":
                text = view["text"] + params.get("delta", "")
                view["truncated"] = len(text) > TEXT_LIMIT
                view["text"] = text[-TEXT_LIMIT:]
            elif method == "turn/diff/updated":
                diff = params.get("diff", "")
                view["diff"] = diff[:TEXT_LIMIT]
                view["diffTruncated"] = len(diff) > TEXT_LIMIT
            elif method in ("item/started", "item/completed"):
                item = params.get("item", {})
                if item.get("type") == "agentMessage" and method == "item/completed":
                    view["text"] = item.get("text", view["text"])[-TEXT_LIMIT:]
                elif item.get("type") in ("commandExecution", "fileChange"):
                    compact = {k: item.get(k) for k in ("id", "type", "status", "command", "exitCode")}
                    view["tools"] = [x for x in view["tools"] if x["id"] != compact["id"]][-19:] + [compact]
            history.apply_event(view, method, params)
            self.event_seq += 1
            self.events.append({"seq": self.event_seq, "threadId": tid, "method": method})

    def decide(self, data: dict) -> dict:
        self._scope(data.get("project"), data.get("thread"))
        decision = data.get("decision")
        if not isinstance(data.get("approvalId"), str):
            raise ValueError("Invalid approval id")
        if decision not in ("accept", "decline"):
            raise ValueError("Only accept-once or decline is allowed")
        with self._lock:
            item = self.pending.get(data.get("approvalId"))
            if not item or item["threadId"] != data["thread"]:
                raise PermissionError("Unknown or stale approval")
            if item["deadline"] < time.monotonic():
                self.pending.pop(data["approvalId"])
                self.rpc.reply(item["rpcId"], {"decision": "decline"})
                raise PermissionError("Approval expired")
            # Exactly once. No 'accept for session' or persistent permission rules.
            self.pending.pop(data["approvalId"])
            self.rpc.reply(item["rpcId"], {"decision": decision})
            self.views[item["threadId"]]["status"] = "inProgress"
        return {"sent": True}

    def expire_approvals(self) -> None:
        with self._lock:
            expired = [k for k, v in self.pending.items() if v["deadline"] < time.monotonic()]
            for key in expired:
                item = self.pending.pop(key)
                self.rpc.reply(item["rpcId"], {"decision": "decline"})
