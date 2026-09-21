"""PDF rendering for Heimdall Risk Reports.

Pure: takes a plain-data `ReportData` and returns PDF bytes. It performs no
queries, so the layout can be tested without a database.

ReportLab is used deliberately — it is pure Python with no system libraries to
install, which keeps the serverless function bundle small and the build
reproducible. A browser-based renderer would need a headless Chromium.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.common.disclaimer import DISCLAIMER, EARLY_WARNING_DISCLAIMER

# Brand tokens, matching docs/README and the frontend design tokens.
MIDNIGHT = colors.HexColor("#111827")
GLACIER_BLUE = colors.HexColor("#38BDF8")
BRAND_GOLD = colors.HexColor("#D6A84B")
EMERALD = colors.HexColor("#10B981")
MUTED_RED = colors.HexColor("#DC5A5A")
MUTED_TEXT = colors.HexColor("#64748B")
BORDER = colors.HexColor("#E2E8F0")
FROST = colors.HexColor("#F8FAFC")


@dataclass(slots=True)
class MetricRow:
    """One metric as it appears in the report."""

    label: str
    value: str
    unit: str = ""
    note: str = ""


@dataclass(slots=True)
class TableBlock:
    """A titled table."""

    title: str
    columns: list[str]
    rows: list[list[str]]
    # Column index whose sign should be coloured, if any.
    signed_column: int | None = None
    empty_note: str = "No data available."


@dataclass(slots=True)
class ReportData:
    """Everything the renderer needs. Assembled by the service."""

    portfolio_name: str
    base_currency: str
    generated_at: datetime
    data_as_of: date | None
    analysis_period: str

    summary: list[MetricRow] = field(default_factory=list)
    performance: list[MetricRow] = field(default_factory=list)
    risk: list[MetricRow] = field(default_factory=list)
    holdings: TableBlock | None = None
    allocation: TableBlock | None = None
    risk_contribution: TableBlock | None = None
    stress_tests: list[TableBlock] = field(default_factory=list)
    signals: TableBlock | None = None

    assumptions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    data_sources: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)


def _styles() -> dict[str, ParagraphStyle]:
    """Paragraph styles used throughout the report."""
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "HeimdallTitle",
            parent=base["Title"],
            fontSize=22,
            leading=26,
            textColor=MIDNIGHT,
            alignment=TA_LEFT,
            spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "HeimdallSubtitle",
            parent=base["Normal"],
            fontSize=10.5,
            leading=14,
            textColor=MUTED_TEXT,
            spaceAfter=10,
        ),
        "heading": ParagraphStyle(
            "HeimdallHeading",
            parent=base["Heading2"],
            fontSize=13,
            leading=16,
            textColor=MIDNIGHT,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "subheading": ParagraphStyle(
            "HeimdallSubheading",
            parent=base["Heading3"],
            fontSize=11,
            leading=14,
            textColor=MIDNIGHT,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "HeimdallBody",
            parent=base["Normal"],
            fontSize=9.5,
            leading=13,
            textColor=MIDNIGHT,
        ),
        "muted": ParagraphStyle(
            "HeimdallMuted",
            parent=base["Normal"],
            fontSize=8.5,
            leading=12,
            textColor=MUTED_TEXT,
        ),
        "disclaimer": ParagraphStyle(
            "HeimdallDisclaimer",
            parent=base["Normal"],
            fontSize=8.5,
            leading=12,
            textColor=MUTED_TEXT,
            borderPadding=6,
            backColor=FROST,
        ),
        "cell": ParagraphStyle(
            "HeimdallCell",
            parent=base["Normal"],
            fontSize=8.5,
            leading=11,
            textColor=MIDNIGHT,
        ),
    }


def _metric_table(rows: list[MetricRow], styles: dict[str, ParagraphStyle]) -> Table:
    """Render metric rows as a two-column table with units and notes."""
    data: list[list[Any]] = [["Metric", "Value", "Unit"]]
    for row in rows:
        label = row.label
        if row.note:
            label = f"{label}<br/><font size=7 color='#64748B'>{row.note}</font>"
        data.append(
            [
                Paragraph(label, styles["cell"]),
                Paragraph(f"<b>{row.value}</b>", styles["cell"]),
                Paragraph(row.unit, styles["cell"]),
            ]
        )

    table = Table(data, colWidths=[95 * mm, 45 * mm, 30 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), MIDNIGHT),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, FROST]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _block_table(block: TableBlock, styles: dict[str, ParagraphStyle]) -> list[Any]:
    """Render a titled table, or a note when it has no rows."""
    flowables: list[Any] = [Paragraph(block.title, styles["subheading"])]

    if not block.rows:
        flowables.append(Paragraph(block.empty_note, styles["muted"]))
        return flowables

    data: list[list[Any]] = [
        [Paragraph(f"<b>{column}</b>", styles["cell"]) for column in block.columns]
    ]
    for row in block.rows:
        data.append([Paragraph(str(cell), styles["cell"]) for cell in row])

    width = 170 * mm
    first = width * 0.28
    rest = (width - first) / max(len(block.columns) - 1, 1)
    table = Table(data, colWidths=[first, *[rest] * (len(block.columns) - 1)], repeatRows=1)

    style = [
        ("BACKGROUND", (0, 0), (-1, 0), FROST),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, MIDNIGHT),
    ]

    # Colour signed values, and always keep the sign in the text as well, so the
    # meaning never depends on colour alone.
    if block.signed_column is not None:
        for index, row in enumerate(block.rows, start=1):
            raw = str(row[block.signed_column])
            if raw.startswith("-"):
                style.append(
                    (
                        "TEXTCOLOR",
                        (block.signed_column, index),
                        (block.signed_column, index),
                        MUTED_RED,
                    )
                )
            elif raw.startswith("+"):
                style.append(
                    (
                        "TEXTCOLOR",
                        (block.signed_column, index),
                        (block.signed_column, index),
                        EMERALD,
                    )
                )

    table.setStyle(TableStyle(style))
    flowables.append(table)
    return flowables


def _bullets(items: list[str], styles: dict[str, ParagraphStyle]) -> list[Any]:
    """Render a bullet list."""
    return [Paragraph(f"&bull;&nbsp;{item}", styles["muted"]) for item in items]


def _page_furniture(canvas: Any, document: Any) -> None:
    """Draw the header rule and the footer on every page."""
    canvas.saveState()

    canvas.setStrokeColor(GLACIER_BLUE)
    canvas.setLineWidth(2)
    canvas.line(
        document.leftMargin,
        A4[1] - 14 * mm,
        A4[0] - document.rightMargin,
        A4[1] - 14 * mm,
    )

    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(MIDNIGHT)
    canvas.drawString(document.leftMargin, A4[1] - 12 * mm, "HEIMDALL")
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED_TEXT)
    canvas.drawRightString(
        A4[0] - document.rightMargin,
        A4[1] - 12 * mm,
        "Portfolio Risk Intelligence",
    )

    canvas.setFont("Helvetica", 7)
    canvas.drawString(
        document.leftMargin,
        10 * mm,
        "Educational portfolio analysis. Not financial advice.",
    )
    canvas.drawRightString(A4[0] - document.rightMargin, 10 * mm, f"Page {canvas.getPageNumber()}")

    canvas.restoreState()


def render_report(data: ReportData) -> bytes:
    """Render a Heimdall Risk Report as PDF bytes."""
    styles = _styles()
    buffer = io.BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=22 * mm,
        bottomMargin=18 * mm,
        title=f"Heimdall Risk Report — {data.portfolio_name}",
        author="Heimdall",
        subject="Portfolio risk analysis",
    )

    story: list[Any] = [
        Paragraph("Heimdall Risk Report", styles["title"]),
        Paragraph(
            f"{data.portfolio_name} &nbsp;·&nbsp; base currency {data.base_currency}",
            styles["subtitle"],
        ),
    ]

    generated = data.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    as_of = data.data_as_of.isoformat() if data.data_as_of else "no market data stored"
    story.append(
        Paragraph(
            f"Generated {generated}&nbsp;&nbsp;|&nbsp;&nbsp;Market data as of {as_of}"
            f"&nbsp;&nbsp;|&nbsp;&nbsp;Analysis period {data.analysis_period}",
            styles["muted"],
        )
    )
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(DISCLAIMER, styles["disclaimer"]))

    if data.summary:
        story.append(Paragraph("Portfolio summary", styles["heading"]))
        story.append(_metric_table(data.summary, styles))

    if data.holdings is not None:
        story.append(Paragraph("Holdings", styles["heading"]))
        story.extend(_block_table(data.holdings, styles))

    if data.allocation is not None:
        story.extend(_block_table(data.allocation, styles))

    if data.performance:
        story.append(Paragraph("Performance", styles["heading"]))
        story.append(_metric_table(data.performance, styles))

    if data.risk:
        story.append(Paragraph("Risk measures", styles["heading"]))
        story.append(_metric_table(data.risk, styles))

    if data.risk_contribution is not None:
        story.append(Paragraph("Risk attribution", styles["heading"]))
        story.extend(_block_table(data.risk_contribution, styles))

    if data.stress_tests:
        story.append(PageBreak())
        story.append(Paragraph("Stress tests", styles["heading"]))
        for block in data.stress_tests:
            story.extend(_block_table(block, styles))
            story.append(Spacer(1, 3 * mm))

    # The EWS subsection keeps its own heading and its own disclaimer. The report
    # as a whole is a Heimdall Risk Report, never a Gjallarhorn Report.
    if data.signals is not None:
        story.append(Paragraph("Gjallarhorn Early Warning Signals", styles["heading"]))
        story.extend(_block_table(data.signals, styles))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(EARLY_WARNING_DISCLAIMER, styles["disclaimer"]))

    if data.unavailable:
        story.append(Paragraph("Unavailable measures", styles["heading"]))
        story.append(
            Paragraph(
                "These measures could not be computed. They are reported as unavailable "
                "rather than shown as zero.",
                styles["muted"],
            )
        )
        story.extend(_bullets(data.unavailable, styles))

    tail: list[Any] = [Paragraph("Assumptions", styles["heading"])]
    tail.extend(_bullets(data.assumptions, styles))
    tail.append(Paragraph("Data sources", styles["heading"]))
    tail.extend(_bullets(data.data_sources, styles))
    tail.append(Paragraph("Limitations", styles["heading"]))
    tail.extend(_bullets(data.limitations, styles))
    tail.append(Spacer(1, 4 * mm))
    tail.append(Paragraph(DISCLAIMER, styles["disclaimer"]))
    story.append(KeepTogether([]))
    story.extend(tail)

    document.build(story, onFirstPage=_page_furniture, onLaterPages=_page_furniture)
    return buffer.getvalue()


def format_money(value: Decimal | float | None, currency: str, *, signed: bool = False) -> str:
    """Format a monetary amount.

    A negative amount always carries a minus sign, so the value stays readable in
    black and white and for a reader who cannot distinguish the colours.
    """
    if value is None:
        return "unavailable"
    amount = Decimal(str(value))
    sign = "+" if signed and amount > 0 else ""
    return f"{sign}{amount:,.2f} {currency}"


def format_percent(value: Decimal | float | None, *, signed: bool = False) -> str:
    """Format a fraction as a percentage."""
    if value is None:
        return "unavailable"
    number = float(value) * 100
    sign = "+" if signed and number > 0 else ""
    return f"{sign}{number:,.2f}%"


def format_ratio(value: Decimal | float | None) -> str:
    """Format a plain ratio to two decimal places."""
    if value is None:
        return "unavailable"
    return f"{float(value):,.2f}"
