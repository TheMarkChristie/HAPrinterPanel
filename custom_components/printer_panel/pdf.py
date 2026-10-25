"""The filament register as a PDF, with no Home Assistant and no libraries in it (tested on its own). Mark, 25 Oct 2026:
"a button that downloads a pdf with the list and what has gone out of stock recently".

One A4 document: the spools in stock (number, colour, brand, colour name, type, slot, checked in, grams left of the
label's weight, low at 10 % or less), then what has gone out of stock in the last 30 days (used up or removed), in
English or Norwegian. Written by hand in PDF's own operators with the two Helvetica faces every reader has, so the
integration needs nothing installed for it.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .filament import RECENT_DAYS, REMOVED, Register, colour_hex

W, H = 595.28, 841.89           # A4, in points
LEFT, RIGHT, TOP, BOTTOM = 40.0, 555.0, 800.0, 56.0
ROW = 17.0
INK, GREY, RULE, LOW = (0.1, 0.1, 0.1), (0.42, 0.42, 0.42), (0.85, 0.85, 0.85), (0.8, 0.45, 0.0)

# Helvetica's widths (1/1000 of the size) from its AFM, space to tilde; the bold face is about 6 % wider
_WIDTHS = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556,
           556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667,
           556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556,
           556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722,
           500, 500, 500, 334, 260, 334, 584]

TEXT = {
    "en": {
        "title": "Filament register", "in_stock": "In stock ({n})", "none_in": "No spools in stock.",
        "gone": "Gone out of stock in the last {days} days ({n})", "none_gone": "Nothing has gone out of stock in the last {days} days.",
        "summary": "{n} spools in stock, {kg} kg of filament", "low": "{n} low (10 % or less)",
        "stock_cols": ("No.", "Brand", "Colour", "Type", "Where", "Checked in", "Left (g)", "Of (g)"),
        "gone_cols": ("No.", "Brand", "Colour", "Type", "Weight (g)", "Checked in", "Out", "Why"),
        "why": {"used_up": "Used up", "removed": "Removed"}, "ext": "Ext",
        "footer": "Printer Panel · page {p} of {n}",
        "months": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                   "November", "December"),
        "made": "{d} {month} {y}, {hm}", "day": "{d} {mon} {y}", "thousands": ",", "point": ".",
    },
    "nb": {
        "title": "Filamentregister", "in_stock": "På lager ({n})", "none_in": "Ingen spoler på lager.",
        "gone": "Gått ut av lager de siste {days} dagene ({n})",
        "none_gone": "Ingenting har gått ut av lager de siste {days} dagene.",
        "summary": "{n} spoler på lager, {kg} kg filament", "low": "{n} med lite igjen (10 % eller mindre)",
        "stock_cols": ("Nr.", "Merke", "Farge", "Type", "Hvor", "Sjekket inn", "Igjen (g)", "Av (g)"),
        "gone_cols": ("Nr.", "Merke", "Farge", "Type", "Vekt (g)", "Sjekket inn", "Ut", "Hvorfor"),
        "why": {"used_up": "Brukt opp", "removed": "Fjernet"}, "ext": "Ekst.",
        "footer": "Printer Panel · side {p} av {n}",
        "months": ("januar", "februar", "mars", "april", "mai", "juni", "juli", "august", "september", "oktober",
                   "november", "desember"),
        "made": "{d}. {month} {y} kl. {hm}", "day": "{d}. {mon} {y}", "thousands": " ", "point": ",",
    },
}


def text_width(text: str, size: float, bold: bool = False) -> float:
    w = sum(_WIDTHS[ord(c) - 32] if 32 <= ord(c) <= 126 else 556 for c in text)
    return w * size / 1000.0 * (1.06 if bold else 1.0)


def _fit(text: str, width: float, size: float, bold: bool = False) -> str:
    """The text, cut with an ellipsis to fit the width."""
    if text_width(text, size, bold) <= width:
        return text
    while text and text_width(text + "…", size, bold) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _pdf_string(text: str) -> bytes:
    """A PDF literal string in WinAnsi (cp1252), so Norwegian letters, the middle dot and the ellipsis come out."""
    out = bytearray(b"(")
    for b in text.encode("cp1252", errors="replace"):
        if b in (0x28, 0x29, 0x5C):
            out += b"\\" + bytes([b])
        elif 32 <= b <= 126:
            out.append(b)
        else:
            out += b"\\%03o" % b
    return bytes(out + b")")


def _n(v: float, t: dict[str, Any], digits: int = 0) -> str:
    text = f"{v:,.{digits}f}"
    return text.replace(",", "\0").replace(".", t["point"]).replace("\0", t["thousands"])


def _day(iso: str | None, t: dict[str, Any]) -> str:
    try:
        d = date.fromisoformat(str(iso))
    except ValueError:
        return ""
    return t["day"].format(d=d.day, mon=t["months"][d.month - 1][:3], y=d.year)


class _Doc:
    """Pages of PDF drawing operators, the place on the page going down."""

    def __init__(self) -> None:
        self.pages: list[list[bytes]] = []
        self.new_page()

    def new_page(self) -> None:
        self.ops: list[bytes] = []
        self.pages.append(self.ops)
        self.y = TOP

    def text(self, x: float, y: float, text: str, size: float = 9.5, bold: bool = False, rgb=INK, right: bool = False,
             width: float | None = None) -> None:
        if width is not None:
            text = _fit(text, width, size, bold)
        if right:
            x -= text_width(text, size, bold)
        self.ops.append(b"BT /%s %.1f Tf %.3f %.3f %.3f rg %.2f %.2f Td %s Tj ET"
                        % (b"F2" if bold else b"F1", size, *rgb, x, y, _pdf_string(text)))

    def swatch(self, x: float, y: float, hex_: str | None) -> None:
        c = colour_hex(hex_) or "#808080"
        r, g, b = (int(c[i:i + 2], 16) / 255 for i in (1, 3, 5))
        self.ops.append(b"%.3f %.3f %.3f rg 0.6 G 0.5 w %.2f %.2f 10 10 re B" % (r, g, b, x, y))

    def rule(self, y: float, rgb=RULE, width: float = 0.5) -> None:
        self.ops.append(b"%.3f %.3f %.3f RG %.2f w %.2f %.2f m %.2f %.2f l S" % (*rgb, width, LEFT, y, RIGHT, y))

    def room(self, height: float, heading) -> None:
        """A new page when this much will not fit, with the table's headings again."""
        if self.y - height < BOTTOM:
            self.new_page()
            heading()

    def to_bytes(self, title: str, made: datetime, footer: str) -> bytes:
        n = len(self.pages)
        for p, ops in enumerate(self.pages, start=1):
            t_footer = footer.format(p=p, n=n)
            ops.append(b"BT /F1 8 Tf %.3f %.3f %.3f rg %.2f 32 Td %s Tj ET"
                       % (*GREY, RIGHT - text_width(t_footer, 8), _pdf_string(t_footer)))
        objects: list[bytes] = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"",                                                  # the page tree, once the pages are numbered
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
            b"<< /Title %s /Producer (Printer Panel) /CreationDate (D:%s) >>" % (_pdf_string(title), made.strftime("%Y%m%d%H%M%S").encode()),
        ]
        kids = []
        for ops in self.pages:
            stream = b"\n".join(ops)
            objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
            objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                           b"/Contents %d 0 R >>" % (W, H, len(objects)))
            kids.append(len(objects))
        objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(b"%d 0 R" % k for k in kids), len(kids))
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += b"%d 0 obj\n%s\nendobj\n" % (i, body)
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
        out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
        out += b"trailer\n<< /Size %d /Root 1 0 R /Info 5 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
        return bytes(out)


