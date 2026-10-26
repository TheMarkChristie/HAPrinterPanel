"""Printer Panel against a real Home Assistant (pytest-homeassistant-custom-component). Run from the repository root,
with a Python that has the harness installed:

    python -m pytest -c tests_ha/pytest.ini tests_ha -q

The harness does not install Home Assistant's frontend, so the integration is set up without its dependencies, and its
async_setup (which serves the script and adds it to every page) is replaced by one that only registers the websocket
command. A Creality printer is stood in for by registry entries copied from the Norway K2 Plus (tests/fixtures)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# import this repository's custom_components now: the harness's test Home Assistant later puts its own testing_config
# (a custom_components package of its own) first on the path, and whichever is imported first is the one used
import custom_components.printer_panel  # noqa: E402,F401

if sys.platform == "win32":
    # Home Assistant does not run on Windows; its harness does, almost. asyncio's own loop needs a local socket pair
    # there, which the harness's socket guard refuses. Nothing here goes on the network.
    import pytest_socket

    pytest_socket.disable_socket = lambda *args, **kwargs: None

from homeassistant.core import HomeAssistant, ServiceCall  # noqa: E402
from homeassistant.helpers import device_registry as dr, entity_registry as er  # noqa: E402
from homeassistant.loader import async_get_integration  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

DOMAIN = "printer_panel"
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "k2plus.json").read_text(encoding="utf-8"))


async def _light_setup(hass: HomeAssistant, config: Any) -> bool:
    from custom_components.printer_panel import register_commands

    register_commands(hass)
    return True


@pytest.fixture(autouse=True)
def slots_at_once(monkeypatch):
    """A slot's new reading is acted on at once in these tests (on Norway it must hold a minute first); the test of that
    minute sets it back."""
    from custom_components.printer_panel import register

    monkeypatch.setattr(register, "SLOT_SETTLE", 0)


@pytest.fixture(autouse=True)
async def light_setup(hass: HomeAssistant, enable_custom_integrations: None):
    integration = await async_get_integration(hass, DOMAIN)
    integration.__dict__["dependencies"] = []          # http, frontend, panel_custom, websocket_api: the harness lacks the frontend
    with patch("custom_components.printer_panel.async_setup", _light_setup):
        yield


@pytest.fixture
def phone(hass: HomeAssistant) -> list[dict[str, Any]]:
    """notify.mobile_app_test, recording what it is sent."""
    sent: list[dict[str, Any]] = []

    async def handle(call: ServiceCall) -> None:
        sent.append(dict(call.data))

    hass.services.async_register("notify", "mobile_app_test", handle)
    return sent


@pytest.fixture
def k2plus(hass: HomeAssistant) -> dict[str, str]:
    """The K2 Plus as the Creality integration registers it: its entry (with the printer's address), its device and every
    entity with its key; the states as they were mid-print. Returns translation key -> entity id, and the Creality
    entry's id as creality_entry."""
    source = MockConfigEntry(domain="ha_creality_ws", title="Creality Printer (WS)", data={"host": "192.0.2.60"})
    source.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(config_entry_id=source.entry_id, identifiers={("ha_creality_ws", "k2plus")},
                                                    name="K2Plus-235D", model="K2 Plus")
    entities = er.async_get(hass)
    ids: dict[str, str] = {}
    for e in FIXTURE["registry"]:
        domain, object_id = e["entity_id"].split(".", 1)
        made = entities.async_get_or_create(domain, "ha_creality_ws", e["unique_id"], suggested_object_id=object_id,
                                            config_entry=source, device_id=device.id, translation_key=e.get("translation_key"),
                                            disabled_by=er.RegistryEntryDisabler.USER if e.get("disabled_by") else None)
        ids.setdefault(e.get("translation_key") or e["entity_id"], made.entity_id)
    for s in FIXTURE["states"]:
        hass.states.async_set(s["entity_id"], s["state"], s.get("attributes") or {})
    return {"device_id": device.id, "creality_entry": source.entry_id, **ids}
