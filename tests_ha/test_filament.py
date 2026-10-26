"""The filament register in a real Home Assistant, fed by the Creality integration's entities as the Norway K2 Plus had
them (tests/fixtures): checking spools in from the page, the CFS's Creality spool matched on its own and the Generic ones
waiting for their stock numbers, a print booked off the spools when it ends, a restart of Home Assistant mid-print, and
the printer switched off."""
from __future__ import annotations

import re
import zlib
from typing import Any

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
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


async def test_a_spool_in_with_nothing_set_can_be_confirmed_before_the_print(hass: HomeAssistant, k2plus, hass_ws_client) -> None:
    """Norway's 1B on 25 Oct 2026: filament unknown, but the CFS's state 1 says a spool is in."""
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    blank = {"vendor": "", "type": "", "name": "", "color_hex": "", "rfid": "", "spool_key": None, "selected": 0}
    hass.states.async_set(SLOT_B, "unknown", {**blank, "state": None})
    await hass.async_block_till_done()
    assert "1B" in _register(hass, entry).slots, "unknown with no state: the integration cannot say yet, the slot stays"
    hass.states.async_set(SLOT_B, "unknown", {**blank, "state": 1})
    await hass.async_block_till_done()
    assert _register(hass, entry).slots["1B"]["key"], "a spool is in"
    await _check_in(client, 1, "Sunlu", "Black", "#000000")
    assert (await _ask(client, 2, {"type": "printer_panel/filament/confirm", "slot": "1B", "stock": "F001"}))["success"]
    await _print(hass, [(0, "box_1_slot_2"), (3356, "box_1_slot_2")])
    assert _register(hass, entry).spool("F001")["left"] == 990.0 and not _register(hass, entry).pending


async def test_while_a_print_counts_the_page_gets_only_its_grams_and_it_is_saved_as_it_goes(
        hass: HomeAssistant, k2plus, hass_ws_client, hass_storage, monkeypatch) -> None:
    """Hundreds of spools are not sent every ten seconds; a long print is in storage, not only when it ends."""
    from custom_components.printer_panel import register

    monkeypatch.setattr(register, "TELL_EVERY", 0)
    monkeypatch.setattr(register, "SAVE_EVERY", 0)
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    await _check_in(client, 1, "Sunlu", "Black", "#000000")
    assert (await _ask(client, 2, {"type": "printer_panel/filament/subscribe"}))["success"]
    assert "spools" in (await client.receive_json())["event"]
    _set(hass, ACTIVE, "box_1_slot_2")
    _set(hass, STATUS, "printing", file=FILE, used_material_mm=1000)
    await hass.async_block_till_done()
    assert (await client.receive_json())["event"] == {"printing": {"1B": pytest.approx(1000 * GRAMS_PER_MM, abs=0.05)}}
    assert hass_storage[f"{DOMAIN}.{entry.entry_id}.filament"]["data"]["job"]["last"] == 1000
    _set(hass, STATUS, "completed", file=FILE, used_material_mm=1000)
    await hass.async_block_till_done()
    told = (await client.receive_json())["event"]
    assert "spools" in told and told["pending"] == {"1B": pytest.approx(1000 * GRAMS_PER_MM, abs=0.05)}, "a print booked: all of it"


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


