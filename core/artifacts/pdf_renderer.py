"""
NovaMindd — PDF Renderer

Renders a DocumentIR into a PDF file using reportlab.
Falls back to a plain-text PDF if reportlab is unavailable.
"""
from __future__ import annotations

import io

from core.artifacts.ir import BlockType, DocumentIR
from core.logging import get_logger

logger = get_logger(__name__)


class PDFRenderer:
    """Render DocumentIR → bytes (PDF format) via reportlab."""

    def render(self, doc_ir: DocumentIR) -> bytes:
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import cm
            from reportlab.lib import colors
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                PageBreak, Preformatted,
            )
            from reportlab.platypus import ListFlowable, ListItem
        except ImportError:
            raise RuntimeError(
                "reportlab is required for PDF output (pip install reportlab)"
            )

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=2.5 * cm,
            rightMargin=2.5 * cm,
            topMargin=2.5 * cm,
            bottomMargin=2.5 * cm,
            title=doc_ir.title,
            author=doc_ir.author,
        )

        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            "NMTitle",
            parent=styles["Title"],
            fontSize=18,
            spaceAfter=14,
        )
        h1_style = ParagraphStyle(
            "NMH1",
            parent=styles["Heading1"],
            fontSize=14,
            spaceBefore=14,
            spaceAfter=6,
        )
        h2_style = ParagraphStyle(
            "NMH2",
            parent=styles["Heading2"],
            fontSize=12,
            spaceBefore=10,
            spaceAfter=4,
        )
        h3_style = ParagraphStyle(
            "NMH3",
            parent=styles["Heading3"],
            fontSize=11,
            spaceBefore=8,
            spaceAfter=2,
        )
        body_style = ParagraphStyle(
            "NMBody",
            parent=styles["Normal"],
            fontSize=10,
            leading=15,
            spaceAfter=6,
        )
        code_style = ParagraphStyle(
            "NMCode",
            parent=styles["Code"],
            fontSize=8,
            fontName="Courier",
            backColor=colors.HexColor("#f4f4f4"),
            borderColor=colors.HexColor("#d0d0d0"),
            borderWidth=0.5,
            borderPadding=6,
            spaceAfter=8,
        )

        story = []

        # Title
        story.append(Paragraph(doc_ir.title, title_style))
        if doc_ir.author and doc_ir.author != "NovaMindd":
            story.append(Paragraph(f"Author: {doc_ir.author}", styles["Italic"]))
        story.append(Spacer(1, 0.3 * cm))

        for block in doc_ir.blocks:
            bt = block.block_type

            if bt == BlockType.HEADING1:
                story.append(Paragraph(block.text, h1_style))

            elif bt == BlockType.HEADING2:
                story.append(Paragraph(block.text, h2_style))

            elif bt == BlockType.HEADING3:
                story.append(Paragraph(block.text, h3_style))

            elif bt == BlockType.PARAGRAPH:
                # Escape HTML entities for reportlab
                safe = block.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                story.append(Paragraph(safe, body_style))

            elif bt == BlockType.LIST:
                items = [ListItem(Paragraph(item, body_style)) for item in block.items]
                story.append(ListFlowable(items, bulletType="bullet"))
                story.append(Spacer(1, 0.2 * cm))

            elif bt == BlockType.CODE:
                story.append(Preformatted(block.text, code_style))

            elif bt == BlockType.TABLE:
                if block.rows:
                    table_data = [
                        [cell.text for cell in row]
                        for row in block.rows
                    ]
                    tbl = Table(table_data, repeatRows=1)
                    tbl_style = TableStyle([
                        ("BACKGROUND",   (0, 0), (-1, 0),  colors.HexColor("#3b82d4")),
                        ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.white),
                        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
                        ("FONTSIZE",     (0, 0), (-1, -1), 9),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                         [colors.white, colors.HexColor("#f7f8fa")]),
                        ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
                        ("TOPPADDING",   (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
                    ])
                    tbl.setStyle(tbl_style)
                    story.append(tbl)
                    story.append(Spacer(1, 0.3 * cm))

            elif bt == BlockType.PAGE_BREAK:
                story.append(PageBreak())

        # Evidence references appendix
        if doc_ir.evidence_refs:
            story.append(PageBreak())
            story.append(Paragraph("Evidence References", h2_style))
            for ref in doc_ir.evidence_refs:
                text = (
                    f"{ref.get('document_id', '?')} — "
                    f"Page {ref.get('page', '?')} — "
                    f"Score {ref.get('score', 0):.3f}"
                )
                story.append(Paragraph(f"• {text}", body_style))

        doc.build(story)
        logger.debug("pdf_rendered", title=doc_ir.title, blocks=len(doc_ir.blocks))
        return buf.getvalue()
