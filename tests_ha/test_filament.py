"""The filament register in a real Home Assistant, fed by the Creality integration's entities as the Norway K2 Plus had
them (tests/fixtures): checking spools in from the page, the CFS's Creality spool matched on its own and the Generic ones
waiting for their stock numbers, a print booked off the spools when it ends, a restart of Home Assistant mid-print, and
the printer switched off."""
from __future__ import annotations

from typing import Any

import pytest

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "printer_panel"
P = "sensor.3d_printer_room_k2plus_235d_cfs_"
STATUS, ACTIVE = f"{P}print_status", f"{P}active_filament_slot"
SLOT_B, SLOT_D = f"{P}cfs_box_1_slot_2_filament", f"{P}cfs_box_1_slot_4_filament"
FILE = "/mnt/UDISK/printer_data/gcodes/Coaster_PLA_1h2m.gcode"
GRAMS_PER_MM = 3.14159265 * 0.875 ** 2 / 1000 * 1.24    # 1.75 mm PLA


async def _add(hass: HomeAssistant, k2plus: dict[str, str]) -> MockConfigEntry:
    hass.states.async_set(STATUS, "idle", {"file": "", "progress": 0})
    entry = MockConfigEntry(domain=DOMAIN, title="K2Plus-235D", unique_id=k2plus["device_id"], data={"device_id": k2plus["device_id"]},
                            options={"title": "Printer", "notify": [], "events": []})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _ask(client, n: int, message: dict[str, Any]) -> dict[str, Any]:
    await client.send_json({"id": n, **message})
    return await client.receive_json()


async def _check_in(client, n: int, brand: str, colour: str, hex_: str, material: str = "PLA", weight: float = 1000) -> dict[str, Any]:
    answer = await _ask(client, n, {"type": "printer_panel/filament/check_in", "brand": brand, "colour": colour, "hex": hex_,
                                    "material": material, "weight": weight})
    assert answer["success"], answer
    return answer["result"]


def _set(hass: HomeAssistant, entity_id: str, state: str, **attributes: Any) -> None:
    old = hass.states.get(entity_id)
    hass.states.async_set(entity_id, state, {**(dict(old.attributes) if old else {}), **attributes})


async def _print(hass: HomeAssistant, steps: list[tuple[float, str]], end: str = "completed") -> None:
    """A print: (the printer's count of filament used in mm, the slot printing), then its end."""
    for used, slot in steps:
        _set(hass, ACTIVE, slot)
        _set(hass, STATUS, "printing", file=FILE, used_material_mm=used)
        await hass.async_block_till_done()
    _set(hass, STATUS, end, file=FILE, used_material_mm=steps[-1][0])
    await hass.async_block_till_done()


def _register(hass: HomeAssistant, entry: MockConfigEntry):
    return entry.runtime_data.filament.book


async def test_check_in_gives_the_stock_number_and_the_creality_spool_in_the_cfs_finds_its_slot(hass: HomeAssistant, k2plus, hass_ws_client) -> None:
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    purple = await _check_in(client, 1, "Creality", "Purple", "#9e007e", "Hyper PLA")
    black = await _check_in(client, 2, "Sunlu", "Black", "#000000", weight=750)
    assert (purple["stock"], purple["slot"]) == ("F001", "1D"), "the CFS read its chip: it is the Creality spool in 1D"
    assert (black["stock"], black["slot"], black["left"]) == ("F002", None, 750.0), "a Generic spool waits for its number"
    view = (await _ask(client, 3, {"type": "printer_panel/filament/subscribe"}))
    assert view["success"]
    told = (await client.receive_json())["event"]
    assert [s["stock"] for s in told["spools"]] == ["F001", "F002"] and told["slots"] == {"1D": {"stock": "F001", "how": "auto"}}
    refused = await _ask(client, 4, {"type": "printer_panel/filament/check_in", "brand": "", "material": "PLA", "weight": 1000})
    assert not refused["success"] and refused["error"]["code"] == "invalid_format"
    assert _register(hass, entry).next == 3


async def test_a_print_comes_off_the_spools_and_the_unconfirmed_slot_waits_for_its_number(hass: HomeAssistant, k2plus, hass_ws_client) -> None:
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    await _check_in(client, 1, "Creality", "Purple", "#9e007e", "Hyper PLA")
    await _check_in(client, 2, "Sunlu", "Black", "#000000")
    await _print(hass, [(0, "box_1_slot_4"), (2000, "box_1_slot_4"), (3000, "box_1_slot_2"), (5000, "box_1_slot_2")])
    book = _register(hass, entry)
    assert book.spool("F001")["left"] == pytest.approx(1000 - 2000 * GRAMS_PER_MM, abs=0.05)
    assert book.job is None and "1B" in book.pending
    answer = await _ask(client, 3, {"type": "printer_panel/filament/confirm", "slot": "1B", "stock": "f002"})
    assert answer["success"] and answer["result"]["booked"] == pytest.approx(3000 * GRAMS_PER_MM, abs=0.05)
    assert book.spool("F002")["left"] == pytest.approx(1000 - 3000 * GRAMS_PER_MM, abs=0.05) and not book.pending
    unknown = await _ask(client, 4, {"type": "printer_panel/filament/confirm", "slot": "1B", "stock": "F099"})
    assert not unknown["success"] and unknown["error"]["code"] == "not_found"