async def test_the_register_as_a_pdf(hass: HomeAssistant, k2plus, hass_ws_client, hass_client, hass_client_no_auth) -> None:
    """The page's PDF button: a path Home Assistant signs, fetched without the page's token, in English or Norwegian."""
    from homeassistant.setup import async_setup_component

    from custom_components.printer_panel import FilamentPdfView

    assert await async_setup_component(hass, "http", {})
    assert await async_setup_component(hass, "auth", {})
    hass.http.register_view(FilamentPdfView())
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    await _check_in(client, 1, "Creality", "Purple", "#9e007e", "Hyper PLA")
    await _check_in(client, 2, "Sunlu", "Black", "#000000")
    assert (await _ask(client, 3, {"type": "printer_panel/filament/remove", "stock": "F002"}))["success"]
    web = await hass_client()
    for lang, words in (("en", [b"(Filament register)", b"(In stock \\(1\\))", b"(F001)", b"(1D)", b"(Removed)"]),
                        ("nb", [b"(Filamentregister)", b"(P\\345 lager \\(1\\))", b"(Fjernet)"])):
        answer = await web.get(f"/api/printer_panel/{entry.entry_id}/filament/{lang}.pdf")
        assert answer.status == 200 and answer.content_type == "application/pdf"
        assert answer.headers["Content-Disposition"].startswith('attachment; filename="filament-')
        body = await answer.read()
        text = b"\n".join(zlib.decompress(s) for s in re.findall(rb"/FlateDecode >>\nstream\n(.*?)\nendstream", body, re.S))
        assert body.startswith(b"%PDF-1.4") and all(w in text for w in words), lang
    assert (await web.get("/api/printer_panel/nope/filament/en.pdf")).status == 404
    path = f"/api/printer_panel/{entry.entry_id}/filament/en.pdf"
    anyone = await hass_client_no_auth()
    assert (await anyone.get(path)).status == 401
    signed = await _ask(client, 4, {"type": "auth/sign_path", "path": path, "expires": 60})
    assert signed["success"], signed
    answer = await anyone.get(signed["result"]["path"])
    assert answer.status == 200 and (await answer.read()).startswith(b"%PDF")


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


async def _add_telling(hass: HomeAssistant, k2plus: dict[str, str], events: list[str] | None, minor_version: int = 2) -> MockConfigEntry:
    options = {"title": "Printer", "notify": ["mobile_app_test"]}
    if events is not None:
        options["events"] = events
    hass.states.async_set(STATUS, "idle", {"file": "", "progress": 0})
    entry = MockConfigEntry(domain=DOMAIN, title="K2Plus-235D", unique_id=k2plus["device_id"], data={"device_id": k2plus["device_id"]},
                            options=options, version=1, minor_version=minor_version)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_a_spool_taken_low_tells_the_phones_and_finished_says_what_the_print_cost(
        hass: HomeAssistant, k2plus, hass_ws_client, phone) -> None:
    hass.config.currency = "NOK"
    await _add_telling(hass, k2plus, ["finished", "filament_low"])
    client = await hass_ws_client(hass)
    answer = await _ask(client, 1, {"type": "printer_panel/filament/check_in", "brand": "Sunlu", "colour": "Black", "hex": "#000000",
                                    "material": "PLA", "weight": 1000, "price": 199})
    assert answer["success"] and answer["result"]["price"] == 199.0
    assert (await _ask(client, 2, {"type": "printer_panel/filament/update", "stock": "F001", "left": 110}))["success"]
    assert (await _ask(client, 3, {"type": "printer_panel/filament/confirm", "slot": "1B", "stock": "F001"}))["success"]
    await _print(hass, [(0, "box_1_slot_2"), (3356, "box_1_slot_2")])
    await hass.async_block_till_done()
    texts = sorted(p["message"] for p in phone)
    assert texts[0] == "Coaster is finished, after " + texts[0].split("after ")[1].split(".")[0] + ". Filament: 10 g, 1.99 kr."
    assert texts[1] == "F001 Sunlu Black is down to 100 g (10 %)."
    low = next(p for p in phone if p["message"].startswith("F001"))
    assert low["data"]["tag"].endswith("_F001"), "its own notification, not the print's"


async def test_no_low_notification_when_it_is_not_chosen(hass: HomeAssistant, k2plus, hass_ws_client, phone) -> None:
    await _add_telling(hass, k2plus, ["finished"])
    client = await hass_ws_client(hass)
    await _check_in(client, 1, "Sunlu", "Black", "#000000", weight=12)
    await _ask(client, 2, {"type": "printer_panel/filament/confirm", "slot": "1B", "stock": "F001"})
    await _print(hass, [(0, "box_1_slot_2"), (3356, "box_1_slot_2")])
    await hass.async_block_till_done()
    assert [p["message"] for p in phone if p["message"].startswith("F001")] == []


async def test_printers_set_up_before_get_the_low_notification_and_keep_their_choices(hass: HomeAssistant, k2plus) -> None:
    entry = await _add_telling(hass, k2plus, ["finished", "error"], minor_version=1)
    assert entry.minor_version == 2 and entry.options["events"] == ["finished", "error", "filament_low"]
    assert entry.options["notify"] == ["mobile_app_test"]


