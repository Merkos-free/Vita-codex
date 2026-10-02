"""TEST DOUBLE ONLY: never accesses a model, a real user account, or executes commands."""
import json
import os
import sys

def emit(obj):
    # The real JSONL wire format is UTF-8, independent of Windows console code pages.
    sys.stdout.buffer.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()

for line in sys.stdin.buffer:
    request = json.loads(line)
    method, ident = request.get("method"), request.get("id")
    if ident is None:
        continue
    if method == "initialize":
        emit({"id": ident, "result": {"userAgent": "fake-codex-test-only"}})
    elif method == "test/env":
        emit({"id": ident, "result": {"apiKeyPresent": any(k in os.environ for k in ("OPENAI_API_KEY", "CODEX_API_KEY"))}})
    elif method == "test/roundtrip":
        # Use an identical id for a server request: must not resolve the client Future.
        emit({"id": ident, "method": "test/serverRequest", "params": {"value": "Сервер"}})
        emit({"method": "test/event", "params": {"text": "Привет"}})
        emit({"id": ident, "result": request["params"]})
    elif method == "test/error":
        emit({"id": ident, "error": {"code": -32602, "message": "expected test error"}})
    elif method == "test/exit":
        break
    elif method == "test/wait":
        continue
    elif method:
        emit({"id": ident, "result": {}})