def register_pdf(data: dict[str, Any], printer: str, lang: str, made: datetime) -> bytes:
    """The register (as stored) as a PDF: printer is the printer's name for the heading, made the time it was made."""
    t = TEXT["nb" if lang == "nb" else "en"]
    book = Register(data)
    book.today = lambda: made.date().isoformat()
    doc = _Doc()
    in_stock = sorted((s for s in book.spools if s["left"] > 0), key=lambda s: s["stock"])
    low = [s for s in in_stock if s["weight"] > 0 and s["left"] / s["weight"] <= 0.1]
    gone = book.gone_since(RECENT_DAYS)

    doc.text(LEFT, doc.y, t["title"], size=20, bold=True)
    doc.y -= 18
    doc.text(LEFT, doc.y, f"{printer} · " + t["made"].format(d=made.day, month=t["months"][made.month - 1], y=made.year,
                                                              hm=made.strftime("%H:%M")), size=10, rgb=GREY)
    doc.y -= 15
    summary = t["summary"].format(n=len(in_stock), kg=_n(sum(s["left"] for s in in_stock) / 1000, t, 1))
    doc.text(LEFT, doc.y, summary + (f" · {t['low'].format(n=len(low))}" if low else ""), size=10)
    doc.y -= 30

    # the spools in stock: No. | swatch | brand | colour | type | where | checked in | left | of
    stock_x = (LEFT, 98, 196, 279, 374, 412, 515, 555)

    def stock_heading() -> None:
        for i, label in enumerate(t["stock_cols"]):
            doc.text(stock_x[i], doc.y, label, size=8.5, bold=True, rgb=GREY, right=i >= 6)
        doc.y -= 6
        doc.rule(doc.y, rgb=GREY)
        doc.y -= ROW - 4

    doc.text(LEFT, doc.y, t["in_stock"].format(n=len(in_stock)), size=13, bold=True)
    doc.y -= 20
    if in_stock:
        stock_heading()
        for s in in_stock:
            doc.room(ROW, stock_heading)
            short = s["weight"] > 0 and s["left"] / s["weight"] <= 0.1
            where = book.where(s["stock"]) or ""
            doc.text(stock_x[0], doc.y, s["stock"], bold=True)
            doc.swatch(80, doc.y - 1.5, s.get("hex"))
            doc.text(stock_x[1], doc.y, s.get("brand") or "", width=92)
            doc.text(stock_x[2], doc.y, s.get("colour") or "", width=78)
            doc.text(stock_x[3], doc.y, s.get("type") or "", width=90)
            doc.text(stock_x[4], doc.y, t["ext"] if where == "Ext" else where)
            doc.text(stock_x[5], doc.y, _day(s.get("checked_in"), t))
            doc.text(stock_x[6], doc.y, _n(s["left"], t), bold=short, rgb=LOW if short else INK, right=True)
            doc.text(stock_x[7], doc.y, _n(s["weight"], t), rgb=GREY, right=True)
            doc.rule(doc.y - 5.5)
            doc.y -= ROW
    else:
        doc.text(LEFT, doc.y, t["none_in"], rgb=GREY)
        doc.y -= ROW

    # what has gone out of stock lately: No. | swatch | brand | colour | type | weight | checked in | out | why
    gone_x = (LEFT, 98, 182, 252, 362, 372, 432, 498)

    def gone_heading() -> None:
        for i, label in enumerate(t["gone_cols"]):
            doc.text(gone_x[i], doc.y, label, size=8.5, bold=True, rgb=GREY, right=i == 4)
        doc.y -= 6
        doc.rule(doc.y, rgb=GREY)
        doc.y -= ROW - 4

    doc.y -= 16
    doc.room(20 + 2 * ROW, lambda: None)
    doc.text(LEFT, doc.y, t["gone"].format(days=RECENT_DAYS, n=len(gone)), size=13, bold=True)
    doc.y -= 20
    if gone:
        gone_heading()
        for g in gone:
            doc.room(ROW, gone_heading)
            doc.text(gone_x[0], doc.y, g["stock"], bold=True)
            doc.swatch(80, doc.y - 1.5, g.get("hex"))
            doc.text(gone_x[1], doc.y, g.get("brand") or "", width=80)
            doc.text(gone_x[2], doc.y, g.get("colour") or "", width=66)
            doc.text(gone_x[3], doc.y, g.get("type") or "", width=80)
            doc.text(gone_x[4], doc.y, _n(float(g.get("weight") or 0), t), rgb=GREY, right=True)
            doc.text(gone_x[5], doc.y, _day(g.get("checked_in"), t))
            doc.text(gone_x[6], doc.y, _day(g.get("out"), t))
            doc.text(gone_x[7], doc.y, t["why"].get(g.get("why"), ""), rgb=GREY if g.get("why") == REMOVED else INK, width=RIGHT - gone_x[7])
            doc.rule(doc.y - 5.5)
            doc.y -= ROW
    else:
        doc.text(LEFT, doc.y, t["none_gone"].format(days=RECENT_DAYS), rgb=GREY)
    return doc.to_bytes(t["title"], made, t["footer"])
