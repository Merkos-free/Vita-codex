"""Real Git output into our C++ display parser, in a new temp repository only."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

class GitDiffContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        # No user/global Git configuration, hooks, credentials or signing.
        self.env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
        self.git('init', '-q')
        self.git('config', 'core.autocrlf', 'false')

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.root, env=self.env,
                              check=True, capture_output=True, timeout=10).stdout

    def put(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def index(self, *args):
        patch = self.git('diff', '--no-ext-diff', '--no-textconv', '--no-color', *args)
        result = subprocess.run([os.environ['CV_DIFF_PROBE']], input=patch,
                                capture_output=True, check=True, timeout=5)
        return json.loads(result.stdout)

    def test_unicode_path(self):
        self.put('имя.txt', b'old\n'); self.git('add', '.')
        self.put('имя.txt', b'new\n')
        item, = self.index()
        self.assertEqual(item['name'], 'имя.txt')
        self.assertEqual((item['added'], item['removed']), ('1', '1'))
        self.assertFalse(item['partial'])

    def test_spaces_in_path(self):
        self.put('folder with space/my file.ts', b'old\n'); self.git('add', '.')
        self.put('folder with space/my file.ts', b'new\n')
        self.assertEqual(self.index()[0]['name'], 'folder with space/my file.ts')

    def test_binary_without_headers(self):
        self.put('binary name.bin', b'\x00old'); self.git('add', '.')
        self.put('binary name.bin', b'\x00new')
        item, = self.index()
        self.assertEqual(item['name'], 'binary name.bin')
        self.assertTrue(item['binary'])

    def test_deletion(self):
        self.put('deleted.txt', b'old\n'); self.git('add', '.')
        (self.root/'deleted.txt').unlink()
        item, = self.index()
        self.assertEqual(item['name'], 'deleted.txt')
        self.assertEqual(item['removed'], '1')

    def test_rename(self):
        self.put('old name.txt', b'old\n'); self.git('add', '.')
        tree = self.git('write-tree').decode().strip()
        self.git('mv', 'old name.txt', 'new name.txt')
        item, = self.index('--cached', tree)
        self.assertEqual(item['name'], 'new name.txt')
        self.assertEqual(item['added'], '0')

    def test_new_file(self):
        self.put('new.txt', b'new\n'); self.git('add', '.')
        item, = self.index('--cached')
        self.assertEqual((item['name'], item['added']), ('new.txt','1'))

    def test_header_like_content(self):
        self.put('code.txt', b'-- false header\n'); self.git('add', '.')
        self.put('code.txt', b'++ false header\n')
        item, = self.index()
        self.assertEqual((item['name'], item['added'], item['removed']), ('code.txt','1','1'))

    def test_no_newline(self):
        self.put('code.txt', b'old'); self.git('add', '.')
        self.put('code.txt', b'new')
        item, = self.index()
        self.assertFalse(item['partial'])
        self.assertEqual((item['added'], item['removed']), ('1','1'))

if __name__ == '__main__':
    if not os.environ.get('CV_DIFF_PROBE') or not shutil.which('git'):
        raise SystemExit('CV_DIFF_PROBE and Git are required; no silent skips')
    unittest.main()
