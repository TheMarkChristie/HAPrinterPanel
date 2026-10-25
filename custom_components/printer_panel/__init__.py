"""Printer Panel: a Printer page in Home Assistant's sidebar for a Creality printer, built on the Creality integration
(ha_creality_ws): the live camera, the print's name, progress, time left and finish time, temperatures and their targets,
the CFS's colours, speed and fans, the light, and Pause, Resume and Stop; and phone notifications when a print finishes,
pauses, runs out of filament or stops with an error. The same view is a card (custom:printer-panel-card). Through the
printer's Moonraker, two entities of its own on the printer: Count G-code lines, and Pause at G-code line. And a
filament register: spools checked in with a stock number, matched to the CFS slots, and what each print used taken
off them, with a PDF of it."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

import voluptuous as vol
from aiohttp import web

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import KEY_HASS, HomeAssistantView, StaticPathConfig
from homeassistant.config_entries import ConfigEntryState
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util

from .const import CONF_EVENTS, DEFAULT_EVENTS, DOMAIN, PANEL_ELEMENT, PANEL_FILE, PANEL_PATH, SIDEBAR_ICON, URL_BASE
from .filament import RegisterError
from .linepause import STORE_VERSION
from .link import PrinterLink
from .pdf import register_pdf
from .register import STORE_VERSION as FILAMENT_STORE_VERSION

WWW = Path(__file__).parent / "www"
PLATFORMS = [Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]
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
        register_commands(hass)
        hass.http.register_view(FilamentPdfView())
    frontend.add_extra_js_url(hass, await _script_url(hass))
    return True


def _path(hass: HomeAssistant, entry: ConfigEntry) -> str:
    """/printer for the first printer, /printer-2 and on for more."""
    ids = [e.entry_id for e in hass.config_entries.async_entries(DOMAIN)]
    index = ids.index(entry.entry_id) if entry.entry_id in ids else 0
    return PANEL_PATH if index == 0 else f"{PANEL_PATH}-{index + 1}"


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """1.2 (0.5.0): the notification when a print takes a spool low, chosen for printers set up before it (Mark asked
    for it)."""
    if entry.version == 1 and entry.minor_version < 2:
        events = list(entry.options[CONF_EVENTS]) if CONF_EVENTS in entry.options else list(DEFAULT_EVENTS)
        if "filament_low" not in events:
            events.append("filament_low")
        hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_EVENTS: events}, minor_version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    link = PrinterLink(hass, entry, _path(hass, entry))
    entry.runtime_data = link
    # a set-up retried after a failure half way would find its own panel and be refused: clear it first
    frontend.async_remove_panel(hass, link.path, warn_if_unknown=False)
    await panel_custom.async_register_panel(
        hass, frontend_url_path=link.path, webcomponent_name=PANEL_ELEMENT, module_url=await _script_url(hass),
        sidebar_title=link.title, sidebar_icon=SIDEBAR_ICON, config={"entry_id": entry.entry_id}, require_admin=False)
    # 0.2.0 and 0.2.1 had a Restart printer button: the K2's firmware cannot reboot through Moonraker (no sudo), so it
    # went in 0.2.2 (Mark: a controlled socket instead); its entity goes with it
    registry = er.async_get(hass)
    if old := registry.async_get_entity_id("button", DOMAIN, f"{link.device_id}_restart_printer"):
        registry.async_remove(old)
    await link.line_pause.async_load()  # before the entities, so Pause at G-code line starts with the line kept
    await link.filament.async_load()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(link.async_start())
    entry.async_on_unload(entry.add_update_listener(_options_changed))
    return True


async def _options_changed(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """The printer's entry is deleted: its pause at a line and its filament register go with it."""
    await Store(hass, STORE_VERSION, f"{DOMAIN}.{entry.entry_id}.line_pause").async_remove()
    await Store(hass, FILAMENT_STORE_VERSION, f"{DOMAIN}.{entry.entry_id}.filament").async_remove()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    frontend.async_remove_panel(hass, entry.runtime_data.path)
    return True


def register_commands(hass: HomeAssistant) -> None:
    """What the page asks Home Assistant: its printer, where the printer is in its file, and the filament register."""
    for command in (ws_config, ws_position, ws_filament_subscribe, ws_filament_check_in, ws_filament_update,
                    ws_filament_remove, ws_filament_confirm, ws_filament_forget, ws_filament_tag):
        websocket_api.async_register_command(hass, command)


def _entry(hass: HomeAssistant, msg: dict[str, Any]) -> ConfigEntry | None:
    """The printer a message names, else the first."""
    wanted = msg.get("entry_id")
    return next((e for e in hass.config_entries.async_loaded_entries(DOMAIN) if not wanted or e.entry_id == wanted), None)


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


# ------------------------------------------------------------------------------------------------ the filament register
_NO_PRINTER = ("not_found", "No printer is set up in Printer Panel")
_WEIGHT = vol.All(vol.Coerce(float), vol.Range(min=0, max=10000))
_PRICE = vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0, max=100000)))


