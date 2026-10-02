"""Host-only regression tests: no real Codex, microphone or cloud account."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
from codex_vita.launcher import resolve_command
from codex_vita.schema import field_literals, validate_capabilities
from codex_vita.core import Bridge
from codex_vita.security import Projects


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "space in path"
        self.root.mkdir()

    def npm(self, name="@openai/codex"):
        shim = self.root / "codex.cmd"
        shim.write_text("THIS FILE MUST NEVER EXECUTE", encoding="utf-8")
        package = self.root / "node_modules" / "@openai" / "codex"
        (package / "bin").mkdir(parents=True)
        (package / "bin" / "codex.js").write_text("// fixture", encoding="utf-8")
        (package / "package.json").write_text(json.dumps({"name": name}), encoding="utf-8")
        (self.root / "node.exe").write_bytes(b"fixture, not executable")
        return shim, package

    def test_explicit_native_executable(self):
        argv = resolve_command([sys.executable, "argument with spaces"], windows=False)
        self.assertEqual(argv, [str(Path(sys.executable).resolve()), "argument with spaces"])

    def test_npm_shim_is_not_executed(self):
        shim, package = self.npm()
        argv = resolve_command([str(shim), "app-server"], windows=True)
        self.assertEqual(argv, [str((self.root / "node.exe").resolve()),
                                str((package / "bin" / "codex.js").resolve()), "app-server"])
        self.assertNotIn(str(shim), argv)

    def test_wrong_package_rejected(self):
        shim, _ = self.npm("different-package")
        with self.assertRaises(ValueError):
            resolve_command([str(shim)], windows=True)

    def test_missing_layout_rejected(self):
        shim = self.root / "codex.cmd"; shim.touch()
        with self.assertRaises(ValueError):
            resolve_command([str(shim)], windows=True)

    def test_arbitrary_batch_rejected(self):
        shim = self.root / "other.bat"; shim.touch()
        with self.assertRaises(ValueError):
            resolve_command([str(shim)], windows=True)

    def test_missing_binary_rejected(self):
        with patch("codex_vita.launcher.shutil.which", return_value=None):
            with self.assertRaises(FileNotFoundError):
                resolve_command(["does-not-exist"], windows=True)

    def test_invalid_argv_rejected(self):
        for command in ([], "codex --help", [""], ["codex", "x\0y"]):
            with self.subTest(command=repr(command)):
                with self.assertRaises(ValueError):
                    resolve_command(command)

    def test_windows_script_not_a_native_executable(self):
        script = self.root / "random.js"; script.touch()
        with self.assertRaises(ValueError):
            resolve_command([str(script)], windows=True)


class SchemaTests(unittest.TestCase):
    def test_resolves_internal_enum_but_not_unrelated_literals(self):
        docs = {"bundle.json": {"$defs": {
            "ThreadStartParams": {"properties": {"approvalPolicy": {"$ref": "#/$defs/Approval"}}},
            "Approval": {"enum": ["onRequest", "never"]},
            "Unrelated": {"enum": ["untrusted", "workspaceWrite"]}
        }}}
        self.assertEqual(field_literals(docs, "ThreadStartParams", "approvalPolicy"), {"onRequest", "never"})

    def test_resolves_external_local_ref(self):
        docs = {"v2/ThreadStartParams.json": {"properties": {"sandbox": {"$ref": "Sandbox.json"}}},
                "v2/Sandbox.json": {"anyOf": [{"const": "readOnly"}, {"type": "null"}]}}
        self.assertEqual(field_literals(docs, "ThreadStartParams", "sandbox"), {"readOnly"})

    def test_no_remote_ref_and_no_global_guess(self):
        docs = {"ThreadStartParams.json": {"properties": {"sandbox": {"$ref": "https://example.invalid/schema"}},
                "unrelated": {"enum": ["readOnly"]}}}
        self.assertEqual(field_literals(docs, "ThreadStartParams", "sandbox"), set())

    def test_cyclic_ref_terminates(self):
        docs = {"a.json": {"$defs": {"ThreadStartParams": {"properties": {"sandbox": {"$ref": "#/$defs/Loop"}}},
                "Loop": {"$ref": "#/$defs/Loop"}}}}
        self.assertEqual(field_literals(docs, "ThreadStartParams", "sandbox"), set())

    def test_schema_gate(self):
        report = {"requiredMethods": {"thread/start": True}, "threadApprovalPolicies": ["onRequest"],
                  "turnApprovalPolicies": ["onRequest"], "threadSandboxModes": ["readOnly"]}
        validate_capabilities(report, "onRequest", "readOnly")
        for approval, sandbox in (("never", "readOnly"), ("onRequest", "workspaceWrite")):
            with self.assertRaises(ValueError): validate_capabilities(report, approval, sandbox)
        report["requiredMethods"]["thread/start"] = False
        with self.assertRaises(ValueError): validate_capabilities(report, "onRequest", "readOnly")


class PermissionTests(unittest.TestCase):
    def test_retired_or_auto_approval_rejected(self):
        class RPC: pass
        for policy in ("unlessTrusted", "untrusted", "never", "on-failure"):
            with self.assertRaises(ValueError): Bridge(RPC(), Projects([]), policy)

    def test_write_mode_requires_local_configuration(self):
        class RPC: pass
        bridge = Bridge(RPC(), Projects([]), "onRequest", "workspaceWrite")
        self.assertEqual(bridge._turn_sandbox({"path": "/scratch"}), {
            "type": "workspaceWrite", "writableRoots": ["/scratch"], "networkAccess": False})

    def test_default_is_read_only(self):
        class RPC: pass
        bridge = Bridge(RPC(), Projects([]))
        self.assertEqual(bridge._turn_sandbox({"path": "/scratch"}), {"type": "readOnly"})


if __name__ == "__main__": unittest.main()
