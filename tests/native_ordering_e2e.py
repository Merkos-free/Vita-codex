"""Run the original HTTPS suite plus a delayed-snapshot regression; explicit fixture only."""
import os
import shutil
import threading
import unittest
from unittest.mock import patch
import native_e2e as base
from codex_vita.server import Handler

class SnapshotOrdering(base.NativeEndToEnd):
    def test_old_snapshot_cannot_reenable_send_after_new_turn(self):
        self.connect()
        original = Handler._json
        captured, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def delayed_snapshot(handler, status, value):
            if not captured.is_set() and 'messages' in value and value.get('status') == 'idle':
                captured.set()
                release.wait(timeout=5)
            original(handler, status, value)
        with patch.object(Handler, '_json', delayed_snapshot):
            self.command('snapshot', ticks=80)
            self.assertTrue(captured.wait(timeout=2), 'Old snapshot was not captured')
            result = self.command('send', text='slow', ticks=100)
            self.assertTrue(result['accepted'], result)
            self.assertFalse(result['canSend'], result)
            release.set()
            result = self.command('pump')
        self.assertFalse(result['canSend'], result)
        self.assertEqual(result['view']['status'], 'inProgress', result)
        self.assertEqual(self.rpc.request('test/statistics', {})['sendCount'], 1)


if __name__ == '__main__':
    if not os.environ.get('CV_NATIVE_PROBE') or not shutil.which('openssl'):
        raise SystemExit('CV_NATIVE_PROBE and OpenSSL required')
    unittest.main()
