"""
PRAMAAN v1  --  Assurance Report PDF Generator.

Produces a production-quality, multi-page offline PDF Assurance Report using
ReportLab. Employs a clean technical palette, two-pass numbered canvas,
defensive text sanitization, and strict separation of risk, confidence,
coverage, findings, evidence, limitations, and recommendations.
"""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.reporting.formatting import (
    COLOR_BG_ALT,
    COLOR_BG_LIGHT,
    COLOR_BORDER,
    COLOR_BORDER_LIGHT,
    COLOR_DANGER,
    COLOR_INFO,
    COLOR_NEUTRAL,
    COLOR_PASS,
    COLOR_PRIMARY,
    COLOR_SECONDARY,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    COLOR_WARN,
    get_risk_color,
    get_severity_color,
    get_status_color,
    safe_escape,
)
from backend.reporting.models import AssuranceReportData


# ---------------------------------------------------------------------------
# Two-Pass Numbered Canvas (Page X of Y, Running Header & Footer)
# ---------------------------------------------------------------------------

class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas that accumulates page states and renders running
    headers, footers, and dynamic 'Page X of Y' pagination.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []
        self.assessment_id_short: str = ""

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def _draw_page_decorations(self, page_count: int) -> None:
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(COLOR_TEXT_MUTED)

        # Running Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(54, 752, "PRAMAAN v1  --  Offline Assurance Report")
            if self.assessment_id_short:
                self.drawRightString(612 - 54, 752, f"Assessment ID: {self.assessment_id_short}")
            self.setStrokeColor(COLOR_BORDER_LIGHT)
            self.setLineWidth(0.5)
            self.line(54, 746, 612 - 54, 746)

        # Running Footer (all pages)
        self.setStrokeColor(COLOR_BORDER_LIGHT)
        self.setLineWidth(0.5)
        self.line(54, 46, 612 - 54, 46)

        self.drawString(54, 34, "PRAMAAN v1.0.0  --  Evidence Before Trust  --  Offline Air-Gapped Assurance")
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(612 - 54, 34, page_str)
        self.restoreState()


# ---------------------------------------------------------------------------
# Report Styles Setup
# ---------------------------------------------------------------------------

def _build_report_styles() -> dict[str, ParagraphStyle]:
    """Construct unified, publication-grade typography styles."""
    base = getSampleStyleSheet()

    styles = {
        "DocTitle": ParagraphStyle(
            "DocTitle",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=COLOR_PRIMARY,
        ),
        "DocSubtitle": ParagraphStyle(
            "DocSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            textColor=COLOR_INFO,
        ),
        "SectionHeader": ParagraphStyle(
            "SectionHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=COLOR_PRIMARY,
            spaceBefore=8,
            spaceAfter=6,
        ),
        "SubsectionHeader": ParagraphStyle(
            "SubsectionHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            textColor=COLOR_SECONDARY,
            spaceBefore=6,
            spaceAfter=4,
        ),
        "Body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=COLOR_TEXT_MAIN,
        ),
        "BodyBold": ParagraphStyle(
            "BodyBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=13,
            textColor=COLOR_PRIMARY,
        ),
        "BodyMuted": ParagraphStyle(
            "BodyMuted",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=COLOR_TEXT_MUTED,
        ),
        "TableHead": ParagraphStyle(
            "TableHead",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=COLOR_PRIMARY,
        ),
        "TableCell": ParagraphStyle(
            "TableCell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=COLOR_TEXT_MAIN,
        ),
        "TableCellBold": ParagraphStyle(
            "TableCellBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=COLOR_PRIMARY,
        ),
        "TableCellCode": ParagraphStyle(
            "TableCellCode",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=7.5,
            leading=9.5,
            textColor=COLOR_TEXT_MAIN,
        ),
        "CalloutTitle": ParagraphStyle(
            "CalloutTitle",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=COLOR_PRIMARY,
        ),
        "CalloutText": ParagraphStyle(
            "CalloutText",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=COLOR_TEXT_MAIN,
        ),
    }
    return styles


# ---------------------------------------------------------------------------
# PDF Report Generator
# ---------------------------------------------------------------------------

