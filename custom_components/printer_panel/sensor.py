"""The filament register as sensors on the printer's device, for dashboards and automations (Mark, 25 Oct 2026): the
filament in stock, the spools in stock and the low ones (10 % or less, which they are as attributes), and the last
print's filament and what it cost where its spools have a price."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfMass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .filament import LOW_SHARE, Register
from .link import PrinterLink

PARALLEL_UPDATES = 0


def in_stock(book: Register) -> list[dict[str, Any]]:
    return [s for s in book.spools if s["left"] > 0]


def low(book: Register) -> list[dict[str, Any]]:
    return [s for s in in_stock(book) if s["weight"] > 0 and s["left"] <= s["weight"] * LOW_SHARE]


def _last(book: Register, key: str) -> Any:
    return (book.last_print or {}).get(key)


@dataclass(frozen=True, kw_only=True)
class FilamentSensorDescription(SensorEntityDescription):
    value: Callable[[Register], Any]
    attributes: Callable[[Register], dict[str, Any]] | None = None


SENSORS = (
    FilamentSensorDescription(
        key="filament_in_stock", translation_key="filament_in_stock", icon="mdi:printer-3d-nozzle",
        device_class=SensorDeviceClass.WEIGHT, state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfMass.GRAMS, suggested_unit_of_measurement=UnitOfMass.KILOGRAMS,
        suggested_display_precision=1, value=lambda b: round(sum(s["left"] for s in in_stock(b)), 1)),
    FilamentSensorDescription(
        key="spools_in_stock", translation_key="spools_in_stock", icon="mdi:package-variant-closed",
        state_class=SensorStateClass.MEASUREMENT, value=lambda b: len(in_stock(b))),
    FilamentSensorDescription(
        key="spools_low", translation_key="spools_low", icon="mdi:alert-circle-outline",
        state_class=SensorStateClass.MEASUREMENT, value=lambda b: len(low(b)),
        attributes=lambda b: {"spools": [{"stock": s["stock"], "name": " ".join(filter(None, (s["brand"], s.get("colour")))),
                                          "type": s["type"], "left": s["left"]} for s in low(b)]}),
    FilamentSensorDescription(
        key="last_print_filament", translation_key="last_print_filament", icon="mdi:printer-3d",
        device_class=SensorDeviceClass.WEIGHT, native_unit_of_measurement=UnitOfMass.GRAMS,
        suggested_display_precision=1, value=lambda b: _last(b, "grams"),
        attributes=lambda b: {"file": _last(b, "file"), "ended": _last(b, "ended")}),
    FilamentSensorDescription(
        key="last_print_filament_cost", translation_key="last_print_filament_cost", icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY, suggested_display_precision=2, value=lambda b: _last(b, "cost"),
        attributes=lambda b: {"not_costed_g": _last(b, "uncosted"), "file": _last(b, "file")}),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(FilamentSensor(entry.runtime_data, description) for description in SENSORS)


class FilamentSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    entity_description: FilamentSensorDescription

    def __init__(self, link: PrinterLink, description: FilamentSensorDescription) -> None:
        self.entity_description = description
        self._link = link
        self._attr_unique_id = f"{link.device_id}_{description.key}"
        self.device_entry = dr.async_get(link.hass).async_get(link.device_id)
        if description.device_class is SensorDeviceClass.MONETARY:
            self._attr_native_unit_of_measurement = link.hass.config.currency

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._link.filament.listen(self._changed))

    @callback
    def _changed(self, full: bool) -> None:
        if full:        # a print's grams so far change none of these
            self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self._link.filament.book)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        describe = self.entity_description.attributes
        return describe(self._link.filament.book) if describe else None
