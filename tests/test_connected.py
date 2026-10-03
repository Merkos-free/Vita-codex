"""Regression tests: replay protection, both conversation roles and priority interrupt."""
import copy
import json
import sys
import threading
import time
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
from codex_vita.history import from_thread, apply_event, compact
from codex_vita.replay import ReplayGuard, ReplayConflict
from codex_vita.server import unique_object, invalid_constant
import test_bridge as base


class HistoryTests(unittest.TestCase):
    def test_roles_and_no_reasoning(self):
        history, truncated = from_thread({'turns': [{'items': [
            {'id': 'u', 'type': 'userMessage', 'content': [{'type': 'text', 'text': 'Вопрос'}]},
            {'id': 'r', 'type': 'reasoning', 'text': 'private'},
            {'id': 'a', 'type': 'agentMessage', 'text': 'Ответ'}]}]})
        self.assertEqual([(x['role'], x['text']) for x in history], [('user', 'Вопрос'), ('assistant', 'Ответ')])
        self.assertFalse(truncated)

    def test_delta_completion_not_duplicated(self):
        v = {}
        apply_event(v, 'item/agentMessage/delta', {'itemId': 'a', 'delta': 'При'})
        apply_event(v, 'item/agentMessage/delta', {'itemId': 'a', 'delta': 'вет'})
        apply_event(v, 'item/completed', {'item': {'id': 'a', 'type': 'agentMessage', 'text': 'Привет'}})
        self.assertEqual(v['messages'], [{'id': 'a', 'role': 'assistant', 'text': 'Привет'}])

    def test_utf8_budget(self):
        h, truncated = compact([{'id': 'a', 'role': 'assistant', 'text': 'я' * 100000}])
        self.assertTrue(truncated)
        self.assertLessEqual(sum(len(x['text'].encode()) for x in h), 65536)
        self.assertNotIn('\ufffd', h[0]['text'])

    def test_count_budget(self):
        h, truncated = compact([{'id': str(i), 'role': 'user', 'text': 'x'} for i in range(100)])
        self.assertEqual(len(h), 64)
        self.assertTrue(truncated)


class ReplayTests(unittest.TestCase):
    def test_duplicate_returns_result(self):
        guard = ReplayGuard()
        self.assertTrue(guard.begin('token', 'r1', 'send', {'text': 'hi'})[0])
        guard.finish('token', 'r1', 200, {'turnId': 't'})
        fresh, entry = guard.begin('token', 'r1', 'send', {'text': 'hi'})
        self.assertFalse(fresh)
        self.assertEqual(entry['response']['turnId'], 't')

    def test_different_payload_refused(self):
        guard = ReplayGuard(); guard.begin('t', 'r', 'send', {'text': 'one'})
        with self.assertRaises(ReplayConflict): guard.begin('t', 'r', 'send', {'text': 'two'})

    def test_pending_unknown_and_missing_are_not_success(self):
        guard = ReplayGuard(); guard.begin('t', 'r', 'send', {})
        self.assertEqual(guard.get('t', 'r')['state'], 'pending')
        guard.finish('t', 'r', 504, {'error': 'unknown'})
        self.assertEqual(guard.get('t', 'r')['state'], 'unknown')
        self.assertEqual(guard.get('t', 'missing')['state'], 'notFound')
        self.assertEqual(guard.get('different-session', 'r')['state'], 'notFound')

    def test_full_ledger_never_evicts(self):
        guard = ReplayGuard(1);guard.begin('t', 'one', 'send', {})
        guard.finish('t', 'one', 200, {})
        with self.assertRaises(ReplayConflict):guard.begin('t', 'two', 'send', {})
        self.assertFalse(guard.begin('t', 'one', 'send', {})[0])

    def test_concurrent_reservation_exactly_one(self):
        guard = ReplayGuard(); results=[]
        threads=[threading.Thread(target=lambda: results.append(guard.begin('t', 'r', 'send', {})[0])) for _ in range(20)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(sum(results), 1)

    def test_invalid_ids(self):
        for ident in (None, '', '../x', 'я', 'a'*81):
            with self.assertRaises(ValueError): ReplayGuard().begin('t', ident, 'send', {})

    def test_json_duplicates_and_nonfinite_rejected(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(ValueError):json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid_constant)


class ConnectedCoreTests(unittest.TestCase):
    setUp = base.CoreTests.setUp
    open = base.CoreTests.open
    def test_interrupt_independent_of_operation_lock(self):
        self.open();self.bridge.views['t1']['turnId']='live'
        results=[]
        self.bridge._op_lock.acquire()
        thread=threading.Thread(target=lambda:results.append(self.bridge.dispatch('interrupt', {'project':'p1','thread':'t1'})))
        try:
            thread.start();thread.join(timeout=1)
            self.assertFalse(thread.is_alive(), 'interrupt incorrectly waited for operation lock')
            self.assertEqual(results, [{'requested': True}])
        finally:
            self.bridge._op_lock.release();thread.join(timeout=2)

    def test_history_in_snapshot(self):
        self.open()
        self.bridge.on_message({'method':'item/completed', 'params':{'threadId':'t1','item':{'id':'u','type':'userMessage','content':[{'type':'text','text':'Вопрос'}]}}})
        result=self.bridge.dispatch('snapshot', {'project':'p1','thread':'t1'})
        self.assertEqual(result['messages'][0]['role'], 'user')
        self.assertEqual(result['messages'][0]['text'], 'Вопрос')

    def test_status_protocol_v2_voice_off(self):
        result=self.bridge.dispatch('status', {})
        self.assertEqual(result['protocolVersion'], 2)
        self.assertFalse(result['voice']['enabled'])

    def test_fresh_resume_restores_active_turn(self):
        original = self.rpc.request
        def request(method, params):
            result = original(method, params)
            if method == 'thread/resume':
                result['thread']['turns'] = [{'id': 'running', 'status': 'inProgress', 'items': []}]
            return result
        self.rpc.request = request
        self.bridge.dispatch('resume', {'project': 'p1', 'thread': 't1'})
        self.assertEqual(self.bridge.views['t1']['status'], 'inProgress')
        self.assertEqual(self.bridge.views['t1']['turnId'], 'running')
        with self.assertRaises(ValueError):
            self.bridge.dispatch('send', {'project':'p1','thread':'t1','text':'Do not duplicate'})

    def test_resume_does_not_clear_unknown(self):
        self.open()
        self.bridge.views['t1']['status'] = 'unknown'
        self.bridge.dispatch('resume', {'project':'p1','thread':'t1'})
        self.assertEqual(self.bridge.views['t1']['status'], 'unknown')
