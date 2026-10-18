"""Import the integration's pure modules (const, printer) without Home Assistant installed: the package is registered by
hand with its path, so its __init__ (which needs Home Assistant) is never run."""
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "printer_panel"

if "custom_components.printer_panel" not in sys.modules:
    top = types.ModuleType("custom_components")
    top.__path__ = [str(ROOT / "custom_components")]
    pkg = types.ModuleType("custom_components.printer_panel")
    pkg.__path__ = [str(COMPONENT)]
    sys.modules["custom_components"] = top
    sys.modules["custom_components.printer_panel"] = pkg

from custom_components.printer_panel import const, printer  # noqa: E402,F401
