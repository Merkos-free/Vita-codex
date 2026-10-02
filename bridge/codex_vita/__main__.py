from __future__ import annotations
import argparse
import json
from pathlib import Path
import threading
from .rpc import RpcClient
from .security import Pairing, Projects
from .core import Bridge
from .server import make_server
from .doctor import inspect
from .schema import validate_capabilities


def main():
    parser = argparse.ArgumentParser(description="Codex Vita personal companion")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8-sig"))
    projects = Projects(config["projects"])
    command = config.get("codexCommand", ["codex"])
    if not isinstance(command, list):
        raise ValueError("codexCommand must be an argv list")
    approval = config.get("approvalPolicy", "onRequest")
    sandbox = config.get("sandbox", "readOnly")
    report = inspect(command)  # local schema/version only; no model or account secret reads
    validate_capabilities(report, approval, sandbox)
    rpc = RpcClient(command + ["app-server"])
    bridge = Bridge(rpc, projects, approval, sandbox)
    pairing = Pairing()
    server = None
    try:
        rpc.start()
        bridge.require_chatgpt()
        server = make_server(config.get("host", "127.0.0.1"), config.get("port", 8765),
            bridge, pairing, config.get("tlsCert"), config.get("tlsKey"))
        print("Codex Vita dev bridge. ChatGPT login verified. Native client/voice are not hardware-validated.")
        print(f"Pairing code: {pairing.pin}  (one device, 120 seconds, max 5 attempts)")
        print("Restarting revokes device tokens. Never publish this service on the internet.")
        print("Ctrl+C stops the bridge. Stopping the bridge does NOT undo file changes or guarantee termination of background commands.")
        def expire():
            while not server.stop_event.wait(1):
                try:
                    bridge.expire_approvals()
                except Exception:
                    server.stop_event.set()
        threading.Thread(target=expire, daemon=True).start()
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        pairing.revoke_all()
        if server:
            server.stop_event.set()
            server.server_close()
        rpc.close()

if __name__ == "__main__":
    main()