async def test_the_sensors(hass: HomeAssistant, k2plus, hass_ws_client) -> None:
    hass.config.currency = "NOK"
    entry = await _add(hass, k2plus)
    reg = er.async_get(hass)
    ids = {key: reg.async_get_entity_id("sensor", DOMAIN, f"{k2plus['device_id']}_{key}")
           for key in ("filament_in_stock", "spools_in_stock", "spools_low", "last_print_filament", "last_print_filament_cost")}
    assert all(ids.values()), ids
    client = await hass_ws_client(hass)
    await _check_in(client, 1, "Sunlu", "Black", "#000000")
    await _ask(client, 2, {"type": "printer_panel/filament/check_in", "brand": "eSun", "colour": "Pink", "hex": "#ff37af",
                           "material": "PLA", "weight": 750, "price": 150})
    await _ask(client, 3, {"type": "printer_panel/filament/update", "stock": "F002", "left": 60})
    await _ask(client, 4, {"type": "printer_panel/filament/confirm", "slot": "1A", "stock": "F002"})
    await _print(hass, [(0, "box_1_slot_1"), (3356, "box_1_slot_1")])
    await hass.async_block_till_done()
    state = lambda key: hass.states.get(ids[key])  # noqa: E731
    assert float(state("filament_in_stock").state) == 1.05 and state("filament_in_stock").attributes["unit_of_measurement"] == "kg"
    assert state("spools_in_stock").state == "2" and state("spools_low").state == "1"
    assert state("spools_low").attributes["spools"] == [{"stock": "F002", "name": "eSun Pink", "type": "PLA", "left": 50.0}]
    assert float(state("last_print_filament").state) == 10.0
    cost = state("last_print_filament_cost")
    assert float(cost.state) == 2.0 and cost.attributes["unit_of_measurement"] == "NOK", "10 g of 150 kr for 750 g"
    assert entry.runtime_data.filament.book.last_print["file"] == FILE


async def test_weighed_through_the_page_and_a_tag_found_by_its_colour(hass: HomeAssistant, k2plus, hass_ws_client) -> None:
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    await _check_in(client, 1, "Sunlu", "Black", "#000000")
    await _check_in(client, 2, "Sunlu", "Black", "#000000")
    no_tare = await _ask(client, 3, {"type": "printer_panel/filament/update", "stock": "F001", "weighed": 800})
    assert not no_tare["success"] and no_tare["error"]["code"] == "invalid_format"
    weighed = await _ask(client, 4, {"type": "printer_panel/filament/update", "stock": "F001", "weighed": 800, "tare": 180})
    assert weighed["success"] and weighed["result"]["left"] == 620.0
    tag = await _ask(client, 5, {"type": "printer_panel/filament/tag", "stock": "F002"})
    assert tag["success"] and tag["result"]["material"] == "Generic PLA" and tag["result"]["weight"] == 1000
    colour = tag["result"]["tag"]
    assert colour != "#000000" and (await _ask(client, 6, {"type": "printer_panel/filament/tag", "stock": "F002"}))["result"]["tag"] == colour
    hass.states.async_set(SLOT_B, "Generic PLA", {"vendor": "Creality", "type": "PLA", "name": "Generic PLA", "color_hex": colour,
                                                  "rfid": "00001", "state": 2, "selected": 0})
    await hass.async_block_till_done()
    assert entry.runtime_data.filament.book.slots["1B"].get("stock") == "F002", "the CFS read the tag: F002, not F001"


