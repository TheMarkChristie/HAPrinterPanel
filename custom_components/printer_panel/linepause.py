"""Count G-code lines, and pause at one. While counting is on (the Count G-code lines switch), Printer Panel follows where
the printer is in the file it is printing, through its Moonraker: the page's "Line X of Y", and Pause at G-code line,
which presses the printer's own Pause once it has read the line. While counting is off it asks the printer nothing (Mark,
18 Oct 2026). On the way to a line it looks every 5 minutes while the line is more than 10 minutes off, then more often
the nearer it gets, every second for the last 20 seconds (gcode.next_look), so the pause comes about a second after the
line. The switch and the line are kept in storage, so Home Assistant restarting mid-print keeps them; the print ending,
or another one starting, drops the line."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import TYPE_CHECKING, Any, Callable

from homeassistant.core import CALLBACK_TYPE, HassJob, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .gcode import LineIndex, next_look
from .moonraker import MoonrakerError, Place

if TYPE_CHECKING:
    from .link import PrinterLink

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
UNDER_WAY = ("printing", "paused")   # Moonraker's print states while there is a print
WHILE_PAUSED = 60.0                  # seconds between looks while the print is paused short of the line
AFTER_FAILURE = 10.0                 # and after a look that could not reach the printer
MIN_PACE = 200.0                     # bytes a second assumed at least, so a fast stretch is not slept through
FRESH = 1.5                          # a look this recent also answers the page
FIRE_TRIES = 4                       # presses of Pause before giving up
TOLD_WITHIN = 120.0                  # seconds in which the printer's pause is the one asked for, for the notification


def moonraker_error(err: MoonrakerError) -> HomeAssistantError:
    """A Moonraker failure as the error a service call shows."""
    return HomeAssistantError(translation_domain=DOMAIN, translation_key=f"moonraker_{err.key}",
                              translation_placeholders={"detail": err.detail or err.key})


class LinePause:
    """One printer's pause at a line."""

    def __init__(self, link: PrinterLink) -> None:
        self.link = link
        self.hass = link.hass
        self.counting = False            # the Count G-code lines switch
        self.target: int | None = None   # the line, counted from 1
        self.file: str | None = None     # the print it is for
        self._end: int | None = None     # the position at which the printer has read the line
        self._fired: tuple[int, float] | None = None
        self._index: tuple[str, int, LineIndex] | None = None
        self._index_lock = asyncio.Lock()
        self._place: Place | None = None
        self._seen = 0.0
        self._paces: deque[float] = deque(maxlen=8)
        self._unsub: CALLBACK_TYPE | None = None
        self._listeners: list[Callable[[], None]] = []
        self._failures = 0
        self._fire_tries = 0
        self._store: Store[dict[str, Any]] = Store(self.hass, STORE_VERSION, f"{DOMAIN}.{link.entry.entry_id}.line_pause")
        self._job = HassJob(self._poll_later, f"{DOMAIN} line pause", cancel_on_shutdown=True)

    async def async_load(self) -> None:
        """Take up the switch, and a line set before Home Assistant restarted: the first look checks it is still the
        same print."""
        data = await self._store.async_load() or {}
        line, file = data.get("line"), data.get("file")
        self.counting = bool(data.get("counting"))
        if isinstance(line, int) and line > 0 and file:
            self.counting, self.target, self.file = True, line, str(file)
            self._schedule(0)
        self._changed()

    async def set_counting(self, on: bool) -> None:
        """The Count G-code lines switch. Off drops a line set to pause at, and asks the printer nothing more."""
        if on == self.counting:
            return
        self.counting = on
        if not on:
            self.forget_lines()
            if self.target is not None:
                _LOGGER.info("Printer Panel: counting is off, so the pause at line %s is dropped", self.target)
                self.stop()
                self.target = self.file = self._end = None
        await self._save()
        self._changed()

    async def _save(self) -> None:
        if not self.counting and self.target is None:
            await self._store.async_remove()
        else:
            await self._store.async_save({"counting": self.counting, "line": self.target, "file": self.file})

    @callback
    def stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def listen(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def forget_lines(self) -> None:
        """The print is over: let its lines go (about 4 MB for a 13 MB file)."""
        self._index = None

    @callback
    def take_fired(self) -> int | None:
        """The line the printer had reached when this paused it, if that was just now; once."""
        fired, self._fired = self._fired, None
        return fired[0] if fired and time.monotonic() - fired[1] <= TOLD_WITHIN else None

    def _changed(self) -> None:
        for listener in list(self._listeners):
            listener()

    async def look(self, fresh: float = 0) -> Place:
        """Where the printer is: a look at most `fresh` seconds old, else a new one (which also measures the pace)."""
        now = time.monotonic()
        if self._place is not None and fresh and now - self._seen <= fresh:
            return self._place
        place = await self.link.moonraker().place()
        before, then = self._place, self._seen
        if before is not None and before.file != place.file:
            self._paces.clear()
        elif before is not None and place.position > before.position and now - then >= 0.2:
            self._paces.append((place.position - before.position) / (now - then))
        self._place, self._seen = place, now
        return place

    async def lines(self, place: Place) -> LineIndex:
        """The print's lines, read from the printer once per file."""
        async with self._index_lock:
            if self._index is not None and self._index[:2] == (place.file, place.size):
                return self._index[2]
            index = await self.link.moonraker().index(place.file)
            self._index = (place.file, place.size, index)
            return index

    async def arm(self, line: int) -> None:
        """Pause when the printer has read this line (counted from 1); 0 drops the pause. Turns counting on. Says why not
        when it cannot: nothing printing, the line already printed, a line past the end, the printer out of reach."""
        if line < 1:
            await self.disarm()
            return
        place, index = await self._checked_place()
        if line > index.lines:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="line_beyond",
                                     translation_placeholders={"line": str(line), "lines": str(index.lines)})
        at = index.read_up_to(place.position)
        if at >= line:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="line_passed",
                                     translation_placeholders={"line": str(line), "at": str(at)})
        self.counting, self.target, self.file, self._end = True, line, place.file, index.end_of(line)
        self._failures = self._fire_tries = 0
        await self._save()
        _LOGGER.info("Printer Panel: will pause at line %s of %s (the printer is at line %s)", line, index.lines, at)
        self._changed()
        self._plan(place)

    async def _checked_place(self) -> tuple[Place, LineIndex]:
        try:
            place = await self.look()
            if place.state not in UNDER_WAY or not place.file:
                raise HomeAssistantError(translation_domain=DOMAIN, translation_key="not_printing")
            return place, await self.lines(place)
        except MoonrakerError as err:
            raise moonraker_error(err) from err

    async def disarm(self) -> None:
        self.stop()
        if self.target is None and self.file is None:
            return
        self.target = self.file = self._end = None
        await self._save()
        self._changed()

    @callback
    def _schedule(self, delay: float) -> None:
        self.stop()
        if self.target is not None:
            self._unsub = async_call_later(self.hass, delay, self._job)

    async def _poll_later(self, _now: Any = None) -> None:
        self._unsub = None
        if self.target is None:
            return
        try:
            await self._poll()
        except Exception:  # noqa: BLE001  (the watch must not end quietly)
            _LOGGER.exception("Printer Panel: watching for line %s failed; looking again", self.target)
            self._schedule(AFTER_FAILURE)

    async def _poll(self) -> None:
        try:
            place = await self.look()
            index = await self.lines(place) if place.state in UNDER_WAY and place.file == self.file else None
        except MoonrakerError as err:
            self._failures += 1
            if self._failures == 3:
                _LOGGER.warning("Printer Panel: cannot see where the printer is (%s); still watching for line %s",
                                err.detail or err.key, self.target)
            self._schedule(AFTER_FAILURE)
            return
        self._failures = 0
        if index is None:
            _LOGGER.info("Printer Panel: the print ended or changed; the pause at line %s is dropped", self.target)
            self.forget_lines()
            await self.disarm()
            return
        if self._end is None:  # taken up after a restart
            if self.target is None or self.target > index.lines:
                await self.disarm()
                return
            self._end = index.end_of(self.target)
        if place.position >= self._end:
            if place.state == "printing":
                await self._fire(index.read_up_to(place.position))
            else:  # paused by hand at or after the line: nothing left to do
                await self.disarm()
            return
        self._plan(place)

    @callback
    def _plan(self, place: Place) -> None:
        """The next look, from this one: a minute while the print is paused short of the line (waiting for the resume),
        else by how far off the line is in time."""
        if place.state != "printing" or self._end is None:
            self._schedule(WHILE_PAUSED)
        else:
            self._schedule(next_look((self._end - place.position) / self._pace(place)))

    def _pace(self, place: Place) -> float:
        """Bytes a second, on the fast side, so the line is not slept past: the fastest of the paces seen between recent
        looks and the print's own average, and at least MIN_PACE."""
        average = place.position / place.printing_for if place.printing_for > 0 else 0.0
        return max(MIN_PACE, average, *self._paces)

    async def _fire(self, at: int) -> None:
        pause = self.link.map["entities"].get("pause")
        try:
            if not pause:
                raise HomeAssistantError("the printer has no Pause button")
            await self.hass.services.async_call("button", "press", {"entity_id": pause}, blocking=True)
        except Exception as err:  # noqa: BLE001  (try again: the printer is past the line already)
            self._fire_tries += 1
            _LOGGER.error("Printer Panel: could not pause at line %s (try %s of %s): %s", self.target, self._fire_tries,
                          FIRE_TRIES, err)
            if self._fire_tries < FIRE_TRIES:
                self._schedule(1.0)
                return
        else:
            self._fired = (at, time.monotonic())
            _LOGGER.info("Printer Panel: paused at line %s (asked for line %s)", at, self.target)
        await self.disarm()

    async def position(self) -> dict[str, Any]:
        """For the page: the line the printer is at, of how many, the line it will pause at, and in about how long.
        Nothing is asked of the printer while counting is off."""
        if not self.counting:
            return {"counting": False, "target": None}
        out: dict[str, Any] = {"counting": True, "available": False, "target": self.target}
        try:
            place = await self.look(FRESH)
            if place.state not in UNDER_WAY or not place.file:
                self.forget_lines()
                return {**out, "available": True, "state": place.state}
            index = await self.lines(place)
        except MoonrakerError as err:
            return {**out, "error": err.key}
        eta = None
        if self.target and self._end and place.state == "printing" and place.printing_for > 60 and place.position:
            eta = max(0.0, (self._end - place.position) / (place.position / place.printing_for))
        return {**out, "available": True, "state": place.state, "line": index.read_up_to(place.position),
                "lines": index.lines, "eta": eta}