async def _filament_call(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any], work) -> None:
    """Run a change to the register and answer with its result, or the register's reason for saying no."""
    entry = _entry(hass, msg)
    if entry is None:
        connection.send_error(msg["id"], *_NO_PRINTER)
        return
    try:
        result = await work(entry.runtime_data.filament)
    except RegisterError as err:
        code = websocket_api.ERR_NOT_FOUND if err.key == "not_found" else websocket_api.ERR_INVALID_FORMAT
        connection.send_error(msg["id"], code, str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/filament/subscribe", vol.Optional("entry_id"): str})
@callback
def ws_filament_subscribe(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """The register as the page shows it, now and whenever it changes; while a print counts, only its grams so far
    (at most every ten seconds), so a register of hundreds of spools is not sent again and again."""
    entry = _entry(hass, msg)
    if entry is None:
        connection.send_error(msg["id"], *_NO_PRINTER)
        return
    register = entry.runtime_data.filament

    @callback
    def send(full: bool = True) -> None:
        connection.send_message(websocket_api.event_message(msg["id"], register.view(full)))

    connection.subscriptions[msg["id"]] = register.listen(send)
    connection.send_result(msg["id"])
    send()


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/filament/check_in", vol.Optional("entry_id"): str, vol.Required("brand"): str,
    vol.Optional("colour", default=""): str, vol.Optional("hex", default=""): str, vol.Required("material"): str,
    vol.Required("weight"): _WEIGHT, vol.Optional("price"): _PRICE})
@websocket_api.async_response
async def ws_filament_check_in(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """A spool checked in: brand, colour, type, the weight on its label and (if given) its price. Answers with it and
    its stock number."""
    await _filament_call(hass, connection, msg, lambda r: r.check_in(msg["brand"], msg["colour"], msg["hex"],
                                                                     msg["material"], msg["weight"], msg.get("price")))


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/filament/update", vol.Optional("entry_id"): str, vol.Required("stock"): str,
    vol.Optional("brand"): str, vol.Optional("colour"): str, vol.Optional("hex"): str, vol.Optional("material"): str,
    vol.Optional("weight"): _WEIGHT, vol.Optional("left"): _WEIGHT, vol.Optional("price"): _PRICE,
    vol.Optional("weighed"): _WEIGHT, vol.Optional("tare"): _WEIGHT})
@websocket_api.async_response
async def ws_filament_update(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """A spool's details changed, its price, or its grams left: given, or weighed on a scale (weighed) less an empty
    spool of its brand (tare, kept for the brand once given)."""
    fields = {k: msg[k] for k in ("brand", "colour", "hex", "weight", "left", "price", "weighed", "tare") if k in msg}
    if "material" in msg:
        fields["type"] = msg["material"]
    await _filament_call(hass, connection, msg, lambda r: r.update(msg["stock"], fields))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/filament/remove", vol.Optional("entry_id"): str,
                                  vol.Required("stock"): str})
@websocket_api.async_response
async def ws_filament_remove(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """A spool out of the register (used up, or checked in by mistake)."""
    await _filament_call(hass, connection, msg, lambda r: r.remove(msg["stock"]))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/filament/confirm", vol.Optional("entry_id"): str,
                                  vol.Required("slot"): str, vol.Required("stock"): vol.Any(str, None)})
@websocket_api.async_response
async def ws_filament_confirm(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """The stock number on the spool in a slot, before a print or after it (empty clears it). Answers with the grams
    that came off it."""
    async def work(register):
        return {"booked": round(await register.confirm(msg["slot"], msg["stock"]), 1)}

    await _filament_call(hass, connection, msg, work)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/filament/forget", vol.Optional("entry_id"): str,
                                  vol.Required("slot"): str})
@websocket_api.async_response
async def ws_filament_forget(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """What waits on a slot for a stock number came from a spool not in the register: drop it. Answers with the grams."""
    async def work(register):
        return {"dropped": round(await register.forget(msg["slot"]), 1)}

    await _filament_call(hass, connection, msg, work)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/filament/tag", vol.Optional("entry_id"): str,
                                  vol.Required("stock"): str})
@websocket_api.async_response
async def ws_filament_tag(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """What to write on a spool's NFC tag with a phone app: the material, the weight a tag can say, and the tag's own
    colour (the spool's, a few shades off, so the CFS tells the spool from any other)."""
    await _filament_call(hass, connection, msg, lambda r: r.tag(msg["stock"]))


class FilamentPdfView(HomeAssistantView):
    """The filament register as a PDF to download: the spools in stock and what has gone out of stock in the last 30
    days, in English or Norwegian (nb). The page asks Home Assistant to sign the path, as its own downloads do, so the
    phone app's browser can fetch it."""

    url = "/api/printer_panel/{entry_id}/filament/{lang}.pdf"
    name = "api:printer_panel:filament_pdf"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str, lang: str) -> web.Response:
        hass = request.app[KEY_HASS]
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
            return web.Response(status=404, text="No such printer in Printer Panel")
        link = entry.runtime_data
        device = link.describe().get("name") or entry.title
        made = dt_util.now()
        data = copy.deepcopy(link.filament.book.to_dict())   # a print may change the register while the PDF is drawn
        body = await hass.async_add_executor_job(register_pdf, data, device, lang, made, hass.config.currency)
        return web.Response(body=body, content_type="application/pdf",
                            headers={"Content-Disposition": f'attachment; filename="filament-{made.date().isoformat()}.pdf"'})
