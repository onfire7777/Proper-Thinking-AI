import logging
import re
from html import escape

from PyQt6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PyQt6.QtGui import QFont, QPageLayout, QPainter, QTextDocument
from PyQt6.QtPrintSupport import QPrinter

log = logging.getLogger(__name__)

_FOOTER_PT = 22.0
_FOOTER_FONT_PT = 9.5
_PDF_EPISTEMIC_PT = 10


def _darken_print_colors(html: str) -> str:
    h = html
    h = h.replace("color:#444444", "color:#000000")
    h = h.replace("color: #444444", "color: #000000")
    h = h.replace("color:#555555", "color:#222222")
    h = h.replace("color: #555555", "color: #222222")
    h = h.replace("color:#424242", "color:#1a1a1a")
    h = h.replace("color: #424242", "color: #1a1a1a")
    return h


def _h2_sections_to_paragraphs(html: str) -> str:
    def repl(m) -> str:
        inner = m.group(1)
        return (
            '<p class="fw-section-main" style="margin:10pt 0 5pt 0;font-size:15pt;font-weight:bold;'
            'color:#111111;">'
            f"{inner}</p>"
        )

    return re.sub(
        r'<h2\s+class="fw-section-main"[^>]*>(.*?)</h2>',
        repl,
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )


def _force_table_cells_pdf_font_pt(html: str, pt: float = 10.0) -> str:
    """Override th/td inline font-size so print tables stay 12pt (inline px→pt can look oversized)."""
    fs_re = re.compile(r"font-size\s*:\s*[^;]+;?", re.I)

    def patch(m: re.Match) -> str:
        sty = fs_re.sub(f"font-size:{pt}pt;", m.group(2))
        return m.group(1) + sty + m.group(3)

    out = html
    for tag in ("th", "td"):
        out = re.sub(rf'(<{tag}\s+style=")([^"]*)(")', patch, out, flags=re.I)
    return out


def _force_epistemic_pdf_font_pt(html: str) -> str:
    """Override epistemic inline sizes after global px→pt so UI can use larger px than print."""
    pt = _PDF_EPISTEMIC_PT
    fs_re = re.compile(r"font-size\s*:\s*[^;]+;?", re.I)

    def patch(m: re.Match) -> str:
        sty = fs_re.sub(f"font-size:{pt}pt;", m.group(2))
        return m.group(1) + sty + m.group(3)

    out = html
    for cls in ("fw-epistemic-inner", "fw-epistemic"):
        out = re.sub(rf'(<div class="{cls}" style=")([^"]*)(")', patch, out)
    out = re.sub(
        r'(<span class="fw-epistemic-txt" style=")([^"]*)(")',
        patch,
        out,
    )
    return out


def prepare_framework_body_html(body_html: str) -> str:
    s = body_html
    s = re.sub(
        r'(<p class="fw-body" style=")([^"]*?)font-size:\s*13px([^"]*")',
        r"\1\2font-size:12px\3",
        s,
    )
    s = re.sub(
        r'(<li class="fw-li" style=")([^"]*?)font-size:\s*13px([^"]*")',
        r"\1\2font-size:12px\3",
        s,
    )
    s = re.sub(
        r'(<p class="fw-subhead-kind"[^>]*>\s*<span style=")([^"]*?)font-size:\s*16px([^"]*")',
        r"\1\2font-size:14px\3",
        s,
    )
    # Smaller print sizes than on-screen px→pt 1:1 (less “zoomed” PDF).
    # Epistemic uses _FW_EPISTEMIC_FONT (10px) → 10pt here; no separate epistemic regex.
    for px, pt in (
        ("16", "14"),
        ("15", "13"),
        ("14", "12"),
        ("13", "11"),
        ("12", "10.5"),
        ("11", "10"),
        ("10", "9.5"),
    ):
        s = s.replace(f"font-size:{px}px", f"font-size:{pt}pt")
    s = s.replace("margin:0 0 8px 20px;", "margin:0 0 4px 20px;")
    s = s.replace("margin-bottom:4px; font-size:13px;", "margin-bottom:2px; font-size:11pt;")
    s = _force_epistemic_pdf_font_pt(s)
    s = _force_table_cells_pdf_font_pt(s)
    s = _h2_sections_to_paragraphs(s)
    s = _darken_print_colors(s)
    return s


