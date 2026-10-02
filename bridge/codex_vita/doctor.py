"""Inspect the locally installed Codex without invoking a model or submitting audio."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
from .launcher import resolve_command
from .schema import field_literals


def literals(value, found):
    if isinstance(value, dict):
        if isinstance(value.get("const"), str):
            found.add(value["const"])
        if isinstance(value.get("enum"), list):
            found.update(x for x in value["enum"] if isinstance(x, str))
        for child in value.values():
            literals(child, found)
    elif isinstance(value, list):
        for child in value:
            literals(child, found)


def inspect(command: list[str]) -> dict:
    command = resolve_command(command)
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("CODEX_API_KEY", None)
    version = subprocess.run(command + ["--version"], capture_output=True, text=True,
                             timeout=15, check=True, env=env).stdout.strip()[:160]
    with tempfile.TemporaryDirectory(prefix="codex-vita-schema-") as temp:
        subprocess.run(command + ["app-server", "generate-json-schema", "--out", temp],
                       capture_output=True, timeout=60, check=True, env=env)
        values: set[str] = set()
        documents = {}
        for path in Path(temp).rglob("*.json"):
            if path.stat().st_size <= 20_000_000:
                document = json.loads(path.read_text(encoding="utf-8"))
                literals(document, values)
                if isinstance(document, dict):
                    documents[path.relative_to(temp).as_posix()] = document
    required = ["thread/start", "thread/resume", "thread/read", "turn/start", "turn/interrupt", "account/read", "thread/list", "model/list"]
    return {"codexVersion": version, "requiredMethods": {m: m in values for m in required},
        "threadApprovalPolicies": sorted(field_literals(documents, "ThreadStartParams", "approvalPolicy")),
        "turnApprovalPolicies": sorted(field_literals(documents, "TurnStartParams", "approvalPolicy")),
        "threadSandboxModes": sorted(field_literals(documents, "ThreadStartParams", "sandbox")),
        "audioRelatedSymbols": sorted(x for x in values if any(t in x.lower() for t in ("audio", "transcri", "realtime"))),
        "voiceValidated": False,
        "note": "Schema symbols are not proof of Dictate availability, account eligibility or zero additional charges."}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", default="codex", help="Path to the official executable (not a shell fragment)")
    parser.add_argument("--output", default=".local/capabilities.json")
    args = parser.parse_args()
    result = inspect([args.codex])
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
