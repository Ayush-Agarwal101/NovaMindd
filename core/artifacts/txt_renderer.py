"""
NovaMindd — Plain-text Renderer

Renders a DocumentIR into a clean .txt file.
No dependencies required.
"""
from __future__ import annotations

from core.artifacts.ir import BlockType, DocumentIR
from core.logging import get_logger

logger = get_logger(__name__)

_SEPARATOR = "=" * 72


class TXTRenderer:
    """Render DocumentIR → bytes (UTF-8 plain text)."""

    def render(self, doc_ir: DocumentIR) -> bytes:
        lines: list[str] = []

        # Title block
        lines.append(_SEPARATOR)
        lines.append(doc_ir.title.upper())
        if doc_ir.author and doc_ir.author != "NovaMindd":
            lines.append(f"Author: {doc_ir.author}")
        lines.append(_SEPARATOR)
        lines.append("")

        for block in doc_ir.blocks:
            bt = block.block_type

            if bt == BlockType.HEADING1:
                lines.append("")
                lines.append(block.text.upper())
                lines.append("-" * min(len(block.text), 72))

            elif bt == BlockType.HEADING2:
                lines.append("")
                lines.append(f"## {block.text}")

            elif bt == BlockType.HEADING3:
                lines.append(f"### {block.text}")

            elif bt == BlockType.PARAGRAPH:
                lines.append("")
                lines.append(block.text)

            elif bt == BlockType.LIST:
                lines.append("")
                for item in block.items:
                    lines.append(f"  • {item}")

            elif bt == BlockType.CODE:
                lines.append("")
                lines.append("```")
                lines.append(block.text)
                lines.append("```")

            elif bt == BlockType.TABLE:
                if block.rows:
                    lines.append("")
                    col_widths = self._col_widths(block.rows)
                    for row_idx, row in enumerate(block.rows):
                        row_str = "  ".join(
                            cell.text.ljust(col_widths[col_idx])
                            for col_idx, cell in enumerate(row)
                        )
                        lines.append(row_str)
                        if row_idx == 0:  # header separator
                            lines.append("  ".join("-" * w for w in col_widths))

            elif bt == BlockType.PAGE_BREAK:
                lines.append("")
                lines.append("\f")   # form-feed

        # Evidence references appendix
        if doc_ir.evidence_refs:
            lines.append("")
            lines.append(_SEPARATOR)
            lines.append("EVIDENCE REFERENCES")
            lines.append(_SEPARATOR)
            for ref in doc_ir.evidence_refs:
                lines.append(
                    f"  {ref.get('document_id', '?')}  "
                    f"page {ref.get('page', '?')}  "
                    f"score {ref.get('score', 0):.3f}"
                )

        lines.append("")
        content = "\n".join(lines)
        logger.debug("txt_rendered", title=doc_ir.title, blocks=len(doc_ir.blocks))
        return content.encode("utf-8")

    @staticmethod
    def _col_widths(rows: list) -> list[int]:
        if not rows:
            return []
        n_cols = max(len(r) for r in rows)
        widths = [0] * n_cols
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(cell.text))
        return widths
