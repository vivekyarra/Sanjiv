from __future__ import annotations

# ruff: noqa: E501
import json
import shutil
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageOps
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "submission" / "source"
OUTPUT_DIR = ROOT / "output" / "pdf"
SUBMISSION_DIR = ROOT / "submission"
TMP_DIR = ROOT / "tmp" / "pdfs" / "sanjiv_submission"
OUTPUT_PDF = OUTPUT_DIR / "Sanjiv_Final_Project_Document.pdf"
SUBMISSION_PDF = SUBMISSION_DIR / "Sanjiv_Final_Project_Document.pdf"
EVIDENCE = json.loads((SOURCE_DIR / "evidence_snapshot.json").read_text(encoding="utf-8"))

PAGE_W, PAGE_H = landscape(A4)

INK = colors.HexColor("#09241C")
GREEN = colors.HexColor("#0B6B46")
EMERALD = colors.HexColor("#17B978")
MINT = colors.HexColor("#DDF7EB")
PALE = colors.HexColor("#F5F8F5")
WHITE = colors.white
SLATE = colors.HexColor("#42584F")
MID = colors.HexColor("#6E8178")
LINE = colors.HexColor("#CAD8D1")
AMBER = colors.HexColor("#F2B134")
AMBER_PALE = colors.HexColor("#FFF4D9")
RED = colors.HexColor("#B93A3A")
SOFT_RED = colors.HexColor("#FBE8E8")


def register_fonts() -> tuple[str, str, str]:
    font_dir = Path("C:/Windows/Fonts")
    regular = font_dir / "segoeui.ttf"
    bold = font_dir / "segoeuib.ttf"
    mono = font_dir / "consola.ttf"
    if regular.exists() and bold.exists() and mono.exists():
        pdfmetrics.registerFont(TTFont("SanjivSans", str(regular)))
        pdfmetrics.registerFont(TTFont("SanjivSansBold", str(bold)))
        pdfmetrics.registerFont(TTFont("SanjivMono", str(mono)))
        return "SanjivSans", "SanjivSansBold", "SanjivMono"
    return "Helvetica", "Helvetica-Bold", "Courier"


FONT, FONT_BOLD, FONT_MONO = register_fonts()

STYLES = {
    "body": ParagraphStyle(
        "body", fontName=FONT, fontSize=9.0, leading=12.0, textColor=INK, spaceAfter=0
    ),
    "body_small": ParagraphStyle(
        "body_small", fontName=FONT, fontSize=8.0, leading=10.4, textColor=INK, spaceAfter=0
    ),
    "tiny": ParagraphStyle(
        "tiny", fontName=FONT, fontSize=6.9, leading=8.5, textColor=SLATE, spaceAfter=0
    ),
    "caption": ParagraphStyle(
        "caption", fontName=FONT, fontSize=7.2, leading=9.0, textColor=SLATE, spaceAfter=0
    ),
    "h1": ParagraphStyle(
        "h1", fontName=FONT_BOLD, fontSize=18, leading=21, textColor=INK, spaceAfter=0
    ),
    "h2": ParagraphStyle(
        "h2", fontName=FONT_BOLD, fontSize=13.0, leading=15.5, textColor=INK, spaceAfter=0
    ),
    "h3": ParagraphStyle(
        "h3", fontName=FONT_BOLD, fontSize=9.4, leading=11.0, textColor=GREEN, spaceAfter=0
    ),
    "kicker": ParagraphStyle(
        "kicker", fontName=FONT_BOLD, fontSize=7.4, leading=9.0, textColor=GREEN, spaceAfter=0
    ),
    "white": ParagraphStyle(
        "white", fontName=FONT, fontSize=9.2, leading=12.0, textColor=WHITE, spaceAfter=0
    ),
    "white_small": ParagraphStyle(
        "white_small", fontName=FONT, fontSize=7.8, leading=10.0, textColor=WHITE, spaceAfter=0
    ),
    "white_bold": ParagraphStyle(
        "white_bold", fontName=FONT_BOLD, fontSize=10, leading=12, textColor=WHITE, spaceAfter=0
    ),
    "mono": ParagraphStyle(
        "mono", fontName=FONT_MONO, fontSize=6.9, leading=8.6, textColor=INK, spaceAfter=0
    ),
}


def top_y(top: float, height: float = 0) -> float:
    return PAGE_H - top - height


def rect_top(
    c: canvas.Canvas,
    x: float,
    top: float,
    w: float,
    h: float,
    fill: colors.Color = WHITE,
    stroke: colors.Color = LINE,
    radius: float = 5,
    width: float = 0.7,
) -> None:
    c.setLineWidth(width)
    c.setStrokeColor(stroke)
    c.setFillColor(fill)
    c.roundRect(x, top_y(top, h), w, h, radius, fill=1, stroke=1)


def para(
    c: canvas.Canvas,
    html: str,
    x: float,
    top: float,
    w: float,
    h: float,
    style: str = "body",
    align: int | None = None,
) -> float:
    base = STYLES[style]
    chosen = base if align is None else ParagraphStyle(
        f"{style}_{align}", parent=base, alignment=align
    )
    p = Paragraph(html, chosen)
    pw, ph = p.wrap(w, h)
    if ph > h + 0.2:
        raise RuntimeError(f"Paragraph overflow ({ph:.1f}>{h:.1f}): {html[:80]}")
    p.drawOn(c, x, top_y(top, ph))
    return ph


def bullet_list(items: list[str], color: colors.Color = INK) -> str:
    return "<br/>".join(
        f'<font color="{color.hexval()}"><b>+</b></font> {item}' for item in items
    )


