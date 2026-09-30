"""
NovaMindd — Validation Engine

Multi-stage validation: input → retrieval → tool arguments → output.
Fail-closed: validation failure halts the pipeline rather than passing bad data.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.logging import get_logger

logger = get_logger(__name__)


class ValidationLevel(str, Enum):
    INPUT = "input"
    RETRIEVAL = "retrieval"
    TOOL = "tool"
    OUTPUT = "output"


@dataclass
class ValidationError:
    level: ValidationLevel
    field: str
    message: str


@dataclass
class ValidationResult:
    passed: bool
    level: ValidationLevel
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, field: str, message: str) -> None:
        self.errors.append(ValidationError(level=self.level, field=field, message=message))
        self.passed = False

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


class ValidationEngine:
    """
    Validates data at every stage of the NovaMindd pipeline.

    Design principle: fail closed.
    An invalid result produces a ValidationResult with passed=False.
    The caller must halt the pipeline rather than continue with bad data.
    """

    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------

    def validate_file_upload(
        self,
        filename: str,
        content: bytes,
        allowed_extensions: set[str] | None = None,
        max_bytes: int = 50 * 1024 * 1024,
    ) -> ValidationResult:
        result = ValidationResult(passed=True, level=ValidationLevel.INPUT)
        if not filename:
            result.add_error("filename", "Filename is required")
        if not content:
            result.add_error("content", "File content is empty")
        if len(content) > max_bytes:
            result.add_error(
                "content",
                f"File size {len(content)} exceeds limit {max_bytes}",
            )
        if allowed_extensions:
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            if ext not in allowed_extensions:
                result.add_error(
                    "filename",
                    f"Extension .{ext!r} not in allowed set {allowed_extensions}",
                )
        return result

    # ------------------------------------------------------------------
    # Retrieval validation
    # ------------------------------------------------------------------

    def validate_evidence(
        self,
        evidence: list[Any],
        min_items: int = 1,
        min_score: float = 0.0,
    ) -> ValidationResult:
        result = ValidationResult(passed=True, level=ValidationLevel.RETRIEVAL)
        if len(evidence) < min_items:
            result.add_error(
                "evidence",
                f"Insufficient evidence: {len(evidence)} items, minimum {min_items} required",
            )
        low_quality = [e for e in evidence if getattr(e, "score", 1.0) < min_score]
        if low_quality:
            result.add_warning(
                f"{len(low_quality)} evidence items below score threshold {min_score}"
            )
        return result

    # ------------------------------------------------------------------
    # Tool argument validation
    # ------------------------------------------------------------------

    def validate_tool_arguments(
        self,
        arguments: dict[str, Any],
        schema: dict[str, Any],
    ) -> ValidationResult:
        """Validate arguments against a JSON Schema (required fields only)."""
        result = ValidationResult(passed=True, level=ValidationLevel.TOOL)
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for field_name in required:
            if field_name not in arguments:
                result.add_error(field_name, f"Required field {field_name!r} is missing")

        for field_name, value in arguments.items():
            if field_name not in properties:
                result.add_warning(f"Unexpected argument field: {field_name!r}")
                continue
            prop = properties[field_name]
            expected_type = prop.get("type")
            if expected_type and not self._check_type(value, expected_type):
                result.add_error(
                    field_name,
                    f"Field {field_name!r}: expected {expected_type}, got {type(value).__name__}",
                )
            if "maximum" in prop and isinstance(value, (int, float)):
                if value > prop["maximum"]:
                    result.add_error(
                        field_name,
                        f"Field {field_name!r}: value {value} exceeds maximum {prop['maximum']}",
                    )

        return result

    # ------------------------------------------------------------------
    # Output validation
    # ------------------------------------------------------------------

    def validate_agent_output(
        self,
        answer: str | None,
        evidence: list[Any],
        require_evidence: bool = True,
    ) -> ValidationResult:
        result = ValidationResult(passed=True, level=ValidationLevel.OUTPUT)
        if answer is None or not answer.strip():
            result.add_error("answer", "Agent produced no answer")
        if require_evidence and not evidence:
            result.add_error(
                "evidence",
                "Output produced with no supporting evidence (fail-closed)",
            )
        return result

    def validate_artifact_ir(self, ir_dict: dict[str, Any]) -> ValidationResult:
        result = ValidationResult(passed=True, level=ValidationLevel.OUTPUT)
        if not ir_dict.get("title"):
            result.add_error("title", "Document IR must have a title")
        if "blocks" not in ir_dict:
            result.add_error("blocks", "Document IR must have a blocks list")
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_type(value: Any, expected: str) -> bool:
        mapping = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        t = mapping.get(expected)
        if t is None:
            return True   # unknown type — skip
        return isinstance(value, t)
