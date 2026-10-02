"""Resolve a locally installed Codex without executing shell/batch fragments.

This checks launcher layout, not publisher signatures. Install Codex from OpenAI;
local executables, package files and PATH are part of the trusted host boundary.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil


def resolve_command(command: list[str], *, windows: bool | None = None) -> list[str]:
    if not isinstance(command, list) or not command or not all(
        isinstance(arg, str) and arg and "\0" not in arg for arg in command
    ):
        raise ValueError("Codex command must be a nonempty argv list")
    windows = os.name == "nt" if windows is None else windows
    original = Path(command[0]).expanduser()
    found = str(original) if original.is_file() else shutil.which(command[0])
    if not found:
        raise FileNotFoundError("Codex executable not found. Configure its local path on the computer.")
    executable = Path(found).resolve()
    if not executable.is_file():
        raise FileNotFoundError("Configured executable is not a file")
    suffix = executable.suffix.lower()
    if windows and suffix in (".cmd", ".bat", ".ps1"):
        # Do not run cmd.exe /c or parse/execute any text in an npm shim.
        if executable.stem.lower() != "codex":
            raise ValueError("Only the official Codex npm launcher layout is supported")
        package = executable.parent / "node_modules" / "@openai" / "codex"
        manifest = package / "package.json"
        script = package / "bin" / "codex.js"
        if not manifest.is_file() or manifest.stat().st_size > 65536 or not script.is_file():
            raise ValueError("Codex npm layout not found; configure the actual Codex executable")
        metadata = json.loads(manifest.read_text(encoding="utf-8-sig"))
        if metadata.get("name") != "@openai/codex":
            raise ValueError("Unexpected npm package name")
        node = executable.parent / "node.exe"
        if not node.is_file():
            found_node = shutil.which("node.exe")
            if not found_node:
                raise FileNotFoundError("Node.js is required by this Codex npm installation")
            node = Path(found_node)
        if node.suffix.lower() != ".exe" or not node.is_file():
            raise ValueError("Node must be a native executable, not a batch wrapper")
        return [str(node.resolve()), str(script.resolve()), *command[1:]]
    if windows and suffix != ".exe":
        raise ValueError("Use a native .exe or the supported Codex npm launcher")
    return [str(executable), *command[1:]]
