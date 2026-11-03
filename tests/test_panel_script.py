"""The page's JavaScript parses (node --check): its strings are edited by hand, inside object literals, and neither
suite loads the page (3 Nov 2026 review)."""
import os
import shutil
import subprocess

import pytest

PANEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "custom_components", "printer_panel", "www", "printer-panel.js")


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_panel_script_parses():
    r = subprocess.run(["node", "--check", PANEL], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
