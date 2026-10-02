"""Field-scoped schema inspection. Never infer a permission enum globally."""
from __future__ import annotations
from pathlib import PurePosixPath


def field_literals(documents: dict[str, dict], type_name: str, field: str) -> set[str]:
    result: set[str] = set()
    seen: set[tuple[str, str]] = set()

    def follow(node, filename: str):
        if not isinstance(node, dict):
            return
        if isinstance(node.get("const"), str):
            result.add(node["const"])
        result.update(x for x in node.get("enum", []) if isinstance(x, str))
        ref = node.get("$ref")
        if isinstance(ref, str) and (filename, ref) not in seen:
            seen.add((filename, ref))
            filepart, _, fragment = ref.partition("#")
            target_name = filename
            if filepart:
                candidate = PurePosixPath(filename).parent / filepart
                if candidate.is_absolute() or ".." in candidate.parts or ":" in filepart:
                    return  # no remote URLs or traversal
                target_name = str(candidate)
            target = documents.get(target_name)
            if fragment and not fragment.startswith("/"):
                return
            for part in fragment.strip("/").split("/") if fragment else []:
                if not isinstance(target, dict):
                    return
                target = target.get(part.replace("~1", "/").replace("~0", "~"))
            follow(target, target_name)
        for key in ("oneOf", "anyOf", "allOf"):
            for child in node.get(key, []):
                follow(child, filename)

    for filename, document in documents.items():
        candidates = []
        if document.get("title") == type_name or PurePosixPath(filename).stem == type_name:
            candidates.append(document)
        for key in ("definitions", "$defs"):
            candidate = document.get(key, {}).get(type_name)
            if isinstance(candidate, dict):
                candidates.append(candidate)
        for candidate in candidates:
            follow(candidate.get("properties", {}).get(field), filename)
    return result


def validate_capabilities(report: dict, approval_policy: str, sandbox: str) -> None:
    required = report.get("requiredMethods", {})
    if not required or not all(required.values()):
        raise ValueError("Installed Codex schema lacks required methods; inspect doctor output")
    if approval_policy not in report.get("threadApprovalPolicies", []):
        raise ValueError("approvalPolicy does not match ThreadStartParams in the installed Codex schema")
    if approval_policy not in report.get("turnApprovalPolicies", []):
        raise ValueError("approvalPolicy does not match TurnStartParams in the installed Codex schema")
    if sandbox not in report.get("threadSandboxModes", []):
        raise ValueError("sandbox does not match ThreadStartParams in the installed Codex schema")