async def test_grams_from_a_spool_not_in_the_register_are_dropped(hass: HomeAssistant, k2plus, hass_ws_client) -> None:
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    await _check_in(client, 1, "Sunlu", "Black", "#000000")
    await _print(hass, [(0, "box_1_slot_2"), (3356, "box_1_slot_2")])
    assert "1B" in _register(hass, entry).pending
    answer = await _ask(client, 2, {"type": "printer_panel/filament/forget", "slot": "1B"})
    assert answer["success"] and answer["result"]["dropped"] == 10.0
    assert not _register(hass, entry).pending and _register(hass, entry).spool("F001")["left"] == 1000.0
    again = await _ask(client, 3, {"type": "printer_panel/filament/forget", "slot": "1B"})
    assert not again["success"] and again["error"]["code"] == "not_found"


async def test_confirmed_before_a_stopped_print_it_comes_off_at_once(hass: HomeAssistant, k2plus, hass_ws_client) -> None:
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    await _check_in(client, 1, "Sunlu", "Black", "#000000")
    assert (await _ask(client, 2, {"type": "printer_panel/filament/confirm", "slot": "1B", "stock": "F001"}))["success"]
    await _print(hass, [(0, "box_1_slot_2"), (3356, "box_1_slot_2")], end="stopped")
    assert _register(hass, entry).spool("F001")["left"] == 990.0 and not _register(hass, entry).pending


async def test_a_print_under_way_when_home_assistant_restarts_is_taken_up(hass: HomeAssistant, k2plus, hass_ws_client) -> None:
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    await _check_in(client, 1, "Sunlu", "Black", "#000000")
    assert (await _ask(client, 2, {"type": "printer_panel/filament/confirm", "slot": "1B", "stock": "F001"}))["success"]
    _set(hass, ACTIVE, "box_1_slot_2")
    _set(hass, STATUS, "printing", file=FILE, used_material_mm=0)
    await hass.async_block_till_done()
    _set(hass, STATUS, "printing", file=FILE, used_material_mm=1000)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(entry.entry_id)      # storage is written as it unloads
    await hass.async_block_till_done()
    assert _register(hass, entry).job["last"] == 1000, "the print is taken up where it was"
    _set(hass, STATUS, "printing", file=FILE, used_material_mm=3356)
    await hass.async_block_till_done()
    _set(hass, STATUS, "completed", file=FILE, used_material_mm=3356)
    await hass.async_block_till_done()
    assert _register(hass, entry).spool("F001")["left"] == 990.0, "counted once, not twice"


async def test_the_printer_off_leaves_the_slots_and_an_emptied_slot_lets_its_spool_go(hass: HomeAssistant, k2plus, hass_ws_client) -> None:
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    await _check_in(client, 1, "Sunlu", "Black", "#000000")
    await _ask(client, 2, {"type": "printer_panel/filament/confirm", "slot": "1B", "stock": "F001"})
    hass.states.async_set(SLOT_B, "unavailable", {})
    await hass.async_block_till_done()
    assert _register(hass, entry).slots["1B"]["stock"] == "F001", "the printer off says nothing about its spools"
    hass.states.async_set(SLOT_B, "-", {"vendor": "", "type": "", "name": "", "color_hex": "", "state": 0})
    await hass.async_block_till_done()
    assert "1B" not in _register(hass, entry).slots


async def test_editing_removing_and_deleting_the_printer(hass: HomeAssistant, k2plus, hass_ws_client, hass_storage) -> None:
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    await _check_in(client, 1, "Creality", "Purple", "#9e007e", "Hyper PLA")
    edited = await _ask(client, 2, {"type": "printer_panel/filament/update", "stock": "F001", "left": 412, "material": "PLA"})
    assert edited["success"] and edited["result"]["left"] == 412.0 and edited["result"]["type"] == "PLA"
    removed = await _ask(client, 3, {"type": "printer_panel/filament/remove", "stock": "F001"})
    assert removed["success"] and not _register(hass, entry).spools and "stock" not in _register(hass, entry).slots.get("1D", {})
    assert f"{DOMAIN}.{entry.entry_id}.filament" in hass_storage
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert f"{DOMAIN}.{entry.entry_id}.filament" not in hass_storage