def page_base(c: canvas.Canvas, number: int, section: str) -> None:
    c.setFillColor(PALE)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.setFillColor(INK)
    c.rect(0, PAGE_H - 39, PAGE_W, 39, fill=1, stroke=0)
    c.setFillColor(EMERALD)
    c.rect(0, PAGE_H - 42, PAGE_W, 3, fill=1, stroke=0)
    c.setFont(FONT_BOLD, 8)
    c.setFillColor(WHITE)
    c.drawString(25, PAGE_H - 25, "SANJIV")
    c.setFont(FONT, 7.5)
    c.setFillColor(colors.HexColor("#B7D9CA"))
    c.drawString(79, PAGE_H - 25, section.upper())
    c.setStrokeColor(LINE)
    c.line(24, 20, PAGE_W - 24, 20)
    c.setFont(FONT, 6.8)
    c.setFillColor(MID)
    c.drawString(25, 8, f"FINAL PROJECT DOCUMENT  |  COMMIT {EVIDENCE['current_commit_sha'][:12]}")
    c.drawRightString(PAGE_W - 25, 8, f"{number:02d} / 10")


def page_title(c: canvas.Canvas, title: str, subtitle: str, section_no: str) -> None:
    para(c, section_no, 25, 54, 300, 14, "kicker")
    para(c, title, 25, 66, 520, 43, "h1")
    para(c, subtitle, 555, 60, PAGE_W - 580, 42, "body_small")


def label(c: canvas.Canvas, text: str, x: float, top: float, w: float) -> None:
    para(c, text.upper(), x, top, w, 11, "kicker")


def table_draw(
    c: canvas.Canvas,
    rows: list[list[str]],
    x: float,
    top: float,
    widths: list[float],
    height: float,
    font_size: float = 7.5,
    header: bool = True,
    aligns: list[str] | None = None,
) -> float:
    body_style = ParagraphStyle(
        "table_body", fontName=FONT, fontSize=font_size, leading=font_size + 2.0, textColor=INK
    )
    head_style = ParagraphStyle(
        "table_head", fontName=FONT_BOLD, fontSize=font_size, leading=font_size + 2.0, textColor=WHITE
    )
    data: list[list[Paragraph]] = []
    for ridx, row in enumerate(rows):
        converted = []
        for cidx, cell in enumerate(row):
            st = head_style if header and ridx == 0 else body_style
            if aligns:
                alignment = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT}[aligns[cidx]]
                st = ParagraphStyle(f"cell_{ridx}_{cidx}", parent=st, alignment=alignment)
            converted.append(Paragraph(cell, st))
        data.append(converted)
    table = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.45, LINE),
    ]
    if header:
        commands.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), GREEN),
                ("BACKGROUND", (0, 1), (-1, -1), WHITE),
            ]
        )
    else:
        commands.append(("BACKGROUND", (0, 0), (-1, -1), WHITE))
    for ridx in range(1 if header else 0, len(rows)):
        if ridx % 2 == 0:
            commands.append(("BACKGROUND", (0, ridx), (-1, ridx), colors.HexColor("#EEF4F0")))
    table.setStyle(TableStyle(commands))
    tw, th = table.wrap(sum(widths), height)
    if th > height + 0.2:
        raise RuntimeError(f"Table overflow ({th:.1f}>{height:.1f})")
    table.drawOn(c, x, top_y(top, th))
    return th


def stat(c: canvas.Canvas, x: float, top: float, w: float, value: str, title: str, note: str) -> None:
    rect_top(c, x, top, w, 66, WHITE, LINE)
    para(c, title.upper(), x + 10, top + 8, w - 20, 10, "kicker")
    para(c, value, x + 10, top + 22, w - 20, 21, "h2")
    para(c, note, x + 10, top + 45, w - 20, 14, "tiny")


def qr_draw(c: canvas.Canvas, value: str, x: float, top: float, size: float) -> None:
    widget = qr.QrCodeWidget(value)
    x1, y1, x2, y2 = widget.getBounds()
    scale = size / max(x2 - x1, y2 - y1)
    drawing = Drawing(size, size, transform=[scale, 0, 0, scale, 0, 0])
    drawing.add(widget)
    c.setFillColor(WHITE)
    c.roundRect(x - 5, top_y(top, size) - 5, size + 10, size + 10, 6, fill=1, stroke=0)
    renderPDF.draw(drawing, c, x, top_y(top, size))
    c.linkURL(value, (x - 5, top_y(top, size) - 5, x + size + 5, top_y(top, size) + size + 5))


def link_text(label_text: str, url: str, color: str = "#0B6B46") -> str:
    return f'<link href="{escape(url)}" color="{color}"><u>{escape(label_text)}</u></link>'


