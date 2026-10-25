"""The filament register in Home Assistant: the Register (filament.py) kept in storage and fed by the Creality
integration's own entities: the print status (with the printer's count of the filament the print has used,
used_material_mm), the slot printing now, and each CFS slot's filament (vendor, type, name, colour, chip). Printer Panel
asks the printer nothing for it: the Creality integration follows the printer already. A printer that is off leaves the
slots as they were (its entities are unavailable, which says nothing about the spools in it)."""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Callable

from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, State, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .filament import Register, colour_hex, slot_key, slot_label

if TYPE_CHECKING:
    from .link import PrinterLink

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
UNDER_WAY = ("printing", "processing", "paused", "self-testing")
OVER = ("completed", "stopped", "error", "idle")
SAVE_DELAY = 10.0       # seconds: a print's count changes every few seconds, storage need not
TELL_EVERY = 10.0       # and the page is told at most this often while it does
NOT_THERE = ("unavailable", "unknown")


class FilamentRegister:
    """One printer's filament register."""

    def __init__(self, link: PrinterLink) -> None:
        self.link = link
        self.hass = link.hass
        self.book = Register()
        self._store: Store[dict[str, Any]] = Store(self.hass, STORE_VERSION, f"{DOMAIN}.{link.entry.entry_id}.filament")
        self._listeners: list[Callable[[], None]] = []
        self._unwatch: CALLBACK_TYPE | None = None
        self._told = 0.0

    async def async_load(self) -> None:
        self.book = Register(await self._store.async_load() or {})

    # ------------------------------------------------------------------ following the printer
    def _slot_entities(self) -> dict[str, str]:
        """Slot label -> the Creality integration's entity for its filament (the colour entity carries the same)."""
        found: dict[str, str] = {}
        for box in self.link.map.get("boxes") or []:
            for slot in box["slots"]:
                if entity := slot.get("filament") or slot.get("color"):
                    found[slot["label"]] = entity
        external = self.link.map.get("external") or {}
        if entity := external.get("filament") or external.get("color"):
            found["Ext"] = entity
        return found

    @staticmethod
    def slot_info(state: State | None) -> dict[str, Any] | None:
        """What the CFS says is in a slot, or None when it cannot say (the printer off, the integration starting)."""
        if state is None or state.state in NOT_THERE:
            return None
        a = state.attributes
        name = a.get("name") or (state.state if state.state not in ("", "-", "None") and not state.state.startswith("#") else "")
        hex_ = colour_hex(a.get("color_hex")) or colour_hex(state.state)
        return {"loaded": bool(name or hex_), "vendor": a.get("vendor") or "", "type": a.get("type") or "", "name": name,
                "hex": hex_ or "", "rfid": a.get("rfid") or "", "state": a.get("state")}

    @callback
    def start(self) -> CALLBACK_TYPE:
        """Follow the printer; take up a print that was under way when Home Assistant stopped. Returns the stop."""
        self._watch()
        self._sync()
        return self.stop

    @callback
    def stop(self) -> None:
        if self._unwatch:
            self._unwatch()
            self._unwatch = None

    @callback
    def restart(self) -> None:
        """The printer's entities changed (a rename, a CFS box added): follow the new ones."""
        self._watch()
        self._sync()

    @callback
    def _watch(self) -> None:
        self.stop()
        entities = self.link.map["entities"]
        ids = [i for i in (entities.get("status"), entities.get("active_slot")) if i] + list(self._slot_entities().values())
        if ids:
            self._unwatch = async_track_state_change_event(self.hass, ids, self._changed)

    @callback
    def _sync(self) -> None:
        changed = False
        for label, entity_id in self._slot_entities().items():
            info = self.slot_info(self.hass.states.get(entity_id))
            if info is not None:
                changed |= self.book.slot_seen(label, info)
        status = self.hass.states.get(self.link.map["entities"].get("status") or "")
        if status is not None:
            changed |= self._status(status)
        if changed:
            self._save()
            self._tell(now=True)

    @callback
    def _changed(self, event: Event[EventStateChangedData]) -> None:
        entity_id, new = event.data["entity_id"], event.data["new_state"]
        if entity_id == self.link.map["entities"].get("status"):
            if new is not None and self._status(new):
                self._save()
                self._tell()
            return
        label = next((k for k, v in self._slot_entities().items() if v == entity_id), None)
        if label is None:
            return  # the slot printing now: read whenever the count moves
        info = self.slot_info(new)
        if info is not None and self.book.slot_seen(label, info):
            self._save()
            self._tell(now=True)

    def _active(self) -> str | None:
        state = self.hass.states.get(self.link.map["entities"].get("active_slot") or "")
        return slot_label(state.state) if state is not None else None

    @callback
    def _status(self, state: State) -> bool:
        """The print status: while a print is under way, book its count to the slot printing; when it is over, book the
        print. True when the register changed."""
        a = state.attributes
        file = str(a.get("file") or "")
        try:
            used = float(a["used_material_mm"]) if a.get("used_material_mm") is not None else None
        except (TypeError, ValueError):
            used = None
        if state.state in UNDER_WAY and file and used is not None:
            self._log(self.book.track(file, used, self._active()))
            return True
        if state.state in OVER and self.book.job:
            if used is not None and file == self.book.job.get("file"):
                self.book.track(file, used, self._active())   # the count the print ended on
            self._log(self.book.end())
            return True
        return False

    def _log(self, booked: list[dict[str, Any]]) -> None:
        for b in booked:
            if b["stock"]:
                _LOGGER.info("Printer Panel: the print used %.1f g from %s (slot %s)", b["grams"], b["stock"], b["slot"])
            else:
                _LOGGER.info("Printer Panel: the print used %.1f g from slot %s; it waits for the spool's stock number",
                             b["grams"], b["slot"])

    # ------------------------------------------------------------------ storage and the page
    @callback
    def _save(self) -> None:
        self._store.async_delay_save(self.book.to_dict, SAVE_DELAY)

    async def _save_now(self) -> None:
        await self._store.async_save(self.book.to_dict())

    async def async_remove(self) -> None:
        await self._store.async_remove()

    @callback
    def listen(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def _tell(self, now: bool = False) -> None:
        moment = time.monotonic()
        if not now and moment - self._told < TELL_EVERY:
            return
        self._told = moment
        for listener in list(self._listeners):
            listener()

    def view(self) -> dict[str, Any]:
        return self.book.view()

    # ------------------------------------------------------------------ what the page asks
    async def check_in(self, brand: Any, colour: Any, hex_: Any, material: Any, weight: Any) -> dict[str, Any]:
        spool = self.book.check_in(brand, colour, hex_, material, weight, dt_util.now().date().isoformat())
        self._rematch()
        await self._save_now()
        self._tell(now=True)
        return {**spool, "slot": self.book.where(spool["stock"])}

    async def update(self, stock: Any, fields: dict[str, Any]) -> dict[str, Any]:
        spool = self.book.update(stock, fields)
        self._rematch()
        await self._save_now()
        self._tell(now=True)
        return {**spool, "slot": self.book.where(spool["stock"])}

    async def remove(self, stock: Any) -> None:
        self.book.remove(stock)
        self._rematch()
        await self._save_now()
        self._tell(now=True)

    async def confirm(self, label: str, stock: Any) -> float:
        used = self.book.confirm(label, stock)
        if used:
            _LOGGER.info("Printer Panel: %.1f g that slot %s used came off %s", used, label, str(stock).upper())
        await self._save_now()
        self._tell(now=True)
        return used

    def _rematch(self) -> None:
        """A Creality spool checked in (or changed) while it sits in the CFS is matched to its slot at once."""
        for label, entity_id in self._slot_entities().items():
            info = self.slot_info(self.hass.states.get(entity_id))
            slot = self.book.slots.get(label)
            if info is None or not slot or slot.get("stock") or slot.get("key") != slot_key(info):
                continue
            if stock := self.book.match(label, info):
                slot.update(stock=stock, how="auto")
