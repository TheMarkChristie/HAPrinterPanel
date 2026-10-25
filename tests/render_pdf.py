"""Draw the filament register's PDF and turn its pages into pictures to look at (needs PyMuPDF): 40 spools in
English, which goes over two pages, and the small register in Norwegian. PyMuPDF opening it is a second reader's word
that the file is sound.

    python tests/render_pdf.py   -> tests/render_pdf_en_1.png, render_pdf_en_2.png, render_pdf_nb_1.png
"""
import os
import sys
from datetime import datetime

import pymupdf as fitz

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_pdf import book  # noqa: E402

from custom_components.printer_panel.pdf import register_pdf  # noqa: E402

MADE = datetime(2026, 10, 25, 20, 15)

for lang, spools in (("en", 40), ("nb", 3)):
    pdf = register_pdf(book(spools), "K2Plus-235D & CFS", lang, MADE)
    doc = fitz.open(stream=pdf, filetype="pdf")
    print(f"{lang}: {len(pdf):,} bytes, {doc.page_count} page(s); first lines: {doc[0].get_text().splitlines()[:4]}")
    for i, page in enumerate(doc, start=1):
        png = os.path.join(HERE, f"render_pdf_{lang}_{i}.png")
        page.get_pixmap(dpi=110).save(png)
        print("  ", png)
