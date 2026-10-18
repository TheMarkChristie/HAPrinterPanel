"""Count G-code lines: while on, Printer Panel follows where the printer is in the file it is printing (the page's "Line X
of Y", and Pause at G-code line); while off, it asks the printer nothing (Mark, 18 Oct 2026). Setting a line to pause
at turns it on; turning it off drops that pause. On the printer's own device, so automations can switch it."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import COUNT_SUFFIX
from .link import PrinterLink

PARALLEL_UPDATES = 1


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([CountLinesSwitch(entry.runtime_data)])


class CountLinesSwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "count_lines"
    _attr_icon = "mdi:counter"
    _attr_should_poll = False

    def __init__(self, link: PrinterLink) -> None:
        self._link = link
        self._attr_unique_id = f"{link.device_id}_{COUNT_SUFFIX}"
        self.device_entry = dr.async_get(link.hass).async_get(link.device_id)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._link.line_pause.listen(self.async_write_ha_state))

    @property
    def is_on(self) -> bool:
        return self._link.line_pause.counting

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._link.line_pause.set_counting(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._link.line_pause.set_counting(False)
