"""Printer Panel: a Printer page in Home Assistant's sidebar for a Creality printer, built on the Creality integration
(ha_creality_ws): the live camera, the print's name, progress, time left and finish time, temperatures and their targets,
the CFS's colours, speed and fans, the light, and Pause, Resume and Stop; and phone notifications when a print finishes,
pauses, runs out of filament or stops with an error. The same view is a card (custom:printer-panel-card). Through the
printer's Moonraker, two entities of its own on the printer: Restart printer, and Pause at G-code line."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import DOMAIN, PANEL_ELEMENT, PANEL_FILE, PANEL_PATH, SIDEBAR_ICON, URL_BASE
from .linepause import STORE_VERSION
from .link import PrinterLink

WWW = Path(__file__).parent / "www"
PLATFORMS = [Platform.BUTTON, Platform.NUMBER]
_STATIC = f"{DOMAIN}_static"
_SCRIPT_URL = f"{DOMAIN}_script_url"


def _hash() -> str:
    try:
        return hashlib.sha256((WWW / PANEL_FILE).read_bytes()).hexdigest()[:10]
    except OSError:
        return "0"


async def _script_url(hass: HomeAssistant) -> str:
    """The page's script with the version and a hash of the file, so a changed script is never served from a cache."""
    if url := hass.data.get(_SCRIPT_URL):
        return url
    integration = await async_get_integration(hass, DOMAIN)
    url = f"{URL_BASE}/{PANEL_FILE}?v={integration.version}-{await hass.async_add_executor_job(_hash)}"
    hass.data[_SCRIPT_URL] = url
    return url


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the script once per run; load it on every page, so the card and the Creality icon in the sidebar are there
    from the start; and answer the page's question about its printer."""
    if not hass.data.get(_STATIC):
        await hass.http.async_register_static_paths([StaticPathConfig(URL_BASE, str(WWW), cache_headers=False)])
        hass.data[_STATIC] = True
        websocket_api.async_register_command(hass, ws_config)
        websocket_api.async_register_command(hass, ws_position)
    frontend.add_extra_js_url(hass, await _script_url(hass))
    return True


def _path(hass: HomeAssistant, entry: ConfigEntry) -> str:
    """/printer for the first printer, /printer-2 and on for more."""
    ids = [e.entry_id for e in hass.config_entries.async_entries(DOMAIN)]
    index = ids.index(entry.entry_id) if entry.entry_id in ids else 0
    return PANEL_PATH if index == 0 else f"{PANEL_PATH}-{index + 1}"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    link = PrinterLink(hass, entry, _path(hass, entry))
    entry.runtime_data = link
    # a set-up retried after a failure half way would find its own panel and be refused: clear it first
    frontend.async_remove_panel(hass, link.path, warn_if_unknown=False)
    await panel_custom.async_register_panel(
        hass, frontend_url_path=link.path, webcomponent_name=PANEL_ELEMENT, module_url=await _script_url(hass),
        sidebar_title=link.title, sidebar_icon=SIDEBAR_ICON, config={"entry_id": entry.entry_id}, require_admin=False)
    await link.line_pause.async_load()  # before the entities, so Pause at G-code line starts with the line kept
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(link.async_start())
    entry.async_on_unload(entry.add_update_listener(_options_changed))
    return True


async def _options_changed(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """The printer's entry is deleted: its pause at a line goes with it."""
    await Store(hass, STORE_VERSION, f"{DOMAIN}.{entry.entry_id}.line_pause").async_remove()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    frontend.async_remove_panel(hass, entry.runtime_data.path)
    return True


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/config", vol.Optional("entry_id"): str})
@callback
def ws_config(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """The printer a page or card shows: the entry it names, else the first."""
    wanted = msg.get("entry_id")
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    entry = next((e for e in entries if not wanted or e.entry_id == wanted), None)
    if entry is None:
        connection.send_error(msg["id"], "not_found", "No printer is set up in Printer Panel")
        return
    connection.send_result(msg["id"], entry.runtime_data.describe())


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/position", vol.Optional("entry_id"): str})
@websocket_api.async_response
async def ws_position(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Where the printer is in the file it is printing, for the page: the line, of how many, the line it will pause at
    and in about how long. From the printer's Moonraker; available false when it cannot be reached."""
    wanted = msg.get("entry_id")
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    entry = next((e for e in entries if not wanted or e.entry_id == wanted), None)
    if entry is None:
        connection.send_error(msg["id"], "not_found", "No printer is set up in Printer Panel")
        return
    connection.send_result(msg["id"], await entry.runtime_data.line_pause.position())
