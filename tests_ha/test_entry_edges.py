"""The entry's edges (0.6.1): a Creality printer that is gone from Home Assistant fails the set-up with a message that
says what to do, Reconfigure points the same entry at a printer again and keeps its filament register, and the
register's delayed save is written as the entry unloads."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from test_filament import ACTIVE, FILE, STATUS, _add, _ask, _check_in, _register, _set

DOMAIN = "printer_panel"


async def test_a_printer_that_is_gone_says_so_instead_of_an_empty_page(hass: HomeAssistant, k2plus) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="Old printer", unique_id="gone", data={"device_id": "gone"},
                            options={"title": "Printer", "notify": [], "events": []})
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert "Reconfigure" in (entry.reason or "")


async def test_reconfigure_points_the_entry_at_a_printer_again_and_keeps_the_register(hass: HomeAssistant, k2plus, hass_ws_client) -> None:
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    await _check_in(client, 1, "Sunlu", "Black", "#000000")
    # the Creality integration added again: a new device with the printer's status entity
    source = MockConfigEntry(domain="ha_creality_ws", title="Creality Printer (WS)", data={"host": "192.0.2.61"})
    source.add_to_hass(hass)
    new = dr.async_get(hass).async_get_or_create(config_entry_id=source.entry_id, identifiers={("ha_creality_ws", "k2plus-new")},
                                                 name="K2Plus-NEW", model="K2 Plus")
    er.async_get(hass).async_get_or_create("sensor", "ha_creality_ws", "k2plus-new-status", suggested_object_id="k2plus_new_print_status",
                                           config_entry=source, device_id=new.id, translation_key="print_status")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id})
    assert result["type"] == "form" and result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"device_id": new.id})
    assert result["type"] == "abort" and result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.data["device_id"] == new.id and entry.unique_id == new.id and entry.title == "K2Plus-NEW"
    assert entry.state is ConfigEntryState.LOADED
    assert _register(hass, entry).spool("F001")["brand"] == "Sunlu", "the register went with the entry"


async def test_the_register_is_written_as_the_entry_unloads(hass: HomeAssistant, k2plus, hass_ws_client, hass_storage) -> None:
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    await _check_in(client, 1, "Sunlu", "Black", "#000000")
    assert (await _ask(client, 2, {"type": "printer_panel/filament/confirm", "slot": "1B", "stock": "F001"}))["success"]
    _set(hass, ACTIVE, "box_1_slot_2")
    _set(hass, STATUS, "printing", file=FILE, used_material_mm=0)
    await hass.async_block_till_done()
    _set(hass, STATUS, "printing", file=FILE, used_material_mm=1000)
    await hass.async_block_till_done()
    key = f"{DOMAIN}.{entry.entry_id}.filament"
    assert (hass_storage[key]["data"].get("job") or {}).get("last") != 1000, "the delayed save has not run yet"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass_storage[key]["data"]["job"]["last"] == 1000, "written as it unloaded"
