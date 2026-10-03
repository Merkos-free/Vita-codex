"""Launch the built Windows GUI and verify it stays idle. Never connects or logs in."""
from pathlib import Path
import argparse
import json
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('executable', type=Path)
parser.add_argument('report', type=Path)
args = parser.parse_args()
if args.report.exists():
    raise SystemExit('Refusing stale smoke-test report')
subprocess.run([str(args.executable.resolve()), '--smoke-test', str(args.report.resolve())],
               check=True, timeout=30, stdin=subprocess.DEVNULL)
result = json.loads(args.report.read_text(encoding='utf-8'))
assert result['guiCreated'] and result['phase'] == 'idle'
assert result['runtimeStarted'] is False and result['voiceEnabled'] is False
assert result['size'][0] >= 960 and result['size'][1] >= 720
print('Real packaged GUI opened and exited without starting a listener, Codex or model.')
