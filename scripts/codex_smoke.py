"""Official pinned Codex handshake/schema smoke test with a clean home; NO model calls."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
from codex_vita.doctor import inspect
from codex_vita.rpc import RpcClient
from codex_vita.schema import validate_capabilities


def main():
    if len(sys.argv) != 3:
        raise SystemExit('Usage: codex_smoke.py official-codex-js output.json')
    entry = Path(sys.argv[1]).resolve()
    if not entry.is_file():
        raise SystemExit('Official Codex entrypoint is missing')
    node = shutil.which('node')
    if not node:
        raise SystemExit('Node is required')
    with tempfile.TemporaryDirectory(prefix='cv-codex-no-account-') as home:
        os.environ['CODEX_HOME'] = home
        for key in ('OPENAI_API_KEY', 'CODEX_API_KEY'):
            os.environ.pop(key, None)
        command = [node, str(entry)]
        report = inspect(command)
        if '0.155.1' not in report['codexVersion']:
            raise AssertionError('Unexpected Codex version')
        approval = next((v for v in ('on-request','onRequest') if v in report['threadApprovalPolicies'] and v in report['turnApprovalPolicies']), '')
        sandbox = next((v for v in ('read-only','readOnly') if v in report['threadSandboxModes']), '')
        validate_capabilities(report, approval, sandbox)
        rpc = RpcClient(command + ['app-server'])
        try:
            rpc.start()
            account = rpc.request('account/read', {'refreshToken': False})
            if account.get('account') is not None:
                raise AssertionError('Smoke environment unexpectedly has an account')
        finally:
            rpc.close()
        report.update(noAccountHandshake=True, modelCalls=0, hardwareTested=False,
                      selectedApproval=approval, selectedSandbox=sandbox)
        output = Path(sys.argv[2]);output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Official Codex schema and no-account handshake passed; no model/dictation test.')

if __name__ == '__main__':
    main()
