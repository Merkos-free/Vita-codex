"""One-time pairing, expiring device tokens, strict allowlisted project roots."""
from __future__ import annotations
import hashlib
import hmac
import secrets
import threading
import time
from pathlib import Path

class Pairing:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self._lock = threading.Lock()
        self.pin = f"{secrets.randbelow(1_000_000):06d}"
        self.deadline = clock() + 120
        self.attempts = 0
        self.used = False
        self._tokens: dict[str, float] = {}

    def exchange(self, pin: str) -> str:
        with self._lock:
            if self.used or self.clock() > self.deadline or self.attempts >= 5:
                raise PermissionError("Pairing closed; restart the bridge locally")
            self.attempts += 1
            if not isinstance(pin, str) or len(pin) != 6 or not pin.isascii() or not pin.isdigit() or not hmac.compare_digest(pin, self.pin):
                raise PermissionError("Invalid pairing code")
            token = secrets.token_urlsafe(32)
            self._tokens[hashlib.sha256(token.encode()).hexdigest()] = self.clock() + 86400
            self.used = True
            return token

    def check(self, token: str) -> bool:
        if not isinstance(token, str) or not 32 <= len(token) <= 128:
            return False
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self._lock:
            deadline = self._tokens.get(digest)
            return deadline is not None and self.clock() < deadline

    def revoke_all(self) -> None:
        with self._lock:
            self._tokens.clear()

class Projects:
    def __init__(self, entries: list[dict]):
        self.entries: dict[str, dict] = {}
        for entry in entries:
            ident = entry.get("id", "")
            if not ident or len(ident) > 80 or not all(c.isalnum() or c in "-_" for c in ident):
                raise ValueError("Invalid project id")
            path = Path(entry["path"]).expanduser()
            if not path.is_absolute() or not path.is_dir():
                raise ValueError("Every project needs an existing absolute directory")
            if ident in self.entries:
                raise ValueError("Duplicate project id")
            self.entries[ident] = {"id": ident, "name": entry.get("name", ident),
                                  "path": str(path.resolve())}

    def get(self, ident: str) -> dict:
        if not isinstance(ident, str) or ident not in self.entries:
            raise PermissionError("Project is not allowlisted")
        return self.entries[ident].copy()

    def matches(self, ident: str, cwd: str | None) -> bool:
        if not isinstance(cwd, str) or not cwd or not Path(cwd).is_absolute():
            return False
        return Path(cwd).resolve() == Path(self.get(ident)["path"])
