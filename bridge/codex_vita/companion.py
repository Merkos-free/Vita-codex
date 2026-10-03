"""Local desktop lifecycle. No model turns, automatic login, firewall or API fallback.

The GUI polls immutable snapshots on the Tk thread. Slow setup, local Codex
startup and server shutdown are owned by one worker, never by a button handler.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
import hashlib
import ipaddress
import json
from pathlib import Path
import ssl
import threading
import zipfile
from .core import Bridge
from .doctor import inspect
from .rpc import RpcClient
from .schema import validate_capabilities
from .security import Pairing, Projects
from .server import make_server, unique_object, invalid_constant
from .setup import prepare


@dataclass(frozen=True)
class State:
    phase: str = 'idle'
    message: str = 'Выберите тестовый проект. Сервер выключен.'
    config: str = ''
    endpoint: str = ''
    pin: str = ''
    seconds: int = 0
    paired: bool = False


def private_ipv4(host: str) -> str:
    address = ipaddress.IPv4Address(host)
    if not any(address in ipaddress.IPv4Network(n) for n in
               ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.0/8')):
        raise ValueError('Select a private or loopback IPv4 address')
    return str(address)


def read_small(path: Path, limit: int = 65536) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError('Select a regular local file')
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Local configuration exceeds limit')
    return data


def read_config(path: Path) -> dict:
    """GUI intentionally accepts only private HTTPS + read-only configurations."""
    data = json.loads(read_small(path).decode('utf-8-sig'),
                      object_pairs_hook=unique_object, parse_constant=invalid_constant)
    if not isinstance(data, dict):
        raise ValueError('Configuration must be an object')
    data['host'] = private_ipv4(data['host'])
    if type(data.get('port')) is not int or not 1024 <= data['port'] <= 65535:
        raise ValueError('Select an unprivileged TCP port')
    if data.get('sandbox') not in ('read-only', 'readOnly'):
        raise ValueError('Desktop companion supports read-only mode only')
    if data.get('approvalPolicy') not in ('on-request', 'onRequest'):
        raise ValueError('On-request approval is required')
    argv = data.get('codexCommand')
    if not isinstance(argv, list) or not argv or len(argv) > 8 or not all(
            isinstance(v, str) and v and '\0' not in v and len(v) <= 4096 for v in argv):
        raise ValueError('Invalid local executable configuration')
    entries = data.get('projects')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 128:
        raise ValueError('Select at least one explicit project')
    projects = Projects(entries)
    for entry in projects.entries.values():
        if path.resolve().is_relative_to(Path(entry['path'])):
            raise ValueError('Private configuration must be outside the project')
    for field in ('tlsCert', 'tlsKey'):
        if not isinstance(data.get(field), str) or not Path(data[field]).is_absolute():
            raise ValueError('Absolute certificate and private key paths are required')
        read_small(Path(data[field]))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(data['tlsCert'], data['tlsKey'], password='')
    return data


def export_public_bundle(config_path: Path, destination: Path) -> None:
    """Explicit export of exactly three validated PUBLIC files; never state folder."""
    config = read_config(config_path)
    folder = config_path.resolve().parent / 'vita'
    names = ('ca.pem', 'connection.json', 'CERTIFICATE_SHA256.txt')
    payload = {name: read_small(folder / name) for name in names}
    if any(b'PRIVATE KEY' in value for value in payload.values()):
        raise ValueError('Private key material is forbidden in public export')
    ca = payload['ca.pem']
    if ca != read_small(Path(config['tlsCert'])) or ca.count(b'BEGIN CERTIFICATE') != 1:
        raise ValueError('Export certificate does not match this server')
    fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(ca.decode('ascii'))).hexdigest()
    if payload['CERTIFICATE_SHA256.txt'].decode('ascii').strip() != fingerprint:
        raise ValueError('Certificate fingerprint mismatch')
    connection = json.loads(payload['connection.json'], object_pairs_hook=unique_object)
    if connection != {'endpoint': f'https://{config["host"]}:{config["port"]}'}:
        raise ValueError('Export endpoint does not match this server')
    # Exclusive creation: even an existing archive is not silently replaced.
    with destination.open('xb') as output:
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in names:
                archive.writestr(name, payload[name])


class Companion:
    def __init__(self):
        self._lock = threading.RLock()
        self._state = State()
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._worker is not None and self._worker.is_alive()

    def snapshot(self) -> State:
        with self._lock:
            return replace(self._state)

    def _set(self, **changes) -> None:
        with self._lock:
            self._state = replace(self._state, **changes)

    def _launch(self, phase: str, task, *args) -> bool:
        with self._lock:
            if self.busy:
                return False
            self._stop.clear()
            self._state = State(phase=phase, message='Выполняется локальная проверка...')
            self._worker = threading.Thread(target=task, args=args, name='vita-companion', daemon=True)
            self._worker.start()
            return True

    def prepare(self, host: str, project: Path, output: Path, codex: str = 'codex') -> bool:
        return self._launch('preparing', self._prepare, host, project, output, codex)

    def _prepare(self, host: str, project: Path, output: Path, codex: str) -> None:
        try:
            private_ipv4(host)
            project = project.resolve(strict=True)
            if output.resolve().is_relative_to(project) or project.is_relative_to(output.resolve()):
                raise ValueError('Keep private state separate from project source')
            config = prepare(host, project, output, codex)
            if self._stop.is_set():
                self._set(phase='stopped', message='Отменено. Подготовленная папка сохранена; сервер не запускался.')
            else:
                self._set(phase='prepared', config=str(config), endpoint=f'https://{host}:8765',
                          message='Готово. Перенесите публичный комплект на Vita, затем нажмите «Запустить».')
        except Exception:
            self._set(phase='error', message='Подготовка не удалась: проверьте Codex, OpenSSL, IP и новую папку вне проекта.')

    def start(self, config: Path) -> bool:
        return self._launch('starting', self._serve, config)

    def stop(self) -> None:
        self._stop.set()
        if self.busy:
            self._set(phase='stopping', pin='', seconds=0, message='Остановка. Новые действия не запускаются.')

    def wait(self, timeout: float = 5) -> bool:
        """For tests/CLI only: a Tk callback must poll busy instead of joining."""
        worker = self._worker
        if worker:
            worker.join(timeout)
        return not self.busy

    def _serve(self, config_path: Path) -> None:
        rpc = server = pairing = serving = None
        failure = ''
        phase = 'config'
        try:
            config = read_config(config_path)
            if self._stop.is_set():
                return
            phase = 'schema'
            report = inspect(config['codexCommand'])
            validate_capabilities(report, config['approvalPolicy'], config['sandbox'])
            if self._stop.is_set():
                return
            phase = 'login'
            rpc = RpcClient(config['codexCommand'] + ['app-server'])
            bridge = Bridge(rpc, Projects(config['projects']), config['approvalPolicy'], config['sandbox'])
            rpc.start()
            bridge.require_chatgpt()
            if self._stop.is_set():
                return
            phase = 'listen'
            pairing = Pairing()
            server = make_server(config['host'], config['port'], bridge, pairing,
                                 config['tlsCert'], config['tlsKey'])
            if self._stop.is_set():
                return
            serving = threading.Thread(target=server.serve_forever,
                                       kwargs={'poll_interval': .1}, daemon=True)
            serving.start()
            while not self._stop.is_set():
                if not serving.is_alive() or not rpc.alive:
                    raise RuntimeError('Owned server or Codex exited')
                bridge.expire_approvals()
                status = pairing.local_status()
                self._set(phase='running', config=str(config_path),
                          endpoint=f'https://{config["host"]}:{config["port"]}',
                          pin=status['pin'], seconds=status['seconds'], paired=status['paired'],
                          message='Устройство сопряжено.' if status['paired'] else
                          ('Введите код в Vita.' if status['pin'] else 'Код закрыт. Для нового кода остановите и запустите Bridge.'))
                self._stop.wait(.1)
        except Exception:
            failure = {'config': 'Проверьте read-only конфигурацию, IP, сертификат и ключ.',
                       'schema': 'Не удалось подтвердить совместимость установленного Codex.',
                       'login': 'Codex не подтвердил ChatGPT-вход. Войдите самостоятельно в официальный Codex.',
                       'listen': 'Сервер или Codex остановился. Проверьте занятый порт и локальную установку.'}[phase]
        finally:
            # Never leave a usable device token when the local GUI stops its runtime.
            if pairing:
                pairing.revoke_all()
            try:
                if server:
                    server.stop_event.set()
                    if serving and serving.is_alive():
                        server.shutdown()
                    server.server_close()
                if serving:
                    serving.join(timeout=2)
                if rpc:
                    rpc.close()
            except Exception:
                failure = 'Завершение не подтверждено. Проверьте собственный процесс Codex на компьютере.'
            self._set(phase='error' if failure else 'stopped', pin='', seconds=0, paired=False,
                      message=failure or 'Bridge выключен; токены отозваны. Это не откат файлов и не гарантия остановки фоновых команд.')
