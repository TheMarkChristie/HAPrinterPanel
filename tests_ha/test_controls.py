"""Printer Panel's own controls on the printer, in a real Home Assistant, with the printer's Moonraker stood in for
(aioclient_mock): Restart printer, Pause at G-code line, and what the page is told about where the printer is."""
from __future__ import annotations

from datetime import timedelta
from urllib.parse import quote

import aiohttp
import pytest

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker, AiohttpClientMockResponse

DOMAIN = "printer_panel"
BASE = "http://192.0.2.60:7125"
FILE = "GTA 6 stand - Warden of Bacon_PLA_9h1m52s.gcode"
LINE = 15  # bytes in each line of the stand-in file: b"G1 X0001 Y0001\n"


class Printer:
    """The printer's Moonraker as Printer Panel uses it: where it is in its file, and the file."""

    def __init__(self, mock: AiohttpClientMocker, lines: int = 1000) -> None:
        self.gcode = b"".join(b"G1 X%04d Y%04d\n" % (i, i) for i in range(1, lines + 1))
        self.state, self.file, self.line, self.printing_for = "printing", FILE, 100, 600.0
        self.file_reads = 0
        mock.get(f"{BASE}/printer/objects/query", side_effect=self._query)
        mock.get(f"{BASE}/server/files/gcodes/{quote(FILE)}", side_effect=self._file)

    async def _query(self, method, url, data):
        return AiohttpClientMockResponse(method, url, json={"result": {"status": {
            "virtual_sdcard": {"file_position": self.line * LINE, "file_size": len(self.gcode)},
            "print_stats": {"state": self.state, "filename": self.file, "print_duration": self.printing_for}}}})

    async def _file(self, method, url, data):
        self.file_reads += 1
        return AiohttpClientMockResponse(method, url, response=self.gcode)


