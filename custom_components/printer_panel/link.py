"""One printer in Home Assistant: its entities (found again whenever the entity registry changes, so a rename is
followed), what the Printer page is told about it, the phone notifications when a print finishes, pauses, runs out of
filament or stops with an error, and the way to its Moonraker (for the pause at a line and the restart)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event

from .const import (CONF_DEVICE, CONF_EVENTS, CONF_NOTIFY, CONF_TITLE, COUNT_SUFFIX, DEFAULT_EVENTS, DEFAULT_TITLE,
                    DOMAIN, PAUSE_AT_LINE_SUFFIX, RESTART_SUFFIX, SOURCE_DOMAIN)
from .linepause import LinePause
from .moonraker import Moonraker, MoonrakerError
from .printer import filament_event, message, print_event, print_name, resolve

_LOGGER = logging.getLogger(__name__)


class PrinterLink:
    """The printer behind one Printer Panel entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, path: str) -> None:
        self.hass = hass
        self.entry = entry
        self.path = path
        self.map = self._resolve()
        self._unwatch: CALLBACK_TYPE | None = None
        self._missing_targets: set[str] = set()
        self.line_pause = LinePause(self)

    @property
    def device_id(self) -> str:
        return str(self.entry.data[CONF_DEVICE])

    @property
    def title(self) -> str:
        return str(self.entry.options.get(CONF_TITLE) or DEFAULT_TITLE)

    def _resolve(self) -> dict[str, Any]:
        registry = er.async_get(self.hass)
        return resolve({"entity_id": e.entity_id, "unique_id": e.unique_id, "translation_key": e.translation_key,
                        "disabled_by": e.disabled_by}
                       for e in er.async_entries_for_device(registry, self.device_id, include_disabled_entities=True))

    def host(self) -> str | None:
        """The printer's address, from the Creality integration's entry for its device (which follows the printer)."""
        device = dr.async_get(self.hass).async_get(self.device_id)
        if device is None:
            return None
        # a device belongs to one config entry from Home Assistant 2026.10 (config_entry_id); before, to a set of them
        entry_ids = [device.config_entry_id] if hasattr(device, "config_entry_id") else list(device.config_entries)
        for entry_id in entry_ids:
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry and entry.domain == SOURCE_DOMAIN and entry.data.get("host"):
                return str(entry.data["host"]).strip()
        return None

    def moonraker(self) -> Moonraker:
        if not (host := self.host()):
            raise MoonrakerError("no_host")
        return Moonraker(async_get_clientsession(self.hass), host)

    def _own(self) -> dict[str, str]:
        """This integration's own entities on the printer: Restart printer, Pause at G-code line, Count G-code lines
        (unless disabled)."""
        registry, found = er.async_get(self.hass), {}
        for what, platform, suffix in (("restart", "button", RESTART_SUFFIX), ("pause_at_line", "number", PAUSE_AT_LINE_SUFFIX),
                                       ("count_lines", "switch", COUNT_SUFFIX)):
            entity_id = registry.async_get_entity_id(platform, DOMAIN, f"{self.device_id}_{suffix}")
            entry = registry.async_get(entity_id) if entity_id else None
            if entry and not entry.disabled_by:
                found[what] = entry.entity_id
        return found

    def describe(self) -> dict[str, Any]:
        """What the page needs to draw this printer: its entities, the CFS boxes and slots, and its names."""
        device = dr.async_get(self.hass).async_get(self.device_id)
        return {"entry_id": self.entry.entry_id, "title": self.title, "path": self.path, "device_id": self.device_id,
                "name": (device.name_by_user or device.name) if device else None, "model": device.model if device else None,
                **self.map, "entities": {**self.map["entities"], **self._own()}}

    @callback
    def async_start(self) -> CALLBACK_TYPE:
        """Follow the printer's status and filament for notifications, and its entities for renames. Returns the stop."""
        self._watch()
        stop_registry = self.hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, self._registry_changed)

        @callback
        def stop() -> None:
            stop_registry()
            self.line_pause.stop()
            if self._unwatch:
                self._unwatch()
                self._unwatch = None

        return stop

    @callback
    def _registry_changed(self, _event: Event) -> None:
        fresh = self._resolve()
        if fresh != self.map:
            self.map = fresh
            self._watch()

    @callback
    def _watch(self) -> None:
        if self._unwatch:
            self._unwatch()
            self._unwatch = None
        ids = [i for i in (self.map["entities"].get("status"), self.map["entities"].get("filament_status")) if i]
        if ids:
            self._unwatch = async_track_state_change_event(self.hass, ids, self._changed)

    @callback
    def _changed(self, event: Event[EventStateChangedData]) -> None:
        old, new = event.data["old_state"], event.data["new_state"]
        before, after = (old.state if old else None), (new.state if new else None)
        if event.data["entity_id"] == self.map["entities"].get("status"):
            what = print_event(before, after)
            if after in ("completed", "stopped", "error", "idle"):
                self.line_pause.forget_lines()
        else:
            what = filament_event(before, after)
        line = self.line_pause.take_fired() if what == "paused" else None
        if what and what in (self.entry.options.get(CONF_EVENTS) or DEFAULT_EVENTS) and self.entry.options.get(CONF_NOTIFY):
            self.hass.async_create_task(self._notify(what, line), f"printer_panel {what}")

    def _state(self, what: str):
        entity_id = self.map["entities"].get(what)
        return self.hass.states.get(entity_id) if entity_id else None

    def _picture(self) -> str | None:
        """The notification's picture: the print's own (the slicer's picture of the model), which loads whenever there is
        a print; else the camera's still, unless the Creality integration says the camera cannot take one. Not the camera
        first: a WebRTC camera's still comes through go2rtc and can take longer than the ten seconds Home Assistant gives
        it, and a phone that cannot fetch the picture shows none. An image entity's state is when its picture last
        changed, so after a restart it is unknown while the picture is there."""
        preview = self._state("preview")
        if preview and preview.state != STATE_UNAVAILABLE:
            return f"/api/image_proxy/{preview.entity_id}"
        camera = self._state("camera")
        if camera and camera.state != STATE_UNAVAILABLE and camera.attributes.get("snapshot_supported") is not False:
            return f"/api/camera_proxy/{camera.entity_id}"
        return None

    def notification(self, what: str, line: int | None = None) -> dict[str, Any]:
        """The notification for an event: its title, text and the phone app's extras (a picture of the print, and a tap
        that opens the Printer page). A pause this integration made at a line says the line."""
        status, material = self._state("status"), self._state("material")
        name = print_name(status.attributes.get("file") if status else None) \
            or print_name(material.attributes.get("gcode_file") if material else None)
        progress_state = self._state("progress")
        progress = progress_state.state if progress_state else (status.attributes.get("progress") if status else None)
        job_state = self._state("job_time")
        job = job_state.state if job_state else (status.attributes.get("job_time_s") if status else None)
        title, text = message("paused_line" if what == "paused" and line else what, self.hass.config.language, name,
                              progress, job, line)
        data: dict[str, Any] = {"tag": f"printer_panel_{self.entry.entry_id}", "group": "printer",
                                "clickAction": f"/{self.path}", "url": f"/{self.path}"}
        if picture := self._picture():
            data["image"] = picture
        return {"title": title, "message": text, "data": data}

    async def _notify(self, what: str, line: int | None = None) -> None:
        payload = self.notification(what, line)
        for target in self.entry.options.get(CONF_NOTIFY) or []:
            if not self.hass.services.has_service("notify", target):
                if target not in self._missing_targets:
                    self._missing_targets.add(target)
                    _LOGGER.warning("Printer Panel: notify.%s does not exist; the %s notification was not sent there", target, what)
                continue
            self._missing_targets.discard(target)
            try:
                await self.hass.services.async_call("notify", target, payload, blocking=True)
            except Exception as err:  # noqa: BLE001  (one phone failing must not stop the others)
                _LOGGER.warning("Printer Panel: notify.%s refused the %s notification: %s", target, what, err)
