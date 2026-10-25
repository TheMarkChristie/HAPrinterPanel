"""Setting up Printer Panel: which Creality printer, the sidebar item's title, and who is told when a print finishes,
pauses, runs out of filament or stops with an error. One entry per printer."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    CONF_DEVICE,
    CONF_EVENTS,
    CONF_NOTIFY,
    CONF_TITLE,
    DEFAULT_EVENTS,
    DEFAULT_TITLE,
    DOMAIN,
    NOT_TARGETS,
    SOURCE_DOMAIN,
)
from .printer import EVENTS, KEYS


def printers(hass: HomeAssistant) -> dict[str, str]:
    """The Creality integration's printers: device id -> name."""
    devices = dr.async_get(hass)
    out: dict[str, str] = {}
    for e in er.async_get(hass).entities.values():
        if e.platform == SOURCE_DOMAIN and e.translation_key == KEYS["status"] and e.device_id:
            device = devices.async_get(e.device_id)
            if device:
                out[device.id] = device.name_by_user or device.name or device.id
    return out


def notify_targets(hass: HomeAssistant) -> list[str]:
    """The notify services that reach a person (the phones' mobile_app_... ones and the like)."""
    return sorted(s for s in hass.services.async_services_for_domain("notify") if s not in NOT_TARGETS)


def _tell_schema(hass: HomeAssistant, defaults: dict[str, Any]) -> dict[Any, Any]:
    targets = sorted(set(notify_targets(hass)) | set(defaults.get(CONF_NOTIFY) or []))
    return {
        vol.Required(CONF_TITLE, default=defaults.get(CONF_TITLE, DEFAULT_TITLE)): TextSelector(),
        vol.Optional(CONF_NOTIFY, default=list(defaults.get(CONF_NOTIFY) or [])): SelectSelector(
            SelectSelectorConfig(options=targets, multiple=True, custom_value=True, mode=SelectSelectorMode.LIST)),
        vol.Optional(CONF_EVENTS, default=list(defaults.get(CONF_EVENTS) or DEFAULT_EVENTS)): SelectSelector(
            SelectSelectorConfig(options=list(EVENTS), multiple=True, mode=SelectSelectorMode.LIST, translation_key="event")),
    }


class PrinterPanelConfigFlow(ConfigFlow, domain=DOMAIN):
    """A printer for the sidebar."""

    VERSION = 1
    MINOR_VERSION = 2       # 1.2: filament_low among the events

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        found = printers(self.hass)
        if not found:
            return self.async_abort(reason="no_printer")
        if user_input is not None:
            device = str(user_input[CONF_DEVICE])
            await self.async_set_unique_id(device)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=found.get(device, DEFAULT_TITLE), data={CONF_DEVICE: device},
                options={CONF_TITLE: str(user_input.get(CONF_TITLE) or DEFAULT_TITLE).strip() or DEFAULT_TITLE,
                         CONF_NOTIFY: list(user_input.get(CONF_NOTIFY) or []),
                         CONF_EVENTS: list(user_input.get(CONF_EVENTS) or DEFAULT_EVENTS)})
        phones = [t for t in notify_targets(self.hass) if t.startswith("mobile_app_")]
        schema = {
            vol.Required(CONF_DEVICE, default=next(iter(found))): SelectSelector(SelectSelectorConfig(
                options=[SelectOptionDict(value=k, label=v) for k, v in found.items()], mode=SelectSelectorMode.DROPDOWN)),
            **_tell_schema(self.hass, {CONF_NOTIFY: phones}),
        }
        return self.async_show_form(step_id="user", data_schema=vol.Schema(schema))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PrinterPanelOptionsFlow()


class PrinterPanelOptionsFlow(OptionsFlow):
    """The sidebar title and the notifications."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={
                CONF_TITLE: str(user_input.get(CONF_TITLE) or DEFAULT_TITLE).strip() or DEFAULT_TITLE,
                CONF_NOTIFY: list(user_input.get(CONF_NOTIFY) or []),
                CONF_EVENTS: list(user_input.get(CONF_EVENTS) or [])})
        return self.async_show_form(step_id="init", data_schema=vol.Schema(_tell_schema(self.hass, dict(self.config_entry.options))))