async def _add(hass: HomeAssistant, k2plus: dict[str, str]) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="K2Plus-235D", unique_id=k2plus["device_id"], data={"device_id": k2plus["device_id"]},
                            options={"title": "Printer", "notify": ["mobile_app_test"], "events": ["finished", "paused", "runout", "error"]})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _own(hass: HomeAssistant, k2plus: dict[str, str], platform: str, suffix: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{k2plus['device_id']}_{suffix}")
    assert entity_id, f"{platform} {suffix}"
    return entity_id


async def _later(hass: HomeAssistant, seconds: float) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


async def _set_line(hass: HomeAssistant, number: str, line: int) -> None:
    await hass.services.async_call("number", "set_value", {"entity_id": number, "value": line}, blocking=True)
    await hass.async_block_till_done()


async def test_restart_is_a_button_on_the_printer_that_reboots_it(hass: HomeAssistant, k2plus, aioclient_mock) -> None:
    entry = await _add(hass, k2plus)
    restart = _own(hass, k2plus, "button", "restart_printer")
    assert er.async_get(hass).async_get(restart).device_id == k2plus["device_id"]
    assert dr.async_get(hass).async_get(k2plus["device_id"]).config_entry_id == k2plus["creality_entry"] != entry.entry_id, \
        "on the printer's device, which stays the Creality integration's"
    assert hass.states.get(restart).attributes["device_class"] == "restart"
    aioclient_mock.post(f"{BASE}/machine/reboot", json={"result": "ok"})
    await hass.services.async_call("button", "press", {"entity_id": restart}, blocking=True)
    assert [(method.upper(), str(url)) for method, url, *_ in aioclient_mock.mock_calls] == [("POST", f"{BASE}/machine/reboot")]


@pytest.mark.parametrize(("reply", "key", "detail"), [
    ({"status": 500, "json": {"error": {"code": 500, "message": "sudo: not found"}}}, "moonraker_refused", "HTTP 500: sudo: not found"),
    ({"exc": aiohttp.ClientConnectionError("No route to host")}, "moonraker_unreachable", "No route to host"),
    ({"exc": aiohttp.ServerDisconnectedError()}, None, None),  # it went down as it answered: a restart under way
])
async def test_a_restart_the_printer_refuses_is_said(hass: HomeAssistant, k2plus, aioclient_mock, reply, key, detail) -> None:
    await _add(hass, k2plus)
    restart = _own(hass, k2plus, "button", "restart_printer")
    aioclient_mock.post(f"{BASE}/machine/reboot", **reply)
    if key is None:
        await hass.services.async_call("button", "press", {"entity_id": restart}, blocking=True)
        return
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call("button", "press", {"entity_id": restart}, blocking=True)
    assert err.value.translation_key == key and err.value.translation_placeholders == {"detail": detail}


async def test_without_the_printers_address_a_restart_says_so(hass: HomeAssistant, k2plus, aioclient_mock) -> None:
    await _add(hass, k2plus)
    creality = hass.config_entries.async_get_entry(k2plus["creality_entry"])
    hass.config_entries.async_update_entry(creality, data={})
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call("button", "press", {"entity_id": _own(hass, k2plus, "button", "restart_printer")}, blocking=True)
    assert err.value.translation_key == "moonraker_no_host" and not aioclient_mock.mock_calls


async def test_a_pause_at_a_line_pauses_just_after_it_and_says_so(hass: HomeAssistant, k2plus, phone, aioclient_mock) -> None:
    await _add(hass, k2plus)
    printer = Printer(aioclient_mock)
    pressed: list[str] = []

    async def press(call: ServiceCall) -> None:  # stands in for the Creality integration's buttons
        pressed.append(call.data["entity_id"])

    hass.services.async_register("button", "press", press)
    number = _own(hass, k2plus, "number", "pause_at_line")
    await _set_line(hass, number, 500)
    assert hass.states.get(number).state == "500" and printer.file_reads == 1
    printer.line = 499
    await _later(hass, 11)
    assert pressed == [], "one line short"
    printer.line = 503  # it went on while Home Assistant looked away
    await _later(hass, 1)
    assert pressed == [k2plus["pause_print"]]
    assert hass.states.get(number).state == "0", "done: the pause is used up"
    status = k2plus["print_status"]
    hass.states.async_set(status, "paused", {"file": f"/mnt/UDISK/printer_data/gcodes/{FILE}"})
    await hass.async_block_till_done()
    assert [s["message"] for s in phone] == ["GTA 6 stand - Warden of Bacon is paused at line 503, as asked."]
    await _later(hass, 30)
    assert pressed == [k2plus["pause_print"]], "pressed once"


async def test_a_line_printed_already_past_the_end_or_with_nothing_printing_is_refused(hass: HomeAssistant, k2plus, aioclient_mock) -> None:
    await _add(hass, k2plus)
    printer = Printer(aioclient_mock)
    number = _own(hass, k2plus, "number", "pause_at_line")
    for line, key, placeholders in ((100, "line_passed", {"line": "100", "at": "100"}), (1001, "line_beyond", {"line": "1001", "lines": "1000"})):
        with pytest.raises(HomeAssistantError) as err:
            await _set_line(hass, number, line)
        assert (err.value.translation_key, err.value.translation_placeholders) == (key, placeholders)
    printer.state = "standby"
    with pytest.raises(HomeAssistantError) as err:
        await _set_line(hass, number, 500)
    assert err.value.translation_key == "not_printing"
    assert hass.states.get(number).state == "0" and printer.file_reads == 1, "the file is read once"


async def test_a_pause_waits_while_the_print_is_paused_and_goes_when_it_ends(hass: HomeAssistant, k2plus, aioclient_mock, hass_storage) -> None:
    entry = await _add(hass, k2plus)
    printer = Printer(aioclient_mock)
    number = _own(hass, k2plus, "number", "pause_at_line")
    await _set_line(hass, number, 800)
    key = f"{DOMAIN}.{entry.entry_id}.line_pause"
    assert hass_storage[key]["data"] == {"line": 800, "file": FILE}
    printer.state = "paused"
    await _later(hass, 11)
    assert hass.states.get(number).state == "800", "paused by hand before the line: still waiting"
    printer.state = "cancelled"
    await _later(hass, 11)
    assert hass.states.get(number).state == "0" and key not in hass_storage


async def test_a_pause_at_a_line_outlives_a_restart_of_home_assistant(hass: HomeAssistant, k2plus, aioclient_mock) -> None:
    entry = await _add(hass, k2plus)
    printer = Printer(aioclient_mock)
    pressed: list[str] = []

    async def press(call: ServiceCall) -> None:
        pressed.append(call.data["entity_id"])

    number = _own(hass, k2plus, "number", "pause_at_line")
    await _set_line(hass, number, 300)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    hass.services.async_register("button", "press", press)
    assert hass.states.get(number).state == "300", "taken up again"
    printer.line = 320
    await _later(hass, 11)
    assert pressed == [k2plus["pause_print"]]


async def test_a_pause_the_printer_refuses_is_tried_again_then_given_up(hass: HomeAssistant, k2plus, aioclient_mock) -> None:
    await _add(hass, k2plus)
    printer = Printer(aioclient_mock)
    tries: list[str] = []

    async def refuse(call: ServiceCall) -> None:
        tries.append(call.data["entity_id"])
        raise HomeAssistantError("printer busy")

    hass.services.async_register("button", "press", refuse)
    number = _own(hass, k2plus, "number", "pause_at_line")
    await _set_line(hass, number, 200)
    printer.line = 210
    await _later(hass, 11)
    for _ in range(5):
        await _later(hass, 1.5)
    assert len(tries) == 4 and hass.states.get(number).state == "0"


async def test_another_print_drops_the_pause(hass: HomeAssistant, k2plus, aioclient_mock) -> None:
    await _add(hass, k2plus)
    printer = Printer(aioclient_mock)
    number = _own(hass, k2plus, "number", "pause_at_line")
    await _set_line(hass, number, 900)
    printer.file = "Something else_PLA_1h2m.gcode"
    await _later(hass, 11)
    assert hass.states.get(number).state == "0"


async def test_the_page_is_told_where_the_printer_is(hass: HomeAssistant, k2plus, aioclient_mock, hass_ws_client) -> None:
    await _add(hass, k2plus)
    Printer(aioclient_mock)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/position"})
    told = (await client.receive_json())["result"]
    assert told == {"available": True, "target": None, "state": "printing", "line": 100, "lines": 1000, "eta": None}
    await _set_line(hass, _own(hass, k2plus, "number", "pause_at_line"), 500)
    await client.send_json({"id": 2, "type": f"{DOMAIN}/position"})
    told = (await client.receive_json())["result"]
    assert told["target"] == 500 and told["eta"] == pytest.approx((500 - 100) * LINE / (100 * LINE / 600.0))
    pause = hass.config_entries.async_entries(DOMAIN)[0].runtime_data.line_pause
    assert pause._index is not None, "the print's lines, read once"
    hass.states.async_set(k2plus["print_status"], "completed", {"file": FILE})
    await hass.async_block_till_done()
    assert pause._index is None, "let go when the print is over"


async def test_the_page_is_told_when_the_printer_cannot_be_reached(hass: HomeAssistant, k2plus, aioclient_mock, hass_ws_client) -> None:
    await _add(hass, k2plus)
    aioclient_mock.get(f"{BASE}/printer/objects/query", exc=aiohttp.ClientConnectionError("No route to host"))
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/position"})
    assert (await client.receive_json())["result"] == {"available": False, "target": None, "error": "unreachable"}


async def test_deleting_the_printer_deletes_its_pause(hass: HomeAssistant, k2plus, aioclient_mock, hass_storage) -> None:
    entry = await _add(hass, k2plus)
    Printer(aioclient_mock)
    await _set_line(hass, _own(hass, k2plus, "number", "pause_at_line"), 700)
    assert f"{DOMAIN}.{entry.entry_id}.line_pause" in hass_storage
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert f"{DOMAIN}.{entry.entry_id}.line_pause" not in hass_storage
