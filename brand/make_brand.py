"""Fetch the Printer Panel icon and logo for HACS and the integrations page (custom_components/printer_panel/brand/).

Printer Panel uses Creality's own mark, as Home Assistant shows it for the Creality integration (ha_creality_ws) on
brands.home-assistant.io. Creality and the Creality logo are trademarks of Shenzhen Creality 3D Technology Co., Ltd.;
the mark is used only to name the printers this works with. The sidebar item draws the same mark from one SVG path
(MARK in www/printer-panel.js), in the sidebar's own colour.

    python brand/make_brand.py
"""
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "custom_components", "printer_panel", "brand")
SOURCE = "https://brands.home-assistant.io/ha_creality_ws/"
FILES = ["icon.png", "icon@2x.png", "logo.png", "logo@2x.png", "dark_icon.png", "dark_icon@2x.png", "dark_logo.png", "dark_logo@2x.png"]


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    for name in FILES:
        request = urllib.request.Request(SOURCE + name, headers={"User-Agent": "printer-panel-brand"})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
        if not data.startswith(b"\x89PNG"):
            raise SystemExit(f"{name}: not a PNG")
        with open(os.path.join(OUT, name), "wb") as f:
            f.write(data)
        print(f"{name}: {len(data)} bytes")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
