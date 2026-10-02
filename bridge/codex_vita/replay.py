"""In-memory single-session mutation ledger. Full ledger refuses work, never evicts IDs."""
from __future__ import annotations
import copy
import hashlib
import json
import re
import threading


class ReplayConflict(ValueError):
    pass


class ReplayGuard:
    def __init__(self, capacity: int = 256):
        self.capacity = capacity
        self._lock = threading.Lock()
        self._entries = {}

    @staticmethod
    def _key(token: str, request_id: str):
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', request_id):
            raise ValueError('Mutation requires a valid requestId')
        return hashlib.sha256(token.encode()).hexdigest(), request_id

    def begin(self, token: str, request_id: str, operation: str, data: dict):
        key = self._key(token, request_id)
        fingerprint = hashlib.sha256(json.dumps([operation, data], sort_keys=True,
            ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()).hexdigest()
        with self._lock:
            item = self._entries.get(key)
            if item:
                if item['fingerprint'] != fingerprint:
                    raise ReplayConflict('requestId already belongs to different data')
                return False, copy.deepcopy(item)
            if len(self._entries) >= self.capacity:
                raise ReplayConflict('Mutation ledger full; restart bridge locally, do not retry old tasks')
            item = {'fingerprint': fingerprint, 'state': 'pending'}
            self._entries[key] = item
            return True, copy.deepcopy(item)

    def finish(self, token: str, request_id: str, status: int, response: dict):
        key = self._key(token, request_id)
        with self._lock:
            self._entries[key].update(state='done' if status < 400 else 'unknown',
                                      status=status, response=copy.deepcopy(response))

    def get(self, token: str, request_id: str):
        key = self._key(token, request_id)
        with self._lock:
            item = self._entries.get(key)
            if not item:
                return {'state': 'notFound'}  # Absence never authorizes resending automatically.
            return {k: copy.deepcopy(v) for k, v in item.items() if k != 'fingerprint'}