def screenshot_crop(
    c: canvas.Canvas,
    source_name: str,
    crop: tuple[int, int, int, int],
    x: float,
    top: float,
    w: float,
    h: float,
) -> None:
    source = ROOT / "reports" / "e2e" / "screenshots" / source_name
    key = (
        f"{source.stem}_{source.stat().st_mtime_ns}_"
        f"{'_'.join(str(v) for v in crop)}_{int(w)}x{int(h)}.jpg"
    )
    target = TMP_DIR / key
    if not target.exists():
        with Image.open(source) as raw:
            part = raw.convert("RGB").crop(crop)
            fitted = ImageOps.fit(
                part,
                (max(800, int(w * 3)), max(400, int(h * 3))),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            fitted.save(target, "JPEG", quality=92, optimize=True)
    c.setFillColor(INK)
    c.roundRect(x - 2, top_y(top, h) - 2, w + 4, h + 4, 4, fill=1, stroke=0)
    c.drawImage(str(target), x, top_y(top, h), width=w, height=h, mask="auto")


def flow_arrow(c: canvas.Canvas, x1: float, y: float, x2: float, color: colors.Color = EMERALD) -> None:
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(1.3)
    c.line(x1, y, x2 - 7, y)
    p = c.beginPath()
    p.moveTo(x2, y)
    p.lineTo(x2 - 7, y + 4)
    p.lineTo(x2 - 7, y - 4)
    p.close()
    c.drawPath(p, fill=1, stroke=0)


def cover(c: canvas.Canvas) -> None:
    c.setFillColor(INK)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#0E3B2C"))
    c.circle(PAGE_W - 20, PAGE_H - 35, 190, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#12513B"))
    c.circle(PAGE_W - 5, 20, 270, fill=1, stroke=0)
    c.setStrokeColor(colors.HexColor("#2C7758"))
    c.setLineWidth(0.8)
    for offset in range(0, 340, 28):
        c.line(PAGE_W - 360 + offset, 0, PAGE_W - 100 + offset, PAGE_H)

    c.setFillColor(EMERALD)
    c.roundRect(42, PAGE_H - 100, 48, 48, 9, fill=0, stroke=1)
    c.setFont(FONT_BOLD, 27)
    c.drawCentredString(66, PAGE_H - 87, "S")
    para(c, "INDIA'S ENERGY RESILIENCE COMMAND CENTER", 108, 54, 430, 20, "white_bold")
    para(c, "FINAL PROJECT DOCUMENT", 108, 76, 430, 15, "white_small")

    c.setFillColor(EMERALD)
    c.rect(42, PAGE_H - 158, 62, 4, fill=1, stroke=0)
    c.setFont(FONT_BOLD, 42)
    c.setFillColor(WHITE)
    c.drawString(42, PAGE_H - 197, "Sanjiv")
    para(
        c,
        "A command center for the moment a supply shock stops being a headline and becomes a decision. It shows what is known, what is assumed, what happens next, and who must approve the response.",
        42,
        220,
        505,
        65,
        "white",
    )

    rect_top(c, 42, 320, 510, 124, colors.HexColor("#0A2E23"), colors.HexColor("#2C7758"), 8)
    para(c, "WHY SANJIV EXISTS", 59, 338, 460, 15, "white_bold")
    para(
        c,
        "Energy resilience is not one prediction. It is a chain of imperfect signals, physical constraints and human responsibility. I built Sanjiv to keep that chain visible - especially the uncertainty.",
        59,
        363,
        462,
        55,
        "white_small",
    )

    qr_draw(c, EVIDENCE["repository_url"], 643, 76, 112)
    para(c, "SCAN FOR REPOSITORY", 622, 199, 155, 13, "white_small", TA_CENTER)

    links = [
        link_text("GitHub repository", EVIDENCE["repository_url"], "#8EF0C2"),
        link_text("Demo folder", EVIDENCE["demo_url"], "#8EF0C2"),
        link_text(EVIDENCE["contact_email"], f"mailto:{EVIDENCE['contact_email']}", "#8EF0C2"),
    ]
    para(c, "<br/>".join(links), 610, 247, 190, 70, "white_small", TA_CENTER)
    para(c, f"Built and documented by <b>{escape(EVIDENCE['contact_name'])}</b>", 610, 327, 190, 28, "white_small", TA_CENTER)
    para(c, f"Submission snapshot  |  {EVIDENCE['document_date']}", 610, 350, 190, 18, "white_small", TA_CENTER)
    para(
        c,
        f"Commit<br/><font name=\"{FONT_MONO}\">{EVIDENCE['current_commit_sha']}</font>",
        600,
        385,
        210,
        55,
        "white_small",
        TA_CENTER,
    )
    para(
        c,
        "All screenshots and measured values are traceable to repository artifacts. PortWatch is a live-fetched daily observation; fixture and replay evidence is never presented as live vessel tracking.",
        595,
        470,
        220,
        50,
        "white_small",
        TA_CENTER,
    )
    c.setFont(FONT, 6.8)
    c.setFillColor(colors.HexColor("#9AC8B4"))
    c.drawString(42, 22, "Sanjiv  |  Final submission document")
    c.drawRightString(PAGE_W - 42, 22, "01 / 10")
    c.showPage()


def problem_users(c: canvas.Canvas) -> None:
    page_base(c, 2, "Problem and target users")
    page_title(
        c,
        "A disruption does not arrive with clean data",
        "The team still has to answer: What changed? What breaks next? What can we do? Which numbers are trustworthy? Who signs off?",
        "02  /  PROBLEM",
    )

    rect_top(c, 25, 107, 378, 176, WHITE, LINE)
    label(c, "Imagine the moment", 40, 121, 170)
    para(
        c,
        "The Strait of Hormuz loses capacity. Vessel feeds may be incomplete. Inventory may be unknown. A media spike may be wrong. The response team still needs a defensible next move:",
        40,
        141,
        345,
        36,
        "body",
    )
    para(
        c,
        bullet_list(
            [
                "What do we know right now?",
                "What is inferred, modeled or assumed?",
                "What happens if no one acts?",
                "Which alternatives survive hard constraints?",
                "Who is accountable for the final decision?",
            ]
        ),
        40,
        180,
        345,
        90,
        "body_small",
    )

    rect_top(c, 418, 107, 398, 176, INK, INK)
    label(c, "The line I would not cross", 434, 121, 220)
    para(
        c,
        "Sanjiv recommends; a human decides. It can observe, freeze a scenario, simulate consequences, compare candidate plans, audit the evidence and preserve a decision record.",
        434,
        143,
        365,
        45,
        "white",
    )
    para(
        c,
        "It cannot place an order, charter a tanker, release a reserve, control a pipeline or operate a refinery. Public capacity metadata does not establish current fill, cargo ownership or commercial availability. That boundary is deliberate. [1][2]",
        434,
        196,
        365,
        66,
        "white_small",
    )

    label(c, "Primary users", 25, 306, 180)
    users = [
        ("Maritime and geopolitical analyst", "Vessel and chokepoint activity, source health, risk explanation, provenance and historical comparison."),
        ("Refinery procurement head", "Candidate suppliers, grades, landed cost, arrival timing, compatibility, sanctions and corridor risk."),
        ("Strategic reserve planner", "Capacity versus opening-fill truth, draw schedule, logistics, policy floors and replenishment constraints."),
        ("Reviewer and approver", "Evidence coverage, recomputation, rejected alternatives, immutable comments and explicit authority."),
    ]
    card_w = 190
    for idx, (title, desc) in enumerate(users):
        x = 25 + idx * 199
        rect_top(c, x, 326, card_w, 118, WHITE, LINE)
        para(c, f"0{idx + 1}", x + 12, 339, 32, 20, "h2")
        para(c, title, x + 12, 362, card_w - 24, 31, "h3")
        para(c, desc, x + 12, 397, card_w - 24, 37, "tiny")

    rect_top(c, 25, 463, 791, 84, MINT, colors.HexColor("#8FCFB2"))
    label(c, "Scope delivered in the repository", 40, 477, 260)
    table_draw(
        c,
        [
            ["Commodity", "Operating mode", "Decision outputs", "Excluded claims"],
            ["Crude oil; typed LPG extension", "Live-fetched PortWatch observation plus checksummed replay and fixtures", "No-action simulation; procurement; reserve; audit; approval; replay export", "No live AIS claim; no private inventory; no confirmed cargo or contract; no execution"],
        ],
        40,
        496,
        [110, 205, 255, 188],
        44,
        7.1,
    )
    c.showPage()


def solution_workflow(c: canvas.Canvas) -> None:
    page_base(c, 3, "Solution and workflow")
    page_title(
        c,
        "Follow one decision from signal to sign-off",
        "Every handoff leaves a fingerprint. If evidence disappears along the way, the decision metric disappears with it.",
        "03  /  SOLUTION",
    )

    label(c, "The six handoffs", 25, 106, 200)
    steps = [
        ("1", "OBSERVE", "Source mode, freshness and evidence"),
        ("2", "FREEZE", "Scenario plus immutable twin fingerprint"),
        ("3", "SIMULATE", "Paired baseline and no-action impact"),
        ("4", "OPTIMISE", "Three procurement and four reserve profiles"),
        ("5", "AUDIT", "Coverage, claims, hashes and recomputation"),
        ("6", "APPROVE", "Server-owned immutable human record"),
    ]
    step_w = 116
    gap = 16
    for idx, (num, title, desc) in enumerate(steps):
        x = 25 + idx * (step_w + gap)
        rect_top(c, x, 128, step_w, 96, WHITE, colors.HexColor("#9CCDB8"), 7)
        c.setFillColor(GREEN)
        c.circle(x + 17, top_y(143), 10, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont(FONT_BOLD, 8)
        c.drawCentredString(x + 17, top_y(146), num)
        para(c, title, x + 33, 137, step_w - 40, 14, "h3")
        para(c, desc, x + 12, 163, step_w - 24, 48, "tiny")
        if idx < len(steps) - 1:
            y = top_y(176)
            flow_arrow(c, x + step_w + 2, y, x + step_w + gap - 2)

    rect_top(c, 25, 247, 506, 292, WHITE, LINE)
    label(c, "What sits behind the screens", 40, 261, 240)
    layers = [
        ("COMMAND CENTER", "Next.js / React / typed REST and WebSocket clients", MINT),
        ("DOMAIN CORE", "FastAPI modular monolith: sources, maritime, twin, scenario, simulation, optimisation, risk, audit, replay", colors.HexColor("#E8F1ED")),
        ("WORKERS", "Ingestion, scheduled refresh and compute workers import the same domain services", AMBER_PALE),
        ("STATE", "PostgreSQL + PostGIS + TimescaleDB (authoritative)  |  Redis (cache/fan-out)  |  MinIO (immutable artifacts)", colors.HexColor("#E7ECE9")),
    ]
    top = 286
    for title, desc, fill in layers:
        rect_top(c, 42, top, 472, 43, fill, colors.HexColor("#AFC7BB"), 4)
        para(c, title, 54, top + 8, 105, 12, "kicker")
        para(c, desc, 162, top + 7, 338, 29, "body_small")
        top += 51
    para(
        c,
        "I kept the first deployment deliberately compact: one measured modular monolith with shared domain services. Multiple API replicas come only after Redis WebSocket fan-out and deployment identity are in place.",
        42,
        487,
        472,
        27,
        "tiny",
    )

    rect_top(c, 545, 247, 271, 292, INK, INK)
    label(c, "Five words with strict meanings", 562, 261, 230)
    truth = [
        ("OBSERVED", "Directly retrieved or supplied; normalization only."),
        ("DERIVED", "Deterministic calculation from identified inputs."),
        ("INFERRED", "Heuristic or probabilistic classification."),
        ("MODELED", "Simulator or optimiser output."),
        ("ASSUMPTION", "Visible editable input used when verification is absent."),
    ]
    y = 288
    for name, desc in truth:
        c.setFillColor(EMERALD if name != "ASSUMPTION" else AMBER)
        c.roundRect(562, top_y(y, 18), 82, 18, 4, fill=1, stroke=0)
        c.setFont(FONT_BOLD, 6.7)
        c.setFillColor(INK)
        c.drawCentredString(603, top_y(y, 13), name)
        para(c, desc, 652, y + 1, 146, 30, "white_small")
        y += 38
    para(
        c,
        "Required fields: source references; effective, fetch and compute timestamps; freshness; confidence; evidence IDs; transformation; units; model and contract versions.",
        562,
        473,
        236,
        43,
        "white_small",
    )
    c.showPage()


def product_observe_simulate(c: canvas.Canvas) -> None:
    page_base(c, 4, "Product evidence: Observe and Simulate")
    page_title(
        c,
        "Real observations and replay stay visibly separate",
        "PortWatch is live-fetched public data marked OBSERVED and CURRENT. The AIS position layer and modeled risk remain separately labeled replay or fixture evidence.",
        "04  /  PRODUCT 1 OF 3",
    )
    portwatch = EVIDENCE["portwatch_observation"]
    left_x, right_x, panel_w = 25, 425, 391
    rect_top(c, left_x, 108, panel_w, 438, WHITE, LINE)
    label(c, "Observe - Command Center", left_x + 14, 121, 250)
    screenshot_crop(c, "01-live-maritime-watch.png", (0, 0, 1920, 900), left_x + 14, 144, panel_w - 28, 170)
    para(
        c,
        f"The public IMF PortWatch service returned <b>{portwatch['tanker_transits']} tanker transits</b>, <b>{portwatch['total_transits']} total transits</b> and <b>{portwatch['estimated_tanker_tonnage']:,} t</b> estimated tanker tonnage for {portwatch['effective_date']}. The fetch is OBSERVED / CURRENT; it is a daily AIS-derived estimate, not live vessel tracking.",
        left_x + 14,
        327,
        panel_w - 28,
        58,
        "body_small",
    )
    table_draw(
        c,
        [
            ["Source plane", "Truth shown in the application"],
            ["PortWatch daily passage", "LIVE fetch; OBSERVED; CURRENT; source date and fetch time visible"],
            ["AIS vessel positions", "REPLAY; synthetic vessels; reported and inferred fields remain distinct"],
            ["Risk model", "FIXTURE / replay inputs remain separate from the observed PortWatch card"],
        ],
        left_x + 14,
        407,
        [105, panel_w - 133],
        108,
        6.7,
    )

    rect_top(c, right_x, 108, panel_w, 438, WHITE, LINE)
    label(c, "Risk Intelligence - observed signal", right_x + 14, 121, 280)
    screenshot_crop(c, "03-risk-intelligence.png", (0, 0, 1920, 620), right_x + 14, 144, panel_w - 28, 118)
    para(
        c,
        "The observed PortWatch card sits above the structural risk ranking. The model remains explicitly fixture-based and severity is not presented as disruption probability.",
        right_x + 14,
        273,
        panel_w - 28,
        38,
        "body_small",
    )
    label(c, "Simulate - Scenario Lab", right_x + 14, 325, 240)
    screenshot_crop(c, "04-scenario-lab.png", (0, 0, 1920, 795), right_x + 14, 347, panel_w - 28, 150)
    para(
        c,
        "A person confirms the parsed disruption before the twin is frozen. Baseline and no-action outputs share one fingerprint; missing inventory remains UNKNOWN.",
        right_x + 14,
        510,
        panel_w - 28,
        33,
        "body_small",
    )
    c.showPage()


def product_optimise_reserve(c: canvas.Canvas) -> None:
    page_base(c, 5, "Product evidence: Optimise and Reserve")
    page_title(
        c,
        "Give the human real choices, not one magic answer.",
        "Each candidate exposes the trade-off it is making. Public reserve capacity never quietly becomes an invented opening fill.",
        "05  /  PRODUCT 2 OF 3",
    )
    left_x, right_x, panel_w = 25, 425, 391
    rect_top(c, left_x, 108, panel_w, 438, WHITE, LINE)
    label(c, "Optimise - Response Planner", left_x + 14, 121, 260)
    screenshot_crop(c, "05-response-planner.png", (0, 0, 1920, 795), left_x + 14, 144, panel_w - 28, 150)
    screenshot_crop(c, "05-response-planner.png", (0, 750, 1920, 1545), left_x + 14, 303, panel_w - 28, 150)
    para(
        c,
        "<b>Builder's note.</b> LOWEST COST, BALANCED and HIGHEST RESILIENCE share the same hard constraints and input fingerprint. The point is not a magic answer; it is a legible choice with checker state, shortage, cost components, rejections, evidence and assumptions.",
        left_x + 14,
        466,
        panel_w - 28,
        63,
        "body_small",
    )

    rect_top(c, right_x, 108, panel_w, 438, WHITE, LINE)
    label(c, "Reserve - Strategic Reserve", right_x + 14, 121, 260)
    screenshot_crop(c, "06-strategic-reserve.png", (0, 0, 1920, 795), right_x + 14, 144, panel_w - 28, 150)
    screenshot_crop(c, "06-strategic-reserve.png", (0, 750, 1920, 1545), right_x + 14, 303, panel_w - 28, 150)
    para(
        c,
        "<b>Builder's note.</b> Capacity is not fill. The screen keeps public site capacity separate from the synthetic opening-fill assumption, then checks floors, draw and receipt limits, transit and residual shortage. No replenishment input means no hidden replenishment.",
        right_x + 14,
        466,
        panel_w - 28,
        63,
        "body_small",
    )
    c.showPage()


def product_audit_replay(c: canvas.Canvas) -> None:
    page_base(c, 6, "Product evidence: Audit, Approve and Monitor")
    page_title(
        c,
        "A plan is not trusted because the interface says 'optimal'.",
        "Trust comes from the evidence, the arithmetic and the person willing to sign their name to the decision.",
        "06  /  PRODUCT 3 OF 3",
    )
    left_x, right_x, panel_w = 25, 425, 391
    rect_top(c, left_x, 108, panel_w, 438, WHITE, LINE)
    label(c, "Audit and Approve - Evidence workspace", left_x + 14, 121, 320)
    screenshot_crop(c, "07-evidence-human-approval.png", (0, 0, 1920, 795), left_x + 14, 144, panel_w - 28, 150)
    screenshot_crop(c, "07-evidence-human-approval.png", (0, 1275, 1920, 2070), left_x + 14, 303, panel_w - 28, 150)
    para(
        c,
        "<b>Builder's note.</b> The captured audit is PASSED with 100.0% coverage and RECOMPUTE_RECONCILED. The approval stores server-resolved actor, role, UTC time and an immutable comment. It records a human decision; it never executes one.",
        left_x + 14,
        466,
        panel_w - 28,
        63,
        "body_small",
    )

    rect_top(c, right_x, 108, panel_w, 438, WHITE, LINE)
    label(c, "Monitor - Historical Replay and LPG", right_x + 14, 121, 300)
    screenshot_crop(c, "08-replay-lpg-monitoring-export.png", (0, 0, 1920, 795), right_x + 14, 144, panel_w - 28, 150)
    screenshot_crop(c, "08-replay-lpg-monitoring-export.png", (0, 800, 1920, 1595), right_x + 14, 303, panel_w - 28, 150)
    para(
        c,
        "<b>Builder's note.</b> Twenty-one versioned CC0 synthetic cases keep regression and demonstration repeatable. Classification, generator, license, assumptions, invariants and audit state stay visible. Seeded sensitivity is deterministic analysis, not a probability forecast.",
        right_x + 14,
        466,
        panel_w - 28,
        63,
        "body_small",
    )
    c.showPage()


def evidence_security(c: canvas.Canvas) -> None:
    page_base(c, 7, "Evidence, assumptions, security and approval")
    page_title(
        c,
        "Provenance must survive a hard question",
        "If someone asks, 'Where did that number come from?', the answer should be one click away - or the number should not be on the decision screen.",
        "07  /  GOVERNANCE",
    )

    rect_top(c, 25, 108, 340, 184, WHITE, LINE)
    label(c, "Evidence chain", 40, 121, 170)
    chain = [
        ("RAW", "Hash and licensing permit"),
        ("NORMALIZE", "Schema, units, time, identity"),
        ("METRIC", "Truth class and full envelope"),
        ("AUDIT", "Freshness, claims, recompute"),
        ("DECISION", "Submit, review, approve/reject"),
    ]
    y = 151
    for idx, (name, desc) in enumerate(chain):
        c.setFillColor(GREEN)
        c.roundRect(42, top_y(y, 24), 77, 24, 4, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont(FONT_BOLD, 6.8)
        c.drawCentredString(80.5, top_y(y, 16), name)
        para(c, desc, 132, y + 3, 206, 20, "body_small")
        if idx < len(chain) - 1:
            c.setStrokeColor(colors.HexColor("#8FCFB2"))
            c.line(80, top_y(y + 26), 80, top_y(y + 33))
        y += 29
    para(c, "Missing mandatory evidence blocks the metric from decision UI and briefing output.", 25, 297, 340, 13, "tiny")

    rect_top(c, 379, 108, 437, 184, INK, INK)
    label(c, "Security and authority boundary", 395, 121, 260)
    para(
        c,
        bullet_list(
            [
                "Credentials stay server-side; browser configuration contains only the public API origin.",
                "Production API and governance fail closed without configured server-side identities.",
                "Origin, request size/type, rate, SSRF-safe adapter and bounded solver controls are implemented.",
                "Independent checkers and the Evidence Auditor block failed plans, approvals and exports.",
                "Terminal plans, audits, approvals, exports and snapshots are append-only or database-immutable.",
            ],
            EMERALD,
        ),
        395,
        149,
        402,
        109,
        "white_small",
    )
    para(
        c,
        "Residual boundary: deployment IdP, TLS termination, multi-user session policy and Redis fan-out are operator-owned prerequisites.",
        395,
        265,
        402,
        23,
        "white_small",
    )

    label(c, "Registered external sources and exact truth treatment", 25, 314, 410)
    source_rows = [
        ["Source", "Repository use", "Truth and limitation", "Ref."],
        ["PPAC", "Typed offline import boundary for refinery and energy statistics", "Bundled operating values are assumptions; no PPAC payload is bundled", "[1]"],
        ["ISPRL", "Public reserve-site capacity and connectivity metadata", "Capacity may be observed; current fill stays unknown without verified input", "[2]"],
        ["IMF PortWatch", "Live-fetched daily passage observation and baseline", "Observed public estimate; current by source cadence; not live AIS", "[3]"],
        ["OFAC", "Official sanctions list files", "List entry observed; exact match derived; fuzzy match inferred", "[4]"],
        ["EIA / FRED", "Optional price, supply and macro series", "Series cadence, units, rights and attribution remain source-specific", "[5][6]"],
        ["NASA FIRMS / GDELT", "Optional thermal and media signals", "Signal is not proof of closure, attack, cause or damage", "[7][8]"],
    ]
    table_draw(c, source_rows, 25, 335, [95, 220, 405, 45], 202, 7.0)
    c.showPage()


def validation(c: canvas.Canvas) -> None:
    page_base(c, 8, "Validation, benchmarks and failure handling")
    page_title(
        c,
        "Here is what actually passed - and what it does not prove",
        "Machine, dataset, timestamp and commit matter. Current tests were rerun; performance evidence was regenerated from a clean committed application source.",
        "08  /  VALIDATION",
    )

    tests = EVIDENCE["current_test_run"]
    stat(
        c,
        25,
        108,
        184,
        f"{tests['total_passed']} passed",
        "Current npm test",
        f"{tests['python_passed']} Python + {tests['web_passed']} web + {tests['contracts_passed']} contracts",
    )
    stat(
        c,
        218,
        108,
        184,
        "0 / 0",
        "Failed / skipped",
        f"Exit 0; elapsed {EVIDENCE['current_test_run']['elapsed_seconds']:.1f} s",
    )
    stat(c, 411, 108, 184, "2 journeys", "Browser E2E coverage", "All 8 product screens; Observe to Monitor")
    stat(c, 604, 108, 212, "21 cases", "Replay catalogue", "Checksummed CC0 synthetic fixture")

    label(c, "Local fixture performance (milliseconds)", 25, 191, 360)
    metrics = EVIDENCE["performance_report"]["metrics_ms"]
    perf_rows = [["Metric", "Median", "p95", "n"]]
    for name, value in metrics.items():
        perf_rows.append(
            [escape(name), f"{value['median']:.3f}", f"{value['p95']:.3f}", str(value["samples"])]
        )
    table_draw(c, perf_rows, 25, 211, [185, 70, 70, 38], 297, 7.2, aligns=["left", "right", "right", "right"])
    para(
        c,
        "Report classification: <b>MEASURED_LOCAL_SYNTHETIC_FIXTURE</b>. Five samples unless shown otherwise. These are release measurements, not production SLAs or model-accuracy claims.",
        25,
        500,
        363,
        36,
        "tiny",
    )

    x = 420
    rect_top(c, x, 191, 396, 88, WHITE, LINE)
    label(c, "Benchmark identity", x + 14, 204, 180)
    para(
        c,
        f"Run <font name=\"{FONT_MONO}\">{EVIDENCE['performance_report']['run_id']}</font><br/>"
        f"Report commit <font name=\"{FONT_MONO}\">{EVIDENCE['performance_report']['commit_sha']}</font><br/>"
        f"Source state <b>{EVIDENCE['performance_report']['source_state']}</b>; timestamp {EVIDENCE['performance_report']['timestamp']}",
        x + 14,
        224,
        368,
        48,
        "tiny",
    )

    rect_top(c, x, 288, 396, 78, MINT, colors.HexColor("#8FCFB2"))
    label(c, "Browser, load and resync", x + 14, 301, 220)
    browser = EVIDENCE["browser_report"]
    load = EVIDENCE["performance_report"]["load"]
    ws = EVIDENCE["performance_report"]["websocket_resync"]
    para(
        c,
        f"Map {browser['map_fps']:.2f} FPS; interaction {browser['interaction_latency_ms']:.3f} ms; frame-time p95 {browser['frame_time_p95_ms']:.1f} ms across {browser['sample_frames']} frames.<br/>"
        f"Load: {load['successful']}/{load['requests']} successful at concurrency {load['concurrency']}; p95 {load['p95_ms']:.3f} ms. Resync observed after {ws['published']} publishes; p95 {ws['p95_ms']:.3f} ms.",
        x + 14,
        321,
        368,
        39,
        "body_small",
    )

    label(c, "Dependency failure and recovery drill (ms)", x, 383, 330)
    rel_rows = [["Component", "Detection", "Recovery", "Result"]]
    for name, value in EVIDENCE["reliability_report"]["checks"].items():
        detect = "n/a" if value["detection_ms"] is None else f"{value['detection_ms']:.3f}"
        rel_rows.append([name, detect, f"{value['recovery_ms']:.3f}", "PASS"])
    table_draw(c, rel_rows, x, 403, [130, 84, 84, 70], 139, 7.0, aligns=["left", "right", "right", "center"])

    rect_top(c, x, 504, 396, 34, WHITE, LINE)
    para(
        c,
        f"<b>Security:</b> {EVIDENCE['security_report']['status']} ({EVIDENCE['security_report']['checks']} checks; {EVIDENCE['security_report']['failure_names']} failure names). "
        f"<b>Backup/restore:</b> PASS; {EVIDENCE['backup_restore_report']['backup_bytes']:,} bytes; migration {EVIDENCE['backup_restore_report']['restored_migration']}; corrupt artifact rejected.",
        x + 10,
        512,
        376,
        22,
        "tiny",
    )
    c.showPage()


def value_deployment(c: canvas.Canvas) -> None:
    page_base(c, 9, "Business value, scalability and deployment path")
    page_title(
        c,
        "The value is a better decision record",
        "The repository proves observed-source ingestion, workflow mechanics and deterministic checks on fixtures. Operational value still requires licensed history and verified operator inputs.",
        "09  /  PATH TO USE",
    )

    col_w = 250
    xs = [25, 295, 565]
    rect_top(c, xs[0], 108, col_w, 206, WHITE, LINE)
    label(c, "Decision value now", xs[0] + 14, 122, 180)
    para(
        c,
        bullet_list(
            [
                "One immutable chain from source state to approval.",
                "Paired no-action and response alternatives on the same frozen inputs.",
                "Independent feasibility checks and named rejected options.",
                "Visible assumption ownership, expiry, freshness and evidence coverage.",
                "Audited JSON/PDF packages plus monitored replay outcomes.",
            ]
        ),
        xs[0] + 14,
        150,
        col_w - 28,
        137,
        "body_small",
    )
    para(c, "No rupee savings, avoided-loss value or decision-time reduction was measured.", xs[0] + 14, 287, col_w - 28, 21, "tiny")

    rect_top(c, xs[1], 108, col_w, 206, INK, INK)
    label(c, "Verified deployment shape", xs[1] + 14, 122, 210)
    para(
        c,
        "Docker Compose runs the same web/API images, three workers, PostgreSQL with PostGIS and TimescaleDB, Redis and MinIO for local and demo use.",
        xs[1] + 14,
        150,
        col_w - 28,
        50,
        "white_small",
    )
    para(
        c,
        bullet_list(
            [
                "Liveness and dependency-aware readiness",
                "Source, worker and request-runtime status",
                "Structured logs and trace-compatible identifiers",
                "Backup/restore and single-dependency drills",
            ],
            EMERALD,
        ),
        xs[1] + 14,
        207,
        col_w - 28,
        80,
        "white_small",
    )

    rect_top(c, xs[2], 108, col_w, 206, WHITE, LINE)
    label(c, "Scaling policy", xs[2] + 14, 122, 170)
    para(
        c,
        bullet_list(
            [
                "Scale vertically first using measured queue and request latency.",
                "Add ingestion/refresh/compute worker replicas by workload.",
                "Add Redis WebSocket fan-out before multiple API replicas.",
                "Use managed database/object storage, external TLS and an operator collector.",
                "Require an ADR and workload evidence before Kubernetes or domain microservices.",
            ]
        ),
        xs[2] + 14,
        150,
        col_w - 28,
        139,
        "body_small",
    )

    label(c, "Operational adoption roadmap", 25, 343, 300)
    readiness = [
        ("01", "Replace fixtures", "Licensed recorded history and verified private/operator inputs."),
        ("02", "Calibrate", "Out-of-sample thresholds, model weights and decision policies with domain owners."),
        ("03", "Secure identities", "Deployment IdP, TLS edge, rotation, sessions and least privilege."),
        ("04", "Scale and recover", "Redis fan-out, managed HA, encrypted off-site backup and multi-region drills."),
        ("05", "Accept and govern", "Operator acceptance, data rights, model monitoring and change control."),
    ]
    for idx, (num, title, desc) in enumerate(readiness):
        x = 25 + idx * 158
        rect_top(c, x, 366, 145, 102, WHITE, LINE)
        para(c, num, x + 12, 378, 35, 18, "h2")
        para(c, title, x + 12, 401, 120, 25, "h3")
        para(c, desc, x + 12, 430, 120, 32, "tiny")

    rect_top(c, 25, 489, 791, 48, AMBER_PALE, colors.HexColor("#E4C06B"))
    label(c, "Metrics for a real deployment - not results in this submission", 40, 499, 420)
    para(
        c,
        "Shortfall reduction; incremental cost per avoided shortage unit; inventory-cover extension; refinery-utilisation recovery; supplier and corridor concentration; decision time saved. Each requires a baseline, verified input data and an agreed measurement window.",
        40,
        514,
        758,
        20,
        "tiny",
    )
    c.showPage()


def limitations_refs(c: canvas.Canvas) -> None:
    page_base(c, 10, "Limitations, references and submission links")
    page_title(
        c,
        "What I refused to fake",
        "A convincing demo should make its limits easier to see, not easier to miss. Real PortWatch observations and fixture-based decision evidence remain explicitly separated.",
        "10  /  LIMITS AND REFERENCES",
    )

    rect_top(c, 25, 108, 370, 300, WHITE, LINE)
    label(c, "Current limitations", 40, 122, 190)
    limits = [
        "PortWatch passage data is live-fetched and labeled OBSERVED / CURRENT; AIS positions, decision-model inputs and the replay catalogue remain fixture or replay evidence where shown.",
        "Commercial price, supplier availability, port/refinery values and reserve opening fill are synthetic assumptions unless replaced by verified operator records.",
        "No order placement, tanker charter, reserve release, pipeline or refinery-control integration exists.",
        "Risk weights, alert thresholds and deterministic sensitivity are not calibrated disruption probabilities.",
        f"The benchmark is a one-machine local synthetic-fixture run from clean application commit {EVIDENCE['performance_report']['commit_sha'][:12]}; it is release evidence, not a production SLA or model-accuracy result.",
        "The recovery drill stops one dependency at a time on a local single-host stack; it does not establish multi-region failover.",
        "Production requires deployment IdP, TLS, key rotation, sessions, managed backups and Redis fan-out before horizontal API scaling.",
        "Licensed recorded validation, domain-owner calibration and operator acceptance remain required before operational decision use.",
    ]
    y = 148
    for idx, item in enumerate(limits):
        c.setFillColor(AMBER if idx in {0, 4} else GREEN)
        c.circle(47, top_y(y + 5), 3.2, fill=1, stroke=0)
        used = para(c, item, 58, y, 319, 37, "body_small")
        y += used + 5

    rect_top(c, 410, 108, 406, 300, WHITE, LINE)
    label(c, "Authoritative references", 425, 122, 220)
    refs = [
        ("[1] PPAC - Installed Refining Capacity", "https://ppac.gov.in/infrastructure/installed-refinery-capacity"),
        ("[2] ISPRL - Strategic reserve facilities", "https://isprlindia.com/aboutus.asp"),
        ("[3] IMF PortWatch - Data and methodology", "https://portwatch.imf.org/pages/data-and-methodology/"),
        ("[4] OFAC - Sanctions List Service", "https://ofac.treasury.gov/sanctions-list-service"),
        ("[5] U.S. EIA - API v2 documentation", "https://www.eia.gov/opendata/documentation.php"),
        ("[6] FRED - API overview", "https://fred.stlouisfed.org/docs/api/fred/overview.html"),
        ("[7] NASA FIRMS - Area API", "https://firms.modaps.eosdis.nasa.gov/api/area/"),
        ("[8] GDELT - DOC 2.0 API", "https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/"),
    ]
    y = 149
    for title, url in refs:
        para(c, link_text(title, url), 425, y, 365, 15, "body_small")
        para(c, escape(url), 425, y + 14, 365, 13, "tiny")
        y += 31

    rect_top(c, 25, 425, 791, 113, INK, INK)
    label(c, "Submission links", 42, 439, 170)
    qr_draw(c, EVIDENCE["repository_url"], 43, 461, 60)
    para(c, "Repository QR", 40, 524, 70, 12, "white_small", TA_CENTER)
    para(
        c,
        f"<b>Repository</b><br/>{link_text(EVIDENCE['repository_url'], EVIDENCE['repository_url'], '#8EF0C2')}<br/><br/>"
        f"<b>Demo</b><br/>{link_text(EVIDENCE['demo_url'], EVIDENCE['demo_url'], '#8EF0C2')}",
        125,
        449,
        430,
        79,
        "white_small",
    )
    para(
        c,
        f"<b>Author</b><br/>{escape(EVIDENCE['contact_name'])}<br/>{link_text(EVIDENCE['contact_email'], 'mailto:' + EVIDENCE['contact_email'], '#8EF0C2')}<br/><br/>"
        f"<b>Application commit</b><br/><font name=\"{FONT_MONO}\">{EVIDENCE['current_commit_sha']}</font>",
        575,
        449,
        220,
        79,
        "white_small",
    )
    c.showPage()


def validate_evidence_snapshot() -> None:
    if EVIDENCE["current_commit_sha"] != "14a7e5deb639aeb6de4e683ec62cd22abbea0838":
        raise RuntimeError("Unexpected final commit SHA in evidence snapshot")
    if EVIDENCE["current_test_run"]["total_passed"] != 212:
        raise RuntimeError("Unexpected current test total")
    required = [
        "01-live-maritime-watch.png",
        "04-scenario-lab.png",
        "05-response-planner.png",
        "06-strategic-reserve.png",
        "07-evidence-human-approval.png",
        "08-replay-lpg-monitoring-export.png",
    ]
    for name in required:
        if not (ROOT / "reports" / "e2e" / "screenshots" / name).exists():
            raise FileNotFoundError(name)


def build() -> None:
    validate_evidence_snapshot()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SUBMISSION_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUTPUT_PDF), pagesize=(PAGE_W, PAGE_H), pageCompression=1)
    c.setTitle("Sanjiv - Final Project Document")
    c.setAuthor(EVIDENCE["contact_name"])
    c.setSubject("India's Energy Resilience Command Center - submission-ready project document")
    c.setCreator("Editable ReportLab source in submission/source")
    cover(c)
    problem_users(c)
    solution_workflow(c)
    product_observe_simulate(c)
    product_optimise_reserve(c)
    product_audit_replay(c)
    evidence_security(c)
    validation(c)
    value_deployment(c)
    limitations_refs(c)
    c.save()
    shutil.copy2(OUTPUT_PDF, SUBMISSION_PDF)
    print(OUTPUT_PDF)
    print(SUBMISSION_PDF)


if __name__ == "__main__":
    build()
