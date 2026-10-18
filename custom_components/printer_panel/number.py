"""Pause at G-code line: set a line and the print pauses about a second after the printer reaches it (linepause.py); 0
means no pause. On the printer's own device, so automations can set it; the Printer page sets it from its box."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import PAUSE_AT_LINE_SUFFIX
from .link import PrinterLink

PARALLEL_UPDATES = 1


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([PauseAtLineNumber(entry.runtime_data)])


class PauseAtLineNumber(NumberEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "pause_at_line"
    _attr_icon = "mdi:pause-octagon-outline"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 99_999_999
    _attr_native_step = 1
    _attr_should_poll = False

    def __init__(self, link: PrinterLink) -> None:
        self._link = link
        self._attr_unique_id = f"{link.device_id}_{PAUSE_AT_LINE_SUFFIX}"
        self.device_entry = dr.async_get(link.hass).async_get(link.device_id)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._link.line_pause.listen(self.async_write_ha_state))

    @property
    def native_value(self) -> int:
        return self._link.line_pause.target or 0

    async def async_set_native_value(self, value: float) -> None:
        await self._link.line_pause.arm(int(value))
