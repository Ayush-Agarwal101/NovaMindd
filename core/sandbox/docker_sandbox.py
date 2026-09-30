"""
NovaMindd — Docker Sandbox

Executes code inside an isolated Docker container with:
- non-root user
- restricted filesystem (read-only root, writable /workspace)
- CPU and memory limits
- network isolation (network_mode=none by default)
- credential isolation (no host env vars)
- configurable timeout

The sandbox is the sole execution path; no code runs directly on the host.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from core.config import get_config
from core.logging import get_audit_logger, get_logger

logger = get_logger(__name__)


@dataclass
class SandboxRequest:
    code: str
    language: str = "python"
    timeout_seconds: int | None = None
    environment: dict[str, str] = field(default_factory=dict)
    request_id: str | None = None


@dataclass
class SandboxResult:
    request_id: str
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: int
    blocked: bool = False       # True if sandbox policy prevented execution
    block_reason: str | None = None


class DockerSandbox:
    """
    Runs code inside a locked-down Docker container.

    Security properties enforced:
    - Non-root UID/GID (65534 / nobody)
    - Read-only root filesystem
    - No new privileges (--security-opt no-new-privileges)
    - Network disabled by default (network_mode=none)
    - CPU + memory hard limits
    - Automatic container removal on exit
    - No host filesystem mounts
    - No host environment variable leakage
    """

    def __init__(self) -> None:
        self._cfg = get_config()
        self._sandbox_cfg = self._cfg.sandbox
        self._exec_policy = self._cfg.policies.execution

    def execute(self, request: SandboxRequest) -> SandboxResult:
        """Execute code inside the sandbox. Returns immediately with the result."""
        import docker
        from docker.errors import DockerException

        req_id = request.request_id or str(uuid.uuid4())
        timeout = min(
            request.timeout_seconds or self._exec_policy.timeout_seconds,
            self._exec_policy.timeout_seconds,
        )

        start_ms = time.monotonic()
        try:
            client = docker.from_env()
        except DockerException as exc:
            logger.error("sandbox_docker_unavailable", error=str(exc))
            return SandboxResult(
                request_id=req_id,
                success=False,
                stdout="",
                stderr=f"Docker unavailable: {exc}",
                exit_code=-1,
                execution_time_ms=0,
            )

        mem_bytes = self._exec_policy.memory_limit_mb * 1024 * 1024
        cpu_quota = int(float(self._exec_policy.cpu_limit) * 100_000)

        container_kwargs = {
            "image": self._sandbox_cfg.image,
            "command": ["python3", "-c", request.code] if request.language == "python" else ["sh", "-c", request.code],
            "detach": True,
            "remove": False,                          # we remove manually after log capture
            "network_mode": self._sandbox_cfg.network_mode,
            "user": "65534:65534",                   # nobody
            "read_only": True,
            "tmpfs": {"/workspace": "size=64m,uid=65534"},
            "security_opt": ["no-new-privileges:true"],
            "cap_drop": ["ALL"],
            "mem_limit": mem_bytes,
            "cpu_quota": cpu_quota,
            "cpu_period": 100_000,
            "environment": {},                        # no host env leakage
            "labels": {
                "novamindd.request_id": req_id,
                "novamindd.sandbox": "true",
            },
        }

        container = None
        try:
            container = client.containers.run(**container_kwargs)
            try:
                exit_status = container.wait(timeout=timeout)
            except Exception:
                container.kill()
                exit_status = {"StatusCode": -1}

            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
            exit_code = exit_status.get("StatusCode", -1)

            # Truncate if output exceeds policy limit
            max_bytes = self._exec_policy.max_output_size_bytes
            if len(stdout.encode()) > max_bytes:
                stdout = stdout[: max_bytes // 2] + "\n[TRUNCATED]"
            if len(stderr.encode()) > max_bytes:
                stderr = stderr[: max_bytes // 2] + "\n[TRUNCATED]"

        except Exception as exc:
            logger.error("sandbox_execution_error", request_id=req_id, error=str(exc))
            stdout, stderr, exit_code = "", str(exc), -1
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

        elapsed_ms = int((time.monotonic() - start_ms) * 1000)
        success = exit_code == 0

        # Audit every sandbox execution
        try:
            get_audit_logger().log(
                "sandbox_execution",
                request_id=req_id,
                language=request.language,
                exit_code=exit_code,
                execution_time_ms=elapsed_ms,
                stdout_len=len(stdout),
                stderr_len=len(stderr),
            )
        except RuntimeError:
            pass  # audit logger not initialised in test environments

        return SandboxResult(
            request_id=req_id,
            success=success,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            execution_time_ms=elapsed_ms,
        )
