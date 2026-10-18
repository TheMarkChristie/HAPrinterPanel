"""Restart printer: Moonraker on the printer reboots it, so the screen, the camera, the CFS and the firmware all start
again; it is back in a minute or two. On the printer's own device, so automations find it there. The Printer page
hides it while a print is running (Mark, 18 Oct 2026); the entity itself does what it is told, for automations."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import RESTART_SUFFIX
from .linepause import moonraker_error
from .link import PrinterLink
from .moonraker import MoonrakerError

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 1


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([RestartPrinterButton(entry.runtime_data)])


class RestartPrinterButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "restart_printer"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, link: PrinterLink) -> None:
        self._link = link
        self._attr_unique_id = f"{link.device_id}_{RESTART_SUFFIX}"
        self.device_entry = dr.async_get(link.hass).async_get(link.device_id)

    async def async_press(self) -> None:
        _LOGGER.info("Printer Panel: restarting %s", self.device_entry.name if self.device_entry else "the printer")
        try:
            await self._link.moonraker().reboot()
        except MoonrakerError as err:
            raise moonraker_error(err) from err
