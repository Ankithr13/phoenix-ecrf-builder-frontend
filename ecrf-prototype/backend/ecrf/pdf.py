"""The two PDFs: a locked blank eCRF, and a subject casebook. Built on the server
with reportlab, so nothing depends on a browser's print dialog.

Protocol text often holds characters the standard PDF fonts cannot draw, such
as the greater-or-equal sign, so these use the Vera font reportlab ships with.
Everything from the protocol or the database is escaped before it reaches a
Paragraph, which would otherwise read it as markup.
"""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ecrf.schema import DraftECRF, FieldDef

FONT, BOLD = "Vera", "VeraBd"
pdfmetrics.registerFont(TTFont(FONT, "Vera.ttf"))
pdfmetrics.registerFont(TTFont(BOLD, "VeraBd.ttf"))

INK = colors.HexColor("#1b2a33")
MUTED = colors.HexColor("#5f6d76")
LINE = colors.HexColor("#c9d1d6")
SHADE = colors.HexColor("#eef1f3")

H1 = ParagraphStyle("h1", fontName=BOLD, fontSize=14, leading=18, textColor=INK, spaceAfter=8)
H2 = ParagraphStyle("h2", fontName=BOLD, fontSize=10.5, leading=14, textColor=INK, spaceBefore=8, spaceAfter=4)
BODY = ParagraphStyle("body", fontName=FONT, fontSize=9, leading=12, textColor=INK)
NAME = ParagraphStyle("name", fontName=BOLD, fontSize=9.5, leading=13, textColor=INK)
META = ParagraphStyle("meta", fontName=FONT, fontSize=8, leading=11, textColor=MUTED)
QUOTE = ParagraphStyle("quote", fontName=FONT, fontSize=6.5, leading=8, textColor=MUTED, spaceAfter=4)
CELL = ParagraphStyle("cell", fontName=FONT, fontSize=7.5, leading=9.5, textColor=INK)
CELL_HEAD = ParagraphStyle("cellhead", fontName=BOLD, fontSize=7.5, leading=9.5, textColor=INK)


def _p(text, style=BODY) -> Paragraph:
    return Paragraph(escape(str(text)), style)


def _build(title: str, header: str, story: list) -> bytes:
    def frame(canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT, 7.5)
        canvas.setFillColor(MUTED)
        width, height = letter
        canvas.drawString(0.75 * inch, height - 0.5 * inch, header[:125])
        canvas.setStrokeColor(LINE)
        canvas.line(0.75 * inch, height - 0.56 * inch, width - 0.75 * inch, height - 0.56 * inch)
        canvas.drawRightString(width - 0.75 * inch, 0.45 * inch, f"Page {doc.page}")
        canvas.restoreState()

    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=letter, title=title, author="Phoenix eCRF Builder",
                            leftMargin=0.75 * inch, rightMargin=0.75 * inch, topMargin=0.8 * inch, bottomMargin=0.7 * inch)
    doc.build(story, onFirstPage=frame, onLaterPages=frame)
    return out.getvalue()


def _field_block(f: FieldDef) -> KeepTogether:
    facts = [f.type]
    if f.repeats > 1:
        facts.append(f"{f.repeats} readings")
    if f.unit:
        facts.append(f.unit)
    if f.min is not None or f.max is not None:
        low = "" if f.min is None else f"{f.min:g}"
        high = "" if f.max is None else f"{f.max:g}"
        facts.append(f"range {low} to {high}")
    if f.cdash:
        facts.append(f"CDASH {f.cdash}")
    facts.append("required" if f.required else "optional")
    parts = [_p(f.name, NAME), _p(" · ".join(facts), META)]
    if f.choices:
        parts.append(_p("Choices: " + " / ".join(f.choices), META))
    answer = Table([[""]], colWidths=[3.2 * inch], rowHeights=[0.14 * inch])
    answer.hAlign = "LEFT"
    answer.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE)]))
    parts.append(answer)
    if f.origin == "foundation":
        source = "Standard field the system puts on every protocol. Not quoted from the protocol."
    else:
        source = f"Protocol {f.source.section}: \"{f.source.quote}\""
    parts += [Spacer(1, 2), _p(source, QUOTE)]
    return KeepTogether(parts)


def blank_ecrf(name: str, version: int, locked_at: str, draft: DraftECRF) -> bytes:
    """The locked form. Each visit starts a new page. A visit with more fields
    than fit carries on to the next."""
    visits: dict[str, list] = {}
    for form in draft.forms:
        visits.setdefault(form.visit, []).append(form)
    story: list = []
    for visit, forms in visits.items():
        story.append(_p(visit, H1))
        for form in forms:
            if form.form != visit:
                story.append(_p(form.form, H2))
            story += [_field_block(f) for f in form.fields if f.collected]
        story.append(PageBreak())
    story.pop()
    return _build(f"Blank eCRF: {name}", f"{name} · version {version} · locked {locked_at}", story)


def casebook(name: str, version: int | None, subject: str, site: str, generated: str, visits: list[dict]) -> bytes:
    """Everything on file for one subject. Each visit dict holds rows (field,
    repeat, value, unit, status, completion, changes, queries), open_queries
    (their text) and signoff (who, when, undone) or None."""
    story: list = [_p(f"Casebook: {subject}", H1),
                   _p(f"{name}, form version {version}. Site {site}. Generated {generated}. Synthetic data only.", META),
                   Spacer(1, 6)]
    widths = [1.8, 0.4, 1.4, 0.6, 0.85, 0.75, 0.6, 0.6]
    head = ["Field", "Rep.", "Value", "Unit", "Status", "Answer", "Edits", "Open"]
    for visit in visits:
        story.append(_p(visit["visit"], H2))
        if visit["rows"]:
            rows = [[_p(h, CELL_HEAD) for h in head]]
            for r in visit["rows"]:
                rows.append([_p(x if x is not None else "", CELL) for x in (
                    r["field"], r["repeat"], r["value"], r["unit"], r["status"], r["completion"], r["changes"], r["queries"])])
            table = Table(rows, colWidths=[w * inch for w in widths], repeatRows=1)
            table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), SHADE),
                                       ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINE),
                                       ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story.append(table)
        else:
            story.append(_p("Nothing entered.", META))
        for text in visit["open_queries"]:
            story.append(_p(f"Open query: {text}", META))
        sg = visit["signoff"]
        line = "Investigator sign-off: not signed."
        if sg:
            line = f"Investigator sign-off: signed by {sg['who']} on {sg['when']}. \"{sg['meaning']}\""
        story += [Spacer(1, 3), _p(line, BODY)]
        for undone in visit.get("undone", []):
            story.append(_p(f"An earlier sign-off by {undone['who']} on {undone['when']} was undone by a later change.", META))
    return _build(f"Casebook {subject}", f"{name} · {subject} · {site}", story)
