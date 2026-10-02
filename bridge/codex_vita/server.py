"""Development HTTPS transport. Not a public multi-user hosting service."""
from __future__ import annotations
import ipaddress
import json
import socket
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .rpc import RpcError

MAX_BODY = 32768

class LimitedServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    def __init__(self, address, handler, bridge, pairing):
        self.slots = threading.BoundedSemaphore(8)
        self.bridge, self.pairing = bridge, pairing
        self.stop_event = threading.Event()
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            if isinstance(request, ssl.SSLSocket):
                try:
                    request.do_handshake()
                except (ssl.SSLError, OSError):
                    self.shutdown_request(request)
                    return
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def get_request(self):
        sock, address = super().get_request()
        sock.settimeout(10)
        return sock, address

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "CodexVita/0.1"

    def log_message(self, *_):
        pass  # Never log PIN, Authorization, prompts, source code or account details.

    def _json(self, status: int, value: dict):
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def _origin_ok(self):
        # Native client only. Reject all browser origins, even localhost/null.
        if self.headers.get("Origin") is not None:
            self._json(403, {"error": "Browser-origin requests are disabled"})
            return False
        return True

    def do_GET(self):
        if not self._origin_ok():
            return
        if self.path == "/healthz":
            self._json(200, {"ok": True})
        else:
            self._json(404, {"error": "Not found"})

    def do_POST(self):
        if not self._origin_ok():
            return
        try:
            if self.path not in ("/v1/pair", "/v1/action"):
                self._json(404, {"error": "Not found"})
                return
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Chunked requests are not supported")
            lengths = self.headers.get_all("Content-Length") or []
            if len(lengths) != 1:
                raise ValueError("One Content-Length is required")
            length = int(lengths[0])
            if length <= 0 or length > MAX_BODY:
                self._json(413, {"error": "Request body too large or empty"})
                return
            if self.headers.get_content_type() != "application/json":
                self._json(415, {"error": "Use application/json"})
                return
            if self.path == "/v1/action":
                auth = self.headers.get("Authorization", "")
                if not auth.startswith("Bearer ") or not self.server.pairing.check(auth[7:]):
                    self._json(401, {"error": "Pair this device first"})
                    return
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("Incomplete request")
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError("Request must be an object")
            if self.path == "/v1/pair":
                token = self.server.pairing.exchange(body.get("pin"))
                self._json(200, {"token": token, "expiresIn": 86400})
                return
            operation = body.get("operation")
            if not isinstance(operation, str):
                raise ValueError("operation must be a string")
            result = self.server.bridge.dispatch(operation, body.get("data", {}))
            self._json(200, result)
        except PermissionError as exc:
            self._json(403, {"error": str(exc)})
        except (ValueError, TypeError, KeyError, UnicodeError):
            self._json(400, {"error": "Invalid request or unsupported operation"})
        except TimeoutError:
            self._json(504, {"error": "Codex response timed out. Do not resend automatically; inspect the thread."})
        except RpcError as exc:
            self._json(502, {"error": "Codex request failed. Check local login, schema and sandbox setup.",
                             "rpcCode": exc.code})
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            return
        except Exception:
            self._json(500, {"error": "Internal bridge error; no details exposed over the network"})

    def do_OPTIONS(self):
        self._json(403, {"error": "Browser clients are disabled"})


def make_server(host: str, port: int, bridge, pairing, cert=None, key=None):
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host == "localhost"
    if not loopback and not (cert and key):
        raise ValueError("Non-loopback binding requires TLS certificate and key")
    if bool(cert) != bool(key):
        raise ValueError("Provide both TLS certificate and key")
    if host != "localhost" and ":" in host:
        raise ValueError("This development server currently supports IPv4 only")
    server = LimitedServer((host, port), Handler, bridge, pairing)
    if cert:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cert, key)
        server.socket = context.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
    return server
