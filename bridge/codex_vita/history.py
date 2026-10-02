"""Bounded role-aware conversation view. No reasoning traces or raw tool payloads."""
from __future__ import annotations

MAX_MESSAGES = 64
MAX_HISTORY_BYTES = 65536


def clip(text: str, limit: int = MAX_HISTORY_BYTES) -> str:
    return text.encode('utf-8')[-limit:].decode('utf-8', errors='ignore')


def compact(messages: list[dict]) -> tuple[list[dict], bool]:
    output, remaining = [], MAX_HISTORY_BYTES
    truncated = len(messages) > MAX_MESSAGES
    for message in reversed(messages[-MAX_MESSAGES:]):
        text = str(message.get('text', ''))
        raw = text.encode('utf-8')
        if len(raw) > remaining:
            text = raw[-remaining:].decode('utf-8', errors='ignore') if remaining else ''
            truncated = True
        if text:
            output.append({'id': str(message.get('id', ''))[:160],
                           'role': message['role'], 'text': text})
            remaining -= len(text.encode('utf-8'))
        if remaining <= 0:
            truncated = True
            break
    return list(reversed(output)), truncated


def from_thread(thread: dict) -> tuple[list[dict], bool]:
    messages = []
    for turn in thread.get('turns', []):
        for item in turn.get('items', []):
            kind = item.get('type')
            if kind == 'userMessage':
                text = '\n'.join(x.get('text', '') for x in item.get('content', [])
                                 if isinstance(x, dict) and x.get('type') == 'text')
                role = 'user'
            elif kind == 'agentMessage':
                text, role = item.get('text', ''), 'assistant'
            else:
                continue
            if isinstance(text, str) and text:
                messages.append({'id': str(item.get('id', ''))[:160], 'role': role, 'text': text})
    return compact(messages)


def apply_event(view: dict, method: str, params: dict) -> None:
    messages = view.setdefault('messages', [])
    item = params.get('item', {})
    if method == 'item/agentMessage/delta':
        ident = str(params.get('itemId') or ('live-' + str(view.get('turnId'))))[:160]
        delta = params.get('delta', '')
        if not isinstance(delta, str):
            return
        existing = next((x for x in messages if x['id'] == ident), None)
        if existing:
            existing['text'] = clip(existing['text'] + delta)
        else:
            messages.append({'id': ident, 'role': 'assistant', 'text': clip(delta)})
    elif method in ('item/started', 'item/completed') and isinstance(item, dict):
        kind = item.get('type')
        if kind not in ('userMessage', 'agentMessage'):
            return
        converted, _ = from_thread({'turns': [{'items': [item]}]})
        if not converted:
            return
        value = converted[0]
        existing = next((x for x in messages if x['id'] == value['id']), None)
        if existing:
            existing.update(value)
        else:
            messages.append(value)
    else:
        return
    view['messages'], truncated = compact(messages)
    view['historyTruncated'] = view.get('historyTruncated', False) or truncated
