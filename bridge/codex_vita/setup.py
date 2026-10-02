"""Prepare a local read-only bridge and PUBLIC Vita trust bundle. Never starts a model."""
from __future__ import annotations
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
from .doctor import inspect
from .schema import validate_capabilities


def prepare(host: str, project: Path, output: Path, codex: str = 'codex') -> Path:
    address = ipaddress.IPv4Address(host)
    networks = ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','127.0.0.0/8')
    if not any(address in ipaddress.IPv4Network(n) for n in networks):
        raise ValueError('Only an explicit private or loopback IPv4 address is supported')
    project = project.resolve(strict=True)
    if not project.is_dir():
        raise ValueError('Select an existing test project directory')
    if output.exists():
        raise FileExistsError('Setup destination exists; it will not be overwritten')
    openssl = shutil.which('openssl')
    if not openssl:
        raise RuntimeError('OpenSSL is required locally for certificate generation')
    report = inspect([codex])
    approval = next((v for v in ('on-request','onRequest') if v in report['threadApprovalPolicies'] and v in report['turnApprovalPolicies']), '')
    sandbox = next((v for v in ('read-only','readOnly') if v in report['threadSandboxModes']), '')
    validate_capabilities(report, approval, sandbox)
    # Caller explicitly selects the destination. Use .local/ or a private user folder,
    # never a tracked source directory. No user account tokens are read/copied.
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    output = output.resolve()
    cert, key = output/'server.pem', output/'server-key.pem'
    try:
        subprocess.run([openssl,'req','-x509','-newkey','rsa:2048','-sha256','-nodes',
            '-days','30','-keyout',str(key),'-out',str(cert),'-subj','/CN=CodexVitaLocal',
            '-addext',f'subjectAltName=IP:{address}'], check=True, timeout=30,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)
        config = {'host':str(address),'port':8765,'codexCommand':[codex],
            'approvalPolicy':approval,'sandbox':sandbox,'tlsCert':str(cert),'tlsKey':str(key),
            'projects':[{'id':'project','name':project.name,'path':str(project)}]}
        with os.fdopen(os.open(output/'config.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w',encoding='utf-8') as f:
            json.dump(config,f,ensure_ascii=False,indent=2)
        vita = output/'vita';vita.mkdir()
        shutil.copyfile(cert,vita/'ca.pem')
        (vita/'connection.json').write_text(json.dumps({'endpoint':f'https://{address}:8765'}),encoding='utf-8')
        der = ssl.PEM_cert_to_DER_cert(cert.read_text(encoding='ascii'))
        (vita/'CERTIFICATE_SHA256.txt').write_text(hashlib.sha256(der).hexdigest()+'\n',encoding='ascii')
        return output/'config.json'
    except Exception:
        # Do not delete or reuse partial setup: preserving it avoids accidental overwrite.
        raise RuntimeError('Setup failed; partial destination was left in place. Use a new directory.') from None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',required=True)
    parser.add_argument('--project',required=True,type=Path)
    parser.add_argument('--output',type=Path,default=Path('.local/setup'))
    parser.add_argument('--codex',default='codex')
    args=parser.parse_args()
    config=prepare(args.host,args.project,args.output,args.codex)
    print(f'Prepared {config}. Bridge is NOT started; ChatGPT login is checked at startup.')
    print(f'Only {config.parent / "vita"} is copied to Vita; never copy server-key.pem.')
    print('Certificate expires in 30 days. No firewall changes, internet listener or model requests were made.')

if __name__=='__main__':
    main()