class PDFReportGenerator:
    """Builds multi-page offline PDF assurance reports."""

    def __init__(self, data: AssuranceReportData) -> None:
        self.data = data
        self.styles = _build_report_styles()
        self.printable_width = 504  # 612 - 2 * 54

    def generate(self) -> bytes:
        """Render report and return raw PDF bytes."""
        buffer = io.BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=54,
            rightMargin=54,
            topMargin=54,
            bottomMargin=54,
        )

        story: list[Any] = []

        # 1. Page 1  --  Executive Summary
        self._build_page1_summary(story)
        story.append(PageBreak())

        # 2. Page 2  --  Detection Battery Results Matrix
        self._build_page2_battery_results(story)
        story.append(PageBreak())

        # 3. Page 3+  --  Detailed Findings & Evidence
        self._build_page3_findings(story)
        story.append(PageBreak())

        # 4. Page 4  --  Coverage & Limitations
        self._build_page4_coverage_limitations(story)
        story.append(PageBreak())

        # 5. Page 5  --  Provenance & Output Binding
        self._build_page5_provenance(story)
        story.append(PageBreak())

        # 6. Page 6  --  Tamper-Evident Audit Verification
        self._build_page6_audit(story)
        story.append(PageBreak())

        # 7. Page 7  --  Recommended Disposition & Metadata
        self._build_page7_recommendation_and_meta(story)

        def canvas_maker(*args: Any, **kwargs: Any) -> NumberedCanvas:
            c = NumberedCanvas(*args, **kwargs)
            c.assessment_id_short = self.data.meta.assessment_id[:8]
            return c

        doc.build(story, canvasmaker=canvas_maker)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

    # -----------------------------------------------------------------------
    # Section Builders
    # -----------------------------------------------------------------------

    def _build_page1_summary(self, story: list[Any]) -> None:
        meta = self.data.meta

        # Header Title
        story.append(Paragraph("PRAMAAN", self.styles["DocTitle"]))
        story.append(
            Paragraph(
                "Offline Computer Vision Integrity Assurance Report",
                self.styles["DocSubtitle"],
            )
        )
        story.append(Spacer(1, 6))
        story.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_PRIMARY, spaceBefore=2, spaceAfter=10))

        # Overall Status / KPI Badges Grid
        risk_color = get_risk_color(meta.overall_risk)
        status_color = get_status_color(meta.status)
        coverage_pct = f"{round(meta.coverage_fraction * 100, 1)}%"

        kpi_data = [
            [
                Paragraph("<b>OVERALL RISK</b>", self.styles["TableHead"]),
                Paragraph("<b>CONFIDENCE</b>", self.styles["TableHead"]),
                Paragraph("<b>COVERAGE</b>", self.styles["TableHead"]),
                Paragraph("<b>STATUS</b>", self.styles["TableHead"]),
            ],
            [
                Paragraph(f"<font color='{risk_color.hexval()}'><b>{safe_escape(meta.overall_risk)}</b></font>", self.styles["SectionHeader"]),
                Paragraph(f"<b>{safe_escape(meta.overall_confidence)}</b>", self.styles["SectionHeader"]),
                Paragraph(f"<b>{coverage_pct}</b>", self.styles["SectionHeader"]),
                Paragraph(f"<font color='{status_color.hexval()}'><b>{safe_escape(meta.status.upper())}</b></font>", self.styles["SectionHeader"]),
            ],
        ]
        kpi_table = Table(kpi_data, colWidths=[126, 126, 126, 126])
        kpi_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG_LIGHT),
                ("BOX", (0, 0), (-1, -1), 1, COLOR_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER_LIGHT),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ])
        )
        story.append(kpi_table)
        story.append(Spacer(1, 14))

        # Assessment Metadata Block
        story.append(Paragraph("Assessment Metadata", self.styles["SubsectionHeader"]))
        meta_rows = [
            [
                Paragraph("<b>Assessment Title:</b>", self.styles["TableCellBold"]),
                Paragraph(safe_escape(meta.title), self.styles["TableCell"]),
                Paragraph("<b>Assessment ID:</b>", self.styles["TableCellBold"]),
                Paragraph(safe_escape(meta.assessment_id), self.styles["TableCellCode"]),
            ],
            [
                Paragraph("<b>Created At (UTC):</b>", self.styles["TableCellBold"]),
                Paragraph(safe_escape(meta.created_at[:19].replace("T", " ")), self.styles["TableCell"]),
                Paragraph("<b>Completed At:</b>", self.styles["TableCellBold"]),
                Paragraph(safe_escape((meta.completed_at or "In Progress")[:19].replace("T", " ")), self.styles["TableCell"]),
            ],
            [
                Paragraph("<b>PRAMAAN Version:</b>", self.styles["TableCellBold"]),
                Paragraph(safe_escape(meta.software_version), self.styles["TableCell"]),
                Paragraph("<b>Execution Mode:</b>", self.styles["TableCellBold"]),
                Paragraph("Strictly Offline / Air-Gapped", self.styles["TableCell"]),
            ],
        ]
        meta_table = Table(meta_rows, colWidths=[100, 152, 100, 152])
        meta_table.setStyle(
            TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER_LIGHT),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER_LIGHT),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(meta_table)
        story.append(Spacer(1, 14))

        # Evaluated Assets Inventory
        story.append(Paragraph("Evaluated Assets Inventory", self.styles["SubsectionHeader"]))
        asset_rows = [
            [
                Paragraph("<b>Asset ID</b>", self.styles["TableHead"]),
                Paragraph("<b>Type</b>", self.styles["TableHead"]),
                Paragraph("<b>Name / Identifier</b>", self.styles["TableHead"]),
                Paragraph("<b>SHA-256 Digest</b>", self.styles["TableHead"]),
                Paragraph("<b>Format / Size</b>", self.styles["TableHead"]),
            ]
        ]
        if not self.data.assets:
            asset_rows.append([
                Paragraph("None registered", self.styles["TableCell"]),
                Paragraph("-", self.styles["TableCell"]),
                Paragraph("-", self.styles["TableCell"]),
                Paragraph("-", self.styles["TableCell"]),
                Paragraph("-", self.styles["TableCell"]),
            ])
        else:
            for a in self.data.assets:
                size_str = f"{a.size_bytes / 1024:.1f} KB" if a.size_bytes > 0 else "N/A"
                access_str = f" [{a.details['access_level'].upper()}]" if (a.details and "access_level" in a.details) else ""
                fmt_str = f"{a.format or a.asset_type.upper()}{access_str} ({size_str})"
                sha_trunc = f"{a.sha256[:16]}...{a.sha256[-8:]}" if len(a.sha256) > 24 else a.sha256
                asset_rows.append([
                    Paragraph(safe_escape(a.asset_id[:8]), self.styles["TableCellCode"]),
                    Paragraph(safe_escape(a.asset_type), self.styles["TableCell"]),
                    Paragraph(safe_escape(a.name), self.styles["TableCell"]),
                    Paragraph(safe_escape(sha_trunc), self.styles["TableCellCode"]),
                    Paragraph(safe_escape(fmt_str), self.styles["TableCell"]),
                ])

        asset_table = Table(asset_rows, colWidths=[65, 80, 120, 139, 100])
        asset_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_BG_ALT),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER_LIGHT),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(asset_table)
        story.append(Spacer(1, 14))

        # Executive Finding Synopsis
        story.append(Paragraph("Executive Assurance Summary", self.styles["SubsectionHeader"]))
        f_count = len(self.data.findings)
        ev_count = sum(len(f.evidence) for f in self.data.findings)
        high_count = sum(1 for f in self.data.findings if f.severity.upper() in ("HIGH", "CRITICAL"))
        med_count = sum(1 for f in self.data.findings if f.severity.upper() == "MEDIUM")
        info_count = sum(1 for f in self.data.findings if f.severity.upper() in ("INFO", "LOW"))

        synopsis_text = (
            f"PRAMAAN completed integrity evaluation with <b>{f_count}</b> total findings "
            f"and <b>{ev_count}</b> cryptographic evidence items across all evaluated batteries. "
            f"Findings breakdown: <b>{high_count}</b> High/Critical severity, "
            f"<b>{med_count}</b> Medium severity, and <b>{info_count}</b> Low/Informational observations. "
            f"Assurance status: <b>{safe_escape(self.data.recommended_disposition)}</b>."
        )
        synopsis_card = Table(
            [[Paragraph(synopsis_text, self.styles["CalloutText"])]],
            colWidths=[self.printable_width],
        )
        synopsis_card.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG_LIGHT),
                ("BOX", (0, 0), (-1, -1), 1, COLOR_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ])
        )
        story.append(synopsis_card)

    def _build_page2_battery_results(self, story: list[Any]) -> None:
        story.append(Paragraph("2. Assurance Results  --  Detection Battery Matrix", self.styles["SectionHeader"]))
        story.append(
            Paragraph(
                "Evaluation of all 11 standardized PRAMAAN integrity detectors across Data Integrity (DI), "
                "Model Integrity (MI), and Inference Provenance (PI). Detectors marked NOT_APPLICABLE indicate "
                "that the corresponding asset was not supplied, which is distinct from a detection failure.",
                self.styles["Body"],
            )
        )
        story.append(Spacer(1, 10))

        rows = [
            [
                Paragraph("<b>Detector Name</b>", self.styles["TableHead"]),
                Paragraph("<b>Category</b>", self.styles["TableHead"]),
                Paragraph("<b>Status</b>", self.styles["TableHead"]),
                Paragraph("<b>Risk</b>", self.styles["TableHead"]),
                Paragraph("<b>Confidence</b>", self.styles["TableHead"]),
                Paragraph("<b>Findings</b>", self.styles["TableHead"]),
                Paragraph("<b>Evidence</b>", self.styles["TableHead"]),
            ]
        ]

        for d in self.data.detectors:
            st_col = get_status_color(d.status)
            rk_col = get_risk_color(d.risk_level)
            st_text = f"<font color='{st_col.hexval()}'><b>{safe_escape(d.status)}</b></font>"
            rk_text = f"<font color='{rk_col.hexval()}'><b>{safe_escape(d.risk_level)}</b></font>" if d.status != "NOT_APPLICABLE" else "-"
            conf_text = safe_escape(d.confidence_level) if d.status != "NOT_APPLICABLE" else "-"

            rows.append([
                Paragraph(safe_escape(d.detector_name), self.styles["TableCellBold"]),
                Paragraph(safe_escape(d.category.replace("_", " ")), self.styles["TableCell"]),
                Paragraph(st_text, self.styles["TableCell"]),
                Paragraph(rk_text, self.styles["TableCell"]),
                Paragraph(conf_text, self.styles["TableCell"]),
                Paragraph(str(d.findings_count), self.styles["TableCell"]),
                Paragraph(str(d.evidence_count), self.styles["TableCell"]),
            ])

        table = Table(rows, colWidths=[150, 95, 75, 54, 55, 38, 37])
        table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_BG_ALT),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER_LIGHT),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ALIGN", (5, 0), (-1, -1), "CENTER"),
            ])
        )
        story.append(table)

    def _build_page3_findings(self, story: list[Any]) -> None:
        story.append(Paragraph("3. Detailed Findings & Evidence Records", self.styles["SectionHeader"]))
        story.append(
            Paragraph(
                "Every meaningful observation is backed by cryptographic or statistical measurements. "
                "PRAMAAN never reports speculative accusations; all findings represent verified discrepancies.",
                self.styles["Body"],
            )
        )
        story.append(Spacer(1, 8))

        if not self.data.findings:
            clean_box = Table(
                [[
                    Paragraph(
                        "<b>No Integrity Anomalies Recorded:</b> All active detectors completed without "
                        "triggering anomalous findings or cryptographic mismatches.",
                        self.styles["CalloutText"],
                    )
                ]],
                colWidths=[self.printable_width],
            )
            clean_box.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG_LIGHT),
                    ("BOX", (0, 0), (-1, -1), 1, COLOR_PASS),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ])
            )
            story.append(clean_box)
            return

        for idx, f in enumerate(self.data.findings, 1):
            sev_col = get_severity_color(f.severity)

            # Finding card elements
            card_items = []
            header_text = (
                f"<b>#{idx}. {safe_escape(f.title)}</b> "
                f"[<font color='{sev_col.hexval()}'><b>{safe_escape(f.severity.upper())}</b></font>]"
            )
            card_items.append(Paragraph(header_text, self.styles["CalloutTitle"]))
            card_items.append(Spacer(1, 3))

            meta_line = (
                f"<b>ID:</b> {safe_escape(f.finding_id[:8])} | "
                f"<b>Detector:</b> {safe_escape(f.detector_id)} | "
                f"<b>Subcategory:</b> {safe_escape(f.subcategory)}"
            )
            card_items.append(Paragraph(meta_line, self.styles["BodyMuted"]))
            card_items.append(Spacer(1, 4))

            card_items.append(Paragraph(f"<b>Description:</b> {safe_escape(f.description)}", self.styles["Body"]))

            # Evidence breakdown
            if f.evidence:
                card_items.append(Spacer(1, 4))
                card_items.append(Paragraph("<b>Cryptographic / Empirical Evidence:</b>", self.styles["TableCellBold"]))
                for ev in f.evidence:
                    ev_desc = f"&bull; [{safe_escape(ev.evidence_type)}] {safe_escape(ev.description)}"
                    card_items.append(Paragraph(ev_desc, self.styles["TableCell"]))
                    if ev.data:
                        # Render compact key-value measurements
                        clean_data = {
                            k: (v[:48] + "..." if isinstance(v, str) and len(v) > 50 else v)
                            for k, v in ev.data.items()
                            if k not in ("detector_version",)
                        }
                        data_str = ", ".join(f"<i>{k}:</i> {v}" for k, v in clean_data.items())
                        card_items.append(Paragraph(f"&nbsp;&nbsp;Data: {safe_escape(data_str)}", self.styles["TableCellCode"]))

            if f.recommended_disposition:
                card_items.append(Spacer(1, 4))
                card_items.append(
                    Paragraph(
                        f"<b>Recommended Disposition:</b> {safe_escape(f.recommended_disposition)}",
                        self.styles["BodyBold"],
                    )
                )

            card_table = Table([[card_items]], colWidths=[self.printable_width])
            card_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG_LIGHT),
                    ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ])
            )
            story.append(KeepTogether([card_table, Spacer(1, 6)]))

    def _build_page4_coverage_limitations(self, story: list[Any]) -> None:
        story.append(Paragraph("4. Evaluated Scope, Coverage Gaps & Limitations", self.styles["SectionHeader"]))
        story.append(
            Paragraph(
                "PRAMAAN explicitly reports unexercised detection capabilities as Coverage Gaps rather than "
                "assuming clean passage. Incomplete coverage honestly reduces evaluation confidence per ADR-003.",
                self.styles["Body"],
            )
        )
        story.append(Spacer(1, 8))

        # Coverage Gaps Table
        story.append(Paragraph("Recorded Coverage Gaps", self.styles["SubsectionHeader"]))
        gap_rows = [
            [
                Paragraph("<b>Detector</b>", self.styles["TableHead"]),
                Paragraph("<b>Reason Code</b>", self.styles["TableHead"]),
                Paragraph("<b>Impact</b>", self.styles["TableHead"]),
                Paragraph("<b>Recommended Action</b>", self.styles["TableHead"]),
            ]
        ]
        if not self.data.coverage_gaps:
            gap_rows.append([
                Paragraph("None  --  Full capability coverage", self.styles["TableCell"]),
                Paragraph("N/A", self.styles["TableCell"]),
                Paragraph("Full verification exercised", self.styles["TableCell"]),
                Paragraph("No remediation necessary", self.styles["TableCell"]),
            ])
        else:
            for g in self.data.coverage_gaps:
                gap_rows.append([
                    Paragraph(safe_escape(g.detector_name), self.styles["TableCellBold"]),
                    Paragraph(safe_escape(g.reason), self.styles["TableCell"]),
                    Paragraph(safe_escape(g.impact), self.styles["TableCell"]),
                    Paragraph(safe_escape(g.recommended_action), self.styles["TableCell"]),
                ])

        gap_table = Table(gap_rows, colWidths=[120, 110, 134, 140])
        gap_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_BG_ALT),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER_LIGHT),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(gap_table)
        story.append(Spacer(1, 14))

        # Documented Limitations Section
        story.append(Paragraph("Methodological Boundaries & Known Limitations", self.styles["SubsectionHeader"]))
        standard_limitations = [
            "Invisible / blended spatial backdoor perturbations cannot be universally detected without reference triggers.",
            "Distributional OOD detection operates statistically and does not claim semantic classification without pretrained embeddings.",
            "PyTorch state dictionaries without executable graph topologies cannot support activation or trigger convergence batteries.",
            "Cryptographic replay detection alone cannot prove duplicate inference when an actor issues a fresh nonce and sequence.",
        ]
        all_limitations = list(dict.fromkeys(self.data.limitations + standard_limitations))

        for lim in all_limitations:
            story.append(Paragraph(f"&bull; {safe_escape(lim)}", self.styles["TableCell"]))
            story.append(Spacer(1, 2))

    def _build_page5_provenance(self, story: list[Any]) -> None:
        story.append(Paragraph("5. Inference Provenance & Output Binding", self.styles["SectionHeader"]))
        story.append(
            Paragraph(
                "Cryptographic binding of inference execution events. A signed ProvenanceManifest binds "
                "the input image, model identity, preprocessing configuration, inference parameters, and "
                "output predictions using SHA-256 digests and Ed25519 digital signatures.",
                self.styles["Body"],
            )
        )
        story.append(Spacer(1, 10))

        prov = self.data.provenance
        if prov is None:
            no_prov = Table(
                [[
                    Paragraph(
                        "<b>Provenance Manifest: NOT PROVIDED</b><br/>"
                        "This assessment evaluated standalone dataset or model artifacts without an associated "
                        "inference execution bundle. Provenance verification (PI-01) was marked NOT_APPLICABLE.",
                        self.styles["CalloutText"],
                    )
                ]],
                colWidths=[self.printable_width],
            )
            no_prov.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG_LIGHT),
                    ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ])
            )
            story.append(no_prov)
            return

        # Provenance Present
        sig_col = COLOR_PASS if prov.signature_status == "VERIFIED" else COLOR_DANGER
        rep_col = COLOR_PASS if prov.replay_status == "CLEAN" else COLOR_WARN

        prov_rows = [
            [
                Paragraph("<b>Manifest ID:</b>", self.styles["TableCellBold"]),
                Paragraph(safe_escape(prov.manifest_id), self.styles["TableCellCode"]),
                Paragraph("<b>Signature Status:</b>", self.styles["TableCellBold"]),
                Paragraph(f"<font color='{sig_col.hexval()}'><b>{safe_escape(prov.signature_status)}</b></font>", self.styles["TableCellBold"]),
            ],
            [
                Paragraph("<b>Stream Sequence:</b>", self.styles["TableCellBold"]),
                Paragraph(str(prov.sequence), self.styles["TableCell"]),
                Paragraph("<b>Replay Status:</b>", self.styles["TableCellBold"]),
                Paragraph(f"<font color='{rep_col.hexval()}'><b>{safe_escape(prov.replay_status)}</b></font>", self.styles["TableCellBold"]),
            ],
            [
                Paragraph("<b>Timestamp (UTC):</b>", self.styles["TableCellBold"]),
                Paragraph(safe_escape(prov.timestamp_utc), self.styles["TableCell"]),
                Paragraph("<b>Nonce:</b>", self.styles["TableCellBold"]),
                Paragraph(safe_escape(f"{prov.nonce[:16]}..."), self.styles["TableCellCode"]),
            ],
            [
                Paragraph("<b>Input SHA-256:</b>", self.styles["TableCellBold"]),
                Paragraph(safe_escape(f"{prov.input_sha256[:24]}..."), self.styles["TableCellCode"]),
                Paragraph("<b>Model SHA-256:</b>", self.styles["TableCellBold"]),
                Paragraph(safe_escape(f"{prov.model_sha256[:24]}..."), self.styles["TableCellCode"]),
            ],
            [
                Paragraph("<b>Output SHA-256:</b>", self.styles["TableCellBold"]),
                Paragraph(safe_escape(f"{prov.output_sha256[:24]}..."), self.styles["TableCellCode"]),
                Paragraph("<b>Canonical Digest:</b>", self.styles["TableCellBold"]),
                Paragraph(safe_escape(f"{(prov.digest or 'N/A')[:24]}..."), self.styles["TableCellCode"]),
            ],
        ]
        prov_table = Table(prov_rows, colWidths=[110, 142, 110, 142])
        prov_table.setStyle(
            TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER_LIGHT),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ])
        )
        story.append(prov_table)

        if prov.anomalies:
            story.append(Spacer(1, 10))
            story.append(Paragraph("<b>Recorded Replay Anomalies:</b>", self.styles["SubsectionHeader"]))
            for anom in prov.anomalies:
                story.append(Paragraph(f"&bull; <font color='{COLOR_WARN.hexval()}'><b>{safe_escape(anom)}</b></font>", self.styles["TableCell"]))

    def _build_page6_audit(self, story: list[Any]) -> None:
        story.append(Paragraph("6. Tamper-Evident Audit Verification", self.styles["SectionHeader"]))
        story.append(
            Paragraph(
                "Assessment execution events are committed to a hash-linked, append-only SQLite WAL audit log. "
                "Each audit event is linked to the prior event's SHA-256 hash, forming an immutable sequence. "
                "Critical lifecycle events are digitally signed with Ed25519 (ADR-005).",
                self.styles["Body"],
            )
        )
        story.append(Spacer(1, 10))

        audit = self.data.audit
        if audit is None:
            story.append(Paragraph("No audit log available for this record.", self.styles["Body"]))
            return

        chain_col = COLOR_PASS if audit.chain_valid else COLOR_DANGER
        chain_text = "CRYPTOGRAPHICALLY VALID" if audit.chain_valid else "VERIFICATION FAILED"

        summary_rows = [
            [
                Paragraph("<b>Audit Chain Status:</b>", self.styles["TableCellBold"]),
                Paragraph(f"<font color='{chain_col.hexval()}'><b>{chain_text}</b></font>", self.styles["TableCellBold"]),
                Paragraph("<b>Events Checked:</b>", self.styles["TableCellBold"]),
                Paragraph(str(audit.events_checked), self.styles["TableCell"]),
            ],
            [
                Paragraph("<b>First Event Hash:</b>", self.styles["TableCellBold"]),
                Paragraph(safe_escape((audit.first_event_hash or "N/A")[:24] + "..."), self.styles["TableCellCode"]),
                Paragraph("<b>Chain Head Hash:</b>", self.styles["TableCellBold"]),
                Paragraph(safe_escape((audit.last_event_hash or "N/A")[:24] + "..."), self.styles["TableCellCode"]),
            ],
        ]
        summary_table = Table(summary_rows, colWidths=[110, 142, 110, 142])
        summary_table.setStyle(
            TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER_LIGHT),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ])
        )
        story.append(summary_table)
        story.append(Spacer(1, 12))

        # Events Timeline
        story.append(Paragraph("Event Sequence Timeline", self.styles["SubsectionHeader"]))
        event_rows = [
            [
                Paragraph("<b>Event Type</b>", self.styles["TableHead"]),
                Paragraph("<b>Actor</b>", self.styles["TableHead"]),
                Paragraph("<b>Timestamp (UTC)</b>", self.styles["TableHead"]),
                Paragraph("<b>Current Hash</b>", self.styles["TableHead"]),
            ]
        ]
        for ev in audit.events[:12]:  # Display first 12 events
            event_rows.append([
                Paragraph(safe_escape(ev.get("event_type", "")), self.styles["TableCellBold"]),
                Paragraph(safe_escape(ev.get("actor", "")), self.styles["TableCell"]),
                Paragraph(safe_escape(ev.get("timestamp_utc", "")[:19].replace("T", " ")), self.styles["TableCell"]),
                Paragraph(safe_escape(f"{ev.get('current_hash', '')[:20]}..."), self.styles["TableCellCode"]),
            ])

        event_table = Table(event_rows, colWidths=[120, 80, 130, 174])
        event_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_BG_ALT),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER_LIGHT),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(event_table)

    def _build_page7_recommendation_and_meta(self, story: list[Any]) -> None:
        story.append(Paragraph("7. Recommended Disposition & Operational Guidance", self.styles["SectionHeader"]))
        story.append(Spacer(1, 6))

        # Disposition Callout
        disp_col = COLOR_PASS if "ACCEPT" in self.data.recommended_disposition else (
            COLOR_WARN if "INVESTIGATE" in self.data.recommended_disposition or "PROVISIONAL" in self.data.recommended_disposition else COLOR_DANGER
        )
        rec_card = Table(
            [[
                Paragraph(
                    f"<b>RECOMMENDED DISPOSITION:</b> <font color='{disp_col.hexval()}'><b>{safe_escape(self.data.recommended_disposition)}</b></font><br/><br/>"
                    f"<b>Rationale:</b> {safe_escape(self.data.disposition_rationale)}",
                    self.styles["CalloutText"],
                )
            ]],
            colWidths=[self.printable_width],
        )
        rec_card.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG_LIGHT),
                ("BOX", (0, 0), (-1, -1), 1.5, disp_col),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ])
        )
        story.append(rec_card)
        story.append(Spacer(1, 10))

        disclaimer = (
            "<b>Advisory Assurance Notice:</b> This recommendation reflects an objective evaluation of evidence, "
            "statistical anomaly thresholds, and cryptographic bindings gathered during this specific offline assessment. "
            "It does not constitute an automated deployment block or an authoritative certification beyond the tested scope."
        )
        story.append(Paragraph(disclaimer, self.styles["BodyMuted"]))
        story.append(Spacer(1, 16))

        # Technical Metadata Block
        story.append(Paragraph("Technical & Cryptographic Specification", self.styles["SubsectionHeader"]))
        meta_rows = [
            [
                Paragraph("<b>PRAMAAN Core Version:</b>", self.styles["TableCellBold"]),
                Paragraph(safe_escape(self.data.meta.software_version), self.styles["TableCell"]),
                Paragraph("<b>Report Schema:</b>", self.styles["TableCellBold"]),
                Paragraph(safe_escape(self.data.report_schema_version), self.styles["TableCell"]),
            ],
            [
                Paragraph("<b>Report Generation Time:</b>", self.styles["TableCellBold"]),
                Paragraph(safe_escape(self.data.generated_at_utc), self.styles["TableCell"]),
                Paragraph("<b>Hash Algorithm:</b>", self.styles["TableCellBold"]),
                Paragraph("SHA-256 (FIPS 180-4)", self.styles["TableCell"]),
            ],
            [
                Paragraph("<b>Signature Scheme:</b>", self.styles["TableCellBold"]),
                Paragraph("Ed25519 (RFC 8032)", self.styles["TableCell"]),
                Paragraph("<b>Perceptual Hashes:</b>", self.styles["TableCellBold"]),
                Paragraph("pHash (DCT) / dHash (Gradient)", self.styles["TableCell"]),
            ],
            [
                Paragraph("<b>Offline Guarantee:</b>", self.styles["TableCellBold"]),
                Paragraph("Strictly Local In-Process Generation", self.styles["TableCell"]),
                Paragraph("<b>Confidentiality:</b>", self.styles["TableCellBold"]),
                Paragraph("No Outbound Network Sockets", self.styles["TableCell"]),
            ],
        ]
        meta_table = Table(meta_rows, colWidths=[120, 132, 120, 132])
        meta_table.setStyle(
            TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER_LIGHT),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER_LIGHT),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(meta_table)


# ---------------------------------------------------------------------------
# High-Level Helper
# ---------------------------------------------------------------------------

def generate_assessment_report_pdf(data: AssuranceReportData) -> bytes:
    """Generate and return PDF bytes from AssuranceReportData."""
    generator = PDFReportGenerator(data)
    return generator.generate()
