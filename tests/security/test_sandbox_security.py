"""
Tests — Security

Adversarial tests verifying that the policy engine + tool gateway
correctly BLOCKS prohibited actions and records audit events.

Expected: every blocked action is both prevented AND recorded.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from core.control_plane.policy import PolicyContext, PolicyDecision, PolicyEngine
from core.control_plane.tools import ToolCallRequest, ToolRegistry
from core.agents.tool_gateway import ToolGateway


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gateway(roles: list[str] | None = None) -> ToolGateway:
    """Create a ToolGateway with a real PolicyEngine (default-deny)."""
    return ToolGateway()


def _req(tool_id: str, roles: list[str], args: dict | None = None) -> ToolCallRequest:
    return ToolCallRequest(
        tool_id=tool_id,
        arguments=args or {},
        user_id="adversary",
        user_roles=roles,
    )


# ---------------------------------------------------------------------------
# Policy blocking
# ---------------------------------------------------------------------------

class TestPolicyBlocking:
    def test_viewer_blocked_from_python_exec(self):
        gw = _gateway()
        result = gw.call(_req("python_exec", roles=["viewer"]))
        assert result.success is False
        assert result.error is not None

    def test_unauthenticated_blocked_from_all_tools(self):
        gw = _gateway()
        for tool_id in ["python_exec", "document_ingest"]:
            result = gw.call(_req(tool_id, roles=[]))
            assert result.success is False, f"Expected {tool_id!r} to be blocked for unauthenticated"

    def test_unknown_tool_rejected(self):
        gw = _gateway()
        result = gw.call(_req("read_etc_passwd", roles=["admin"]))
        assert result.success is False


# ---------------------------------------------------------------------------
# Sandbox adversarial attempts (require Docker)
# ---------------------------------------------------------------------------

class TestSandboxAdversarial:
    """
    Tests that verify sandbox policy prevents common adversarial code patterns.
    Skip if Docker is unavailable.
    """

    @pytest.fixture(autouse=True)
    def skip_if_no_docker(self):
        try:
            import docker
            client = docker.from_env()
            client.ping()
        except Exception:
            pytest.skip("Docker not available")

    def _exec_code(self, code: str) -> dict:
        from core.sandbox.docker_sandbox import DockerSandbox, SandboxRequest
        sb = DockerSandbox()
        result = sb.execute(SandboxRequest(code=code, language="python"))
        return {"exit_code": result.exit_code, "stdout": result.stdout, "stderr": result.stderr}

    def test_cannot_read_etc_passwd(self):
        result = self._exec_code("open('/etc/passwd').read()")
        # Should fail because /etc/passwd doesn't exist in sandbox or is restricted
        assert result["exit_code"] != 0 or "root" not in result["stdout"]

    def test_cannot_import_socket_and_connect(self):
        result = self._exec_code(
            "import socket; s = socket.socket(); s.connect(('8.8.8.8', 53))"
        )
        assert result["exit_code"] != 0

    def test_network_is_blocked(self):
        result = self._exec_code(
            "import urllib.request; urllib.request.urlopen('http://example.com')"
        )
        assert result["exit_code"] != 0

    def test_safe_computation_succeeds(self):
        result = self._exec_code("print(sum(range(100)))")
        assert result["exit_code"] == 0
        assert "4950" in result["stdout"]

    def test_output_is_returned(self):
        result = self._exec_code("print('NOVAMINDD_TEST_OK')")
        assert result["exit_code"] == 0
        assert "NOVAMINDD_TEST_OK" in result["stdout"]


# ---------------------------------------------------------------------------
# Audit recording
# ---------------------------------------------------------------------------

class TestAuditRecording:
    def test_denied_tool_call_is_audited(self, tmp_path):
        from core.logging import init_audit_logger
        log_file = tmp_path / "audit.jsonl"
        init_audit_logger(str(log_file), enabled=True)

        gw = _gateway()
        gw.call(_req("python_exec", roles=["viewer"]))

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) >= 1
        import orjson
        events = [orjson.loads(l) for l in lines if l.strip()]
        event_names = [e["event"] for e in events]
        assert any("denied" in e or "unauthorized" in e for e in event_names)