async def test_a_print_going_wrong_on_norway_comes_off_its_spool_once(hass: HomeAssistant, k2plus, hass_ws_client) -> None:
    """26 Oct 2026, tag Robert in 1C: errors, pauses and idles, the printer twice away and back (its count 0, then where
    it was), stopped at 77,269 mm. It came off the spool four times over; now once, about 230 g."""
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    await _check_in(client, 1, "Sunlu", "Black", "#000000")
    await _ask(client, 2, {"type": "printer_panel/filament/confirm", "slot": "1B", "stock": "F001"})
    robert = "/mnt/UDISK/printer_data/gcodes/tag Robert_PLA_5h51m22s.gcode"
    for state, used, slot in (("printing", 0, "unknown"), ("printing", 455, "box_1_slot_2"), ("printing", 74782, "box_1_slot_2"),
                              ("unavailable", None, "unavailable"), ("printing", 74797, "box_1_slot_2"), ("idle", 75269, "box_1_slot_2"),
                              ("error", 75338, "box_1_slot_2"), ("unavailable", None, "unavailable"), ("idle", 0, "unknown"),
                              ("printing", 0, "unknown"), ("printing", 75268, "unknown"), ("error", 75647, "unknown"),
                              ("paused", 75647, "box_1_slot_2"), ("idle", 75647, "box_1_slot_2"), ("printing", 76022, "box_1_slot_2"),
                              ("error", 76022, "box_1_slot_2"), ("printing", 76685, "box_1_slot_2"), ("processing", 77267, "unknown"),
                              ("stopped", 77269, "unknown")):
        hass.states.async_set(ACTIVE, slot)
        if used is None:
            hass.states.async_set(STATUS, state, {})
        else:
            hass.states.async_set(STATUS, state, {"file": robert if state != "idle" or used else "", "used_material_mm": used})
        await hass.async_block_till_done()
    book = _register(hass, entry)
    assert book.job is None and not book.pending
    assert book.spool("F001")["left"] == pytest.approx(1000 - 77269 * GRAMS_PER_MM, abs=0.5)
    assert book.last_print["grams"] == pytest.approx(77269 * GRAMS_PER_MM, abs=0.5)


async def test_a_printer_starting_up_does_not_take_a_slots_spool_away(hass: HomeAssistant, k2plus, hass_ws_client, monkeypatch) -> None:
    """Restarting, the CFS says passing things about a slot for up to half a minute: unknown, unknown with a spool in,
    a black Generic PLA. A slot's reading must hold a minute before the register acts on it."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    from custom_components.printer_panel import register

    monkeypatch.setattr(register, "SLOT_SETTLE", 60)
    entry = await _add(hass, k2plus)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))   # a new register learns its slots a minute on
    await hass.async_block_till_done()
    client = await hass_ws_client(hass)
    await _check_in(client, 1, "Creality", "Purple", "#9e007e", "Hyper PLA")
    book = _register(hass, entry)
    assert book.slots["1D"]["stock"] == "F001"
    purple = dict(hass.states.get(SLOT_D).attributes)
    for state, attributes in (("unknown", {}), ("unknown", {**purple, "vendor": "", "name": "", "color_hex": "", "state": 1}),
                              ("Generic PLA", {**purple, "vendor": "Generic", "name": "Generic PLA", "color_hex": "#000000", "state": 1}),
                              ("Creality Hyper PLA", purple)):
        hass.states.async_set(SLOT_D, state, attributes)
        await hass.async_block_till_done()
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=20))
        await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=120))
    await hass.async_block_till_done()
    assert book.slots["1D"]["stock"] == "F001", "the purple spool kept its number"
    hass.states.async_set(SLOT_D, "-", {**purple, "vendor": "", "name": "", "color_hex": "", "state": 0})
    await hass.async_block_till_done()
    assert book.slots["1D"]["stock"] == "F001", "not yet: a reading must hold"
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert "1D" not in book.slots, "the spool taken out, a minute on"


async def test_a_slot_given_its_number_while_the_printer_is_off_keeps_it(hass: HomeAssistant, k2plus, hass_ws_client) -> None:
    """Mark, 26 Oct 2026: F005 into 1B with the printer off. The number holds when the printer is back on with a spool
    in 1B, and goes if 1B is empty."""
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    await _check_in(client, 1, "Creality", "Gold", "#ffbf00", "PLA+")
    gold = {"vendor": "Creality", "type": "PLA", "name": "CR-PLA", "color_hex": "#f2b600", "rfid": "01002", "state": 2, "selected": 0}
    for entity in (SLOT_B, STATUS, ACTIVE):
        hass.states.async_set(entity, "unavailable", {})
    await hass.async_block_till_done()
    book = _register(hass, entry)
    book.slots.pop("1B", None)       # as on Norway: the register had nothing for 1B
    assert (await _ask(client, 2, {"type": "printer_panel/filament/confirm", "slot": "1B", "stock": "F001"}))["success"]
    hass.states.async_set(SLOT_B, "Creality CR-PLA", gold)
    await hass.async_block_till_done()
    assert book.slots["1B"]["stock"] == "F001" and book.slots["1B"]["key"], "back on: the spool in 1B is F001"