def _wrap_print_html(document_title: str, body_inner: str) -> str:
    title = escape(document_title or "Framework")
    title_p = (
        f'<p style="text-align:center;font-size:13pt;font-weight:bold;margin:0 0 12pt 0;'
        f'color:#111111;">{title}</p>'
    )
    css = (
        "body{font-family:'Times New Roman','DejaVu Serif',serif;line-height:1.42;"
        "margin:0;padding:12pt 22pt 12pt 22pt;}"
        "p{margin:2pt 0 4pt 0;}"
        "ul{margin:0 0 4pt 20pt;padding:0;}"
        "li{margin:0 0 2pt 0;}"
        "table{border-collapse:collapse;width:100%;margin:6pt 0 12pt 0;}"
        "th,td{border:1px solid #777;padding:3pt;font-size:10pt;vertical-align:top;color:#000;}"
        "th{font-weight:bold;background:#f2f2f2;}"
        ".fw-subhead-3{font-size:11.5pt;font-weight:bold;color:#000;}"
        "div.fw-epistemic,div.fw-epistemic-inner{font-size:10pt;}"
        "div.fw-epistemic b,div.fw-epistemic-inner b,div.fw-epistemic i,div.fw-epistemic-inner i{font-size:10pt;}"
    )
    return (
        "<html><head><meta charset='utf-8'/><style>"
        + css
        + "</style></head><body>"
        + title_p
        + body_inner
        + "</body></html>"
    )


def _print_with_page_footer(doc: QTextDocument, printer: QPrinter) -> None:
    """
    QTextDocument layout uses logical units (points when page size is set in points).
    QPainter on QPrinter uses device pixels (HighResolution). We must scale or the
    layout is drawn at ~1 pixel per point — tiny content in the corner.
    """
    source = printer.pageRect(QPrinter.Unit.Point)
    target = printer.pageRect(QPrinter.Unit.DevicePixel)
    sw, sh = float(source.width()), float(source.height())
    tw, th = float(target.width()), float(target.height())
    if sw <= 0 or sh <= 0 or tw <= 0 or th <= 0:
        log.warning("PDF: invalid page rect; using plain print")
        doc.print(printer)
        return

    sx = tw / sw
    sy = th / sh
    content_h = max(72.0, sh - _FOOTER_PT)
    doc.setPageSize(QSizeF(sw, content_h))
    n = max(1, doc.pageCount())

    painter = QPainter()
    if not painter.begin(printer):
        log.warning("PDF: QPainter.begin failed; using plain print")
        doc.print(printer)
        return
    try:
        sl, st = float(source.left()), float(source.top())
        tl, tt = float(target.left()), float(target.top())

        for i in range(n):
            if i > 0:
                printer.newPage()
            top = i * content_h
            clip = QRectF(0.0, top, sw, content_h)
            painter.save()
            painter.translate(tl, tt)
            painter.scale(sx, sy)
            painter.translate(-sl, -st)
            painter.translate(0.0, -top)
            doc.drawContents(painter, clip)
            painter.restore()

            foot_top = tt + sy * content_h
            foot_text = f"Page {i + 1} of {n}"
            ff = QFont("Times New Roman")
            ff.setPointSizeF(float(_FOOTER_FONT_PT))
            painter.setFont(ff)
            fm = painter.fontMetrics()
            text_w = float(fm.horizontalAdvance(foot_text))
            x = tl + max(0.0, (tw - text_w) / 2.0)
            y = foot_top + float(fm.ascent())
            painter.drawText(int(round(x)), int(round(y)), foot_text)
    finally:
        painter.end()


def export_framework_to_pdf_file(name: str, body_html: str, path: str) -> None:
    safe = (name or "Framework").strip() or "Framework"
    log.info("PDF export: name=%s path=%s bytes=%s", safe, path, len(body_html or ""))

    inner = prepare_framework_body_html(body_html or "")
    html = _wrap_print_html(safe, inner)

    doc = QTextDocument()
    doc.setDocumentMargin(0.0)
    doc.setHtml(html)

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(path)
    try:
        printer.setPageMargins(
            QMarginsF(11.0, 12.0, 11.0, 14.0),
            QPageLayout.Unit.Millimeter,
        )
    except (TypeError, AttributeError):
        log.debug("PDF: setPageMargins not applied (API mismatch)")

    _print_with_page_footer(doc, printer)
    log.info("PDF export done: %s", path)
