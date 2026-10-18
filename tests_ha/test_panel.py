"""Printer Panel in a real Home Assistant: setting a printer up, the sidebar item, what the page is told, the
notifications, a renamed entity, and the options."""
from __future__ import annotations

from homeassistant.components.frontend import DATA_PANELS
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "printer_panel"
STATUS_FILE = "/mnt/UDISK/printer_data/gcodes/GTA 6 stand - Warden of Bacon_PLA_9h1m52s.gcode"


async def _add(hass: HomeAssistant, k2plus: dict[str, str], **options) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="K2Plus-235D", unique_id=k2plus["device_id"], data={"device_id": k2plus["device_id"]},
                            options={"title": "Printer", "notify": ["mobile_app_test"], "events": ["finished", "paused", "runout", "error"], **options})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_no_printer_means_nothing_to_set_up(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "abort" and result["reason"] == "no_printer"


async def test_setting_the_printer_up_offers_it_and_the_phones(hass: HomeAssistant, k2plus, phone) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    schema = {str(k): k for k in result["data_schema"].schema}
    assert schema["device_id"].default() == k2plus["device_id"]
    assert schema["notify"].default() == ["mobile_app_test"], "the phones are ticked to begin with"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"device_id": k2plus["device_id"], "title": "Printer",
                                                                                  "notify": ["mobile_app_test"], "events": ["finished"]})
    assert result["type"] == "create_entry" and result["title"] == "K2Plus-235D"
    assert result["options"] == {"title": "Printer", "notify": ["mobile_app_test"], "events": ["finished"]}
    again = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    again = await hass.config_entries.flow.async_configure(again["flow_id"], {"device_id": k2plus["device_id"], "title": "Printer"})
    assert again["type"] == "abort" and again["reason"] == "already_configured"


async def test_the_sidebar_item_and_what_the_page_is_told(hass: HomeAssistant, k2plus, hass_ws_client) -> None:
    entry = await _add(hass, k2plus)
    panel = hass.data[DATA_PANELS]["printer"]
    assert panel.sidebar_title == "Printer" and panel.sidebar_icon == "printer-panel:creality" and not panel.require_admin
    assert panel.config["_panel_custom"]["name"] == "printer-panel" and panel.config["entry_id"] == entry.entry_id
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "printer_panel/config"})
    answer = await client.receive_json()
    assert answer["success"], answer
    told = answer["result"]
    assert told["name"] == "K2Plus-235D" and told["path"] == "printer" and told["entities"]["status"] == k2plus["print_status"]
    assert [s["label"] for s in told["boxes"][0]["slots"]] == ["1A", "1B", "1C", "1D"] and told["external"]["label"] == "Ext"
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert "printer" not in hass.data[DATA_PANELS]


async def test_a_finished_print_tells_the_phone_with_its_name_and_time(hass: HomeAssistant, k2plus, phone) -> None:
    await _add(hass, k2plus)
    status = k2plus["print_status"]
    hass.states.async_set(status, "printing", {"file": STATUS_FILE, "progress": 99})
    await hass.async_block_till_done()
    hass.states.async_set(k2plus["print_job_time"], "32520")
    hass.states.async_set(status, "completed", {"file": STATUS_FILE, "progress": 100})
    await hass.async_block_till_done()
    assert len(phone) == 1
    sent = phone[0]
    assert sent["title"] == "3D printer" and sent["message"] == "GTA 6 stand - Warden of Bacon is finished, after 9 h 2 min."
    assert sent["data"]["clickAction"] == "/printer" and sent["data"]["image"] == f"/api/camera_proxy/{k2plus['printer_camera']}"


async def test_restarts_and_unwanted_events_tell_nobody(hass: HomeAssistant, k2plus, phone) -> None:
    await _add(hass, k2plus, events=["finished", "runout"])
    status = k2plus["print_status"]
    hass.states.async_set(status, "unavailable")
    await hass.async_block_till_done()
    hass.states.async_set(status, "completed", {"file": STATUS_FILE})
    await hass.async_block_till_done()
    hass.states.async_set(status, "printing", {"file": STATUS_FILE})
    await hass.async_block_till_done()
    hass.states.async_set(status, "paused", {"file": STATUS_FILE})
    await hass.async_block_till_done()
    assert phone == [], "a restart is not a finished print, and pauses were not asked for"
    hass.states.async_set(k2plus["filament_status"], "normal")
    await hass.async_block_till_done()
    hass.states.async_set(k2plus["filament_status"], "runout")
    await hass.async_block_till_done()
    assert [s["message"] for s in phone] == ["GTA 6 stand - Warden of Bacon: the filament ran out at 56 %."]


async def test_a_renamed_status_entity_is_still_followed(hass: HomeAssistant, k2plus, phone) -> None:
    await _add(hass, k2plus)
    er.async_get(hass).async_update_entity(k2plus["print_status"], new_entity_id="sensor.k2_status")
    await hass.async_block_till_done()
    hass.states.async_set("sensor.k2_status", "printing", {"file": STATUS_FILE})
    await hass.async_block_till_done()
    hass.states.async_set("sensor.k2_status", "error", {"file": STATUS_FILE})
    await hass.async_block_till_done()
    assert [s["message"] for s in phone] == ["GTA 6 stand - Warden of Bacon stopped with an error at 56 %."]


async def test_a_phone_that_has_gone_does_not_stop_the_others(hass: HomeAssistant, k2plus, phone) -> None:
    await _add(hass, k2plus, notify=["mobile_app_gone", "mobile_app_test"])
    status = k2plus["print_status"]
    hass.states.async_set(status, "printing", {"file": STATUS_FILE})
    await hass.async_block_till_done()
    hass.states.async_set(status, "paused", {"file": STATUS_FILE})
    await hass.async_block_till_done()
    assert [s["message"] for s in phone] == ["GTA 6 stand - Warden of Bacon is paused at 56 %."]


async def test_the_options_rename_the_sidebar_item(hass: HomeAssistant, k2plus, phone) -> None:
    entry = await _add(hass, k2plus)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"title": "K2", "notify": [], "events": ["finished"]})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.data[DATA_PANELS]["printer"].sidebar_title == "K2"
