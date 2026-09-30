"""
NovaMindd — Structured Document IR (Intermediate Representation)

LLMs output structured JSON; deterministic renderers convert it to final artifacts.
This separation ensures: validation before rendering, reproducibility, and auditability.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class BlockType(str, Enum):
    HEADING1 = "heading1"
    HEADING2 = "heading2"
    HEADING3 = "heading3"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST = "list"
    CODE = "code"
    PAGE_BREAK = "page_break"


@dataclass
class TableCell:
    text: str
    bold: bool = False
    align: str = "left"   # left | center | right


@dataclass
class DocumentBlock:
    block_type: BlockType
    text: str = ""
    items: list[str] = field(default_factory=list)          # for lists
    rows: list[list[TableCell]] = field(default_factory=list)  # for tables
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentIR:
    """
    Language-model-agnostic intermediate representation of a document.
    Renderers consume this; LLMs produce it via structured output.
    """
    title: str
    author: str = "NovaMindd"
    blocks: list[DocumentBlock] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)

    def add_heading(self, text: str, level: int = 1) -> None:
        bt = {1: BlockType.HEADING1, 2: BlockType.HEADING2, 3: BlockType.HEADING3}
        self.blocks.append(DocumentBlock(block_type=bt.get(level, BlockType.HEADING2), text=text))

    def add_paragraph(self, text: str) -> None:
        self.blocks.append(DocumentBlock(block_type=BlockType.PARAGRAPH, text=text))

    def add_list(self, items: list[str]) -> None:
        self.blocks.append(DocumentBlock(block_type=BlockType.LIST, items=items))

    def add_table(self, rows: list[list[str]], header_row: bool = True) -> None:
        table_rows: list[list[TableCell]] = []
        for i, row in enumerate(rows):
            table_rows.append([
                TableCell(text=cell, bold=(i == 0 and header_row))
                for cell in row
            ])
        self.blocks.append(DocumentBlock(block_type=BlockType.TABLE, rows=table_rows))

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DocumentIR":
        import dataclasses
        # Simple reconstruction; extend with pydantic validation for production
        blocks = []
        for b in data.get("blocks", []):
            rows = [
                [TableCell(**c) for c in row]
                for row in b.get("rows", [])
            ]
            blocks.append(DocumentBlock(
                block_type=BlockType(b["block_type"]),
                text=b.get("text", ""),
                items=b.get("items", []),
                rows=rows,
                metadata=b.get("metadata", {}),
            ))
        return cls(
            title=data["title"],
            author=data.get("author", "NovaMindd"),
            blocks=blocks,
            metadata=data.get("metadata", {}),
            evidence_refs=data.get("evidence_refs", []),
        )
