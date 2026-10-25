"""The filament register's PDF, without Home Assistant: python -m pytest tests -q

Checked as a file (every object where the cross-reference table says, the pages counted) and for its words in the
inflated pages; it is drawn by hand, so tests/render_pdf.py turns it into pictures to look at."""
import re
import zlib
from datetime import datetime

import _load  # noqa: F401
from custom_components.printer_panel import filament as f
from custom_components.printer_panel.pdf import register_pdf, text_width

MADE = datetime(2026, 10, 25, 20, 15)
DAY = "2026-10-25"


def book(spools: int = 3) -> dict:
    r = f.Register()
    r.today = lambda: DAY
    r.check_in("Creality", "Purple", "#9e007e", "Hyper PLA", 1000, "2026-10-01")
    r.check_in("Sunlu", "Black", "#000000", "PLA", 1000, "2026-10-02")
    r.check_in("eSun", "Pink", "#ff37af", "PLA+", 1000, "2026-10-03")
    for i in range(4, spools + 1):
        r.check_in("Polymaker", f"Colour {i}", "#2f6f7a", "PETG", 750, "2026-10-04")
    r.slots["1D"] = {"key": "k", "stock": "F001", "how": "auto"}
    r.update("F003", {"left": 64})
    r.update("F002", {"left": 0})
    r.check_in("Elegoo", "White", "#ffffff", "PLA", 1000, "2026-09-01")
    r.remove(f"F{r.next - 1:03d}")
    return r.to_dict()


def made(data: dict, printer: str = "K2Plus-235D & CFS", lang: str = "en") -> tuple[int, bytes, int]:
    """The PDF checked as a file: (its pages, the pages' drawing operators inflated, its size). The file holds together:
    the header, every object at its offset, each stream its stated length, startxref at the table."""
    pdf = register_pdf(data, printer, lang, MADE)
    assert pdf.startswith(b"%PDF-1.4\n") and pdf.rstrip().endswith(b"%%EOF")
    start = int(re.search(rb"startxref\n(\d+)\n", pdf).group(1))
    assert pdf[start:start + 4] == b"xref"
    count = int(re.search(rb"xref\n0 (\d+)\n", pdf).group(1))
    rows = re.findall(rb"(\d{10}) 00000 n ", pdf[start:])
    assert len(rows) == count - 1
    for n, offset in enumerate(rows, start=1):
        assert pdf[int(offset):].startswith(b"%d 0 obj\n" % n), n
    pages = []
    for m in re.finditer(rb"<< /Length (\d+) /Filter /FlateDecode >>\nstream\n", pdf):
        body = pdf[m.end():m.end() + int(m.group(1))]
        assert pdf[m.end() + len(body):].startswith(b"\nendstream")
        pages.append(zlib.decompress(body))
    count = int(re.search(rb"/Type /Pages /Kids \[[^\]]*\] /Count (\d+)", pdf).group(1))
    assert count == len(pages)
    return count, b"\n".join(pages), len(pdf)


def test_the_pdf_holds_the_spools_in_stock_and_what_has_gone():
    pages, text, _ = made(book())
    assert pages == 1
    for words in (b"(Filament register)", b"K2Plus-235D & CFS \\267 25 October 2026, 20:15", b"(In stock \\(2\\))",
                  b"2 spools in stock, 1.1 kg of filament \\267 1 low \\(10 % or less\\)", b"(F001)", b"(1D)",
                  b"(1 Oct 2026)", b"(1,000)", b"(64)", b"(Gone out of stock in the last 30 days \\(2\\))",
                  b"(Used up)", b"(Removed)", b"(Printer Panel \\267 page 1 of 1)"):
        assert words in text, words
    assert b"(F002) Tj" in text.split(b"Gone out of stock")[1], "used up: under gone, not in stock"


def test_in_norwegian():
    _, text, _ = made(book(), lang="nb")
    for words in (b"(Filamentregister)", b"25. oktober 2026 kl. 20:15", b"(P\\345 lager \\(2\\))", b"(1 000)",
                  b"1,1 kg filament", b"(Brukt opp)", b"(Fjernet)", b"(1. okt 2026)", b"(Printer Panel \\267 side 1 av 1)"):
        assert words in text, words


def test_forty_spools_go_over_two_pages_with_the_headings_again():
    pages, text, _ = made(book(40))
    assert pages == 2
    assert text.count(b"(Checked in)") == 3, "the stock table's headings on both pages, and the gone table's"
    assert b"(Printer Panel \\267 page 2 of 2)" in text


def test_hundreds_of_spools_stay_a_small_file():
    pages, _, size = made(book(500))
    assert pages > 10 and size < 200_000, (pages, size)


def test_an_empty_register():
    pages, text, _ = made({})
    assert pages == 1
    assert b"(No spools in stock.)" in text and b"(Nothing has gone out of stock in the last 30 days.)" in text


def test_long_names_are_cut_to_their_column_and_brackets_kept():
    data = f.Register()
    data.check_in("A very long brand name (imported) that goes on", "Teal", "#2f6f7a", "PLA", 1000, DAY)
    _, text, _ = made(data.to_dict(), printer="K2 (garage)")
    cut = re.search(rb"\((A very long[^)]*?)\) Tj", text.replace(b"\\(", b"[").replace(b"\\)", b"]"))
    assert cut and cut.group(1).endswith(b"\\205"), "cut, with an ellipsis"
    assert b"K2 \\(garage\\)" in text
    assert 22 < text_width("F001", 9.5, bold=True) < 25


def test_what_the_spools_with_a_price_are_worth():
    r = f.Register()
    r.check_in("Sunlu", "Black", "#000000", "PLA", 1000, DAY, price=199)
    r.check_in("eSun", "Pink", "#ff37af", "PLA", 750, DAY, price=150)
    r.check_in("Polymaker", "Grey", "#808080", "PLA", 1000, DAY)
    r.update("F002", {"left": 375})
    pdf = register_pdf(r.to_dict(), "K2", "en", MADE, "NOK")
    assert b"2.4 kg of filament, worth 274.00 kr" in made_text(pdf)
    assert b"verdt 274,00 kr" in made_text(register_pdf(r.to_dict(), "K2", "nb", MADE, "NOK"))
    assert b"worth" not in made_text(register_pdf(book(), "K2", "en", MADE, "NOK")), "no prices: no worth"


def made_text(pdf: bytes) -> bytes:
    return b"\n".join(zlib.decompress(s) for s in re.findall(rb"/FlateDecode >>\nstream\n(.*?)\nendstream", pdf, re.S))
