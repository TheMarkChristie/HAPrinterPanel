"""The filament register, with no Home Assistant in it (tested on its own). Mark, 25 Oct 2026: "a filament register where
we check in the filament that we have and how much is in it, then at the end of each print take out that amount from
the register. When we check it in we will check in the Brand, Colour, Type and weight", and "make it read from the CFS,
we can have a stock number written on it so we can confirm before or after the print".

- A spool is checked in with its brand, colour (a name and the colour itself), type and the weight of filament on its
  label (what is left, for a part-used one), and gets the next stock number, F001, F002 and on, never used twice, to
  write on the spool.
- Which spool is in which slot is read from the CFS. A Creality spool's chip tells the CFS its colour and type, so when
  exactly one spool in the register is a Creality spool of that type and colour it is the one. Any other spool (the CFS
  calls it Generic), or two that look alike, waits for its stock number, confirmed before the print or after it. A slot
  that is emptied, or gets a different spool, starts again.
- While a print runs, the printer's own count of the filament it has used goes up; each step is booked to the slot
  printing at the time. When the print ends, finished or stopped, each slot's length is weighed (1.75 mm filament at
  its type's density) and comes off its spool, or waits on the slot until its stock number is confirmed.
"""
from __future__ import annotations

import math
import re
from typing import Any

DIAMETER_MM = 1.75
# g/cm3, the first that fits wins (so PLA-CF before PLA, PETG before PET)
DENSITIES = (("PLA-CF", 1.29), ("PETG-CF", 1.30), ("PA-CF", 1.20), ("PETG", 1.27), ("PET", 1.38), ("PLA", 1.24),
             ("ABS", 1.04), ("ASA", 1.07), ("TPU", 1.21), ("PC", 1.20), ("PA", 1.14), ("NYLON", 1.14), ("PVA", 1.23),
             ("HIPS", 1.04))
DEFAULT_DENSITY = 1.24
COLOUR_NEAR = 48            # RGB distance within which a Creality spool's colour is the CFS's
MAX_WEIGHT = 10000          # g; a 10 kg spool is the largest anyone checks in
UNKNOWN_SLOT = "?"          # where grams go while the printer does not say which slot is printing
HEX = re.compile(r"^#?([0-9a-f]{6})(?:[0-9a-f]{2})?$", re.I)
SLOT_STATE = re.compile(r"box\D*(\d+)\D*slot\D*(\d+)", re.I)


def colour_hex(value: Any) -> str | None:
    """'#FF37AF', '#9E007EFF' (with alpha) or 'ff37af' -> '#ff37af'; anything else None."""
    m = HEX.match(str(value or "").strip())
    return f"#{m.group(1).lower()}" if m else None


def slot_label(state: Any) -> str | None:
    """The Creality integration's active slot ('box_1_slot_2', slots counted from 1) -> '1B'; 'external' -> 'Ext'."""
    value = str(state or "")
    if m := SLOT_STATE.search(value):
        n = int(m.group(2))
        return f"{int(m.group(1))}{chr(64 + n)}" if 1 <= n <= 26 else None
    return "Ext" if value.lower().startswith("ext") else None


def base_type(material: Any) -> str:
    """'Hyper PLA' -> 'PLA', 'PETG-CF' -> 'PETG-CF': the type the density goes by."""
    text = re.sub(r"\s+", "", str(material or "").upper())
    return next((key for key, _ in DENSITIES if key in text), text)


def density(material: Any) -> float:
    key = base_type(material)
    return next((d for k, d in DENSITIES if k == key), DEFAULT_DENSITY)


def grams(mm: float, material: Any) -> float:
    """The weight of mm of 1.75 mm filament of a type."""
    return max(0.0, mm) * math.pi * (DIAMETER_MM / 2) ** 2 / 1000.0 * density(material)


def _near(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    ra, rb = (tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) for h in (a, b))
    return math.dist(ra, rb) <= COLOUR_NEAR


def slot_key(info: dict[str, Any] | None) -> str | None:
    """What the CFS says is in a slot, as one string: a different spool (or none) gives a different one."""
    if not info or not info.get("loaded"):
        return None
    return "|".join(str(info.get(k) or "") for k in ("vendor", "type", "name", "hex", "rfid", "state"))


class RegisterError(ValueError):
    """A request the register says no to: key is not_found or invalid, detail says why."""

    def __init__(self, key: str, detail: str) -> None:
        super().__init__(detail)
        self.key = key


class Register:
    """The spools, which slot holds which, what is waiting for a stock number, and the print under way."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        data = data or {}
        self.next = int(data.get("next") or 1)
        self.spools: list[dict[str, Any]] = [dict(s) for s in data.get("spools") or []]
        self.slots: dict[str, dict[str, Any]] = {k: dict(v) for k, v in (data.get("slots") or {}).items()}
        self.pending: dict[str, dict[str, Any]] = {k: dict(v) for k, v in (data.get("pending") or {}).items()}
        self.job: dict[str, Any] | None = dict(data["job"]) if data.get("job") else None

    def to_dict(self) -> dict[str, Any]:
        return {"next": self.next, "spools": self.spools, "slots": self.slots, "pending": self.pending, "job": self.job}

    # ------------------------------------------------------------------ spools
    def spool(self, stock: Any) -> dict[str, Any] | None:
        wanted = str(stock or "").strip().upper()
        return next((s for s in self.spools if s["stock"] == wanted), None)

    def _need(self, stock: Any) -> dict[str, Any]:
        if (spool := self.spool(stock)) is None:
            raise RegisterError("not_found", f"No spool {str(stock or '').strip().upper() or '(none)'} in the register")
        return spool

    @staticmethod
    def _text(value: Any, what: str, required: bool = True) -> str:
        text = " ".join(str(value or "").split())[:60]
        if required and not text:
            raise RegisterError("invalid", f"The {what} is missing")
        return text

    @staticmethod
    def _weight(value: Any, what: str) -> float:
        try:
            grams_ = round(float(value), 1)
        except (TypeError, ValueError):
            raise RegisterError("invalid", f"The {what} is not a number") from None
        if not 0 <= grams_ <= MAX_WEIGHT:
            raise RegisterError("invalid", f"The {what} should be between 0 and {MAX_WEIGHT} g")
        return grams_

    def check_in(self, brand: Any, colour: Any, hex_: Any, material: Any, weight: Any, day: str) -> dict[str, Any]:
        """A new spool, with the next stock number."""
        weight_g = self._weight(weight, "weight")
        if weight_g <= 0:
            raise RegisterError("invalid", "The weight should be more than 0 g")
        spool = {"stock": f"F{self.next:03d}", "brand": self._text(brand, "brand"), "colour": self._text(colour, "colour", False),
                 "hex": colour_hex(hex_) or "#808080", "type": self._text(material, "type"), "weight": weight_g,
                 "left": weight_g, "checked_in": day}
        self.next += 1
        self.spools.append(spool)
        return spool

    def update(self, stock: Any, fields: dict[str, Any]) -> dict[str, Any]:
        spool = self._need(stock)
        if "brand" in fields:
            spool["brand"] = self._text(fields["brand"], "brand")
        if "colour" in fields:
            spool["colour"] = self._text(fields["colour"], "colour", False)
        if "hex" in fields and colour_hex(fields["hex"]):
            spool["hex"] = colour_hex(fields["hex"])
        if "type" in fields:
            spool["type"] = self._text(fields["type"], "type")
        if "weight" in fields:
            spool["weight"] = self._weight(fields["weight"], "weight")
        if "left" in fields:
            spool["left"] = self._weight(fields["left"], "weight left")
        return spool

    def remove(self, stock: Any) -> None:
        spool = self._need(stock)
        self.spools.remove(spool)
        for slot in self.slots.values():
            if slot.get("stock") == spool["stock"]:
                slot.pop("stock", None)
                slot.pop("how", None)

    def where(self, stock: str) -> str | None:
        return next((label for label, s in self.slots.items() if s.get("stock") == stock), None)

    # ------------------------------------------------------------------ the CFS
    def slot_seen(self, label: str, info: dict[str, Any] | None) -> bool:
        """The CFS's word on a slot ({loaded, vendor, type, name, hex, rfid, state}, or None): a different spool, or
        none, drops the stock number the slot had, and a Creality spool is matched again. True when something changed."""
        key = slot_key(info)
        slot = self.slots.get(label) or {}
        if slot and slot.get("key") == key:
            return False
        fresh: dict[str, Any] = {"key": key, "type": (info or {}).get("type") or ""} if key else {}
        if key and (stock := self.match(label, info or {})):
            fresh.update(stock=stock, how="auto")
        if fresh:
            self.slots[label] = fresh
        else:
            self.slots.pop(label, None)
        return True

    def match(self, label: str, info: dict[str, Any]) -> str | None:
        """The one Creality spool in the register of the CFS's type and colour, not in another slot and not empty."""
        if "creality" not in str(info.get("vendor") or "").lower():
            return None
        elsewhere = {s.get("stock") for k, s in self.slots.items() if k != label}
        found = [s for s in self.spools
                 if "creality" in s["brand"].lower() and base_type(s["type"]) == base_type(info.get("type"))
                 and _near(s["hex"], colour_hex(info.get("hex"))) and s["left"] > 0 and s["stock"] not in elsewhere]
        return found[0]["stock"] if len(found) == 1 else None

    def confirm(self, label: str, stock: Any) -> float:
        """The stock number written on the spool in a slot (None or '' clears it). What the slot used and was waiting
        comes off that spool; if the spool it waits for has since left the slot, the number given is that one's, so it
        is booked but not put in the slot, and so are grams from a slot that was not known. Returns the grams booked."""
        slot = self.slots.get(label) or {"key": None, "type": ""}
        if not str(stock or "").strip():
            slot.pop("stock", None)
            slot.pop("how", None)
            if slot.get("key"):
                self.slots[label] = slot
            return 0.0
        spool = self._need(stock)
        waiting = self.pending.pop(label, None)
        if label != UNKNOWN_SLOT and (not waiting or waiting.get("key") == slot.get("key")):
            for other, s in self.slots.items():
                if other != label and s.get("stock") == spool["stock"]:
                    s.pop("stock", None)
                    s.pop("how", None)
            self.slots[label] = {**slot, "stock": spool["stock"], "how": "confirmed"}
        if not waiting:
            return 0.0
        used = grams(float(waiting.get("mm") or 0), spool["type"])
        spool["left"] = round(max(0.0, spool["left"] - used), 1)
        return used

    def forget(self, label: str) -> float:
        """What waits on a slot for a stock number, dropped: it came from a spool not in the register. Returns the grams."""
        waiting = self.pending.pop(label, None)
        if not waiting:
            raise RegisterError("not_found", f"Nothing waits on slot {label}")
        return grams(float(waiting.get("mm") or 0), (self.slots.get(label) or {}).get("type") or waiting.get("type"))

    # ------------------------------------------------------------------ prints
    def track(self, file: str, used_mm: float, active: str | None) -> list[dict[str, Any]]:
        """The printer's count of filament used in the print under way, and the slot printing now. A new file, or the
        count going back to the start (the same file printed again), ends the print before it. Returns what an ended
        print booked ([] usually)."""
        booked: list[dict[str, Any]] = []
        job = self.job
        if job is not None and (job.get("file") != file or used_mm < float(job.get("last") or 0) - 1.0):
            booked = self.end()
            job = None
        if job is None:
            # counted from 0, so a print's first reading (often a few cm already) is booked too
            self.job = job = {"file": file, "last": 0.0, "used": {}}
        if active and not job.get("active") and UNKNOWN_SLOT in job["used"]:
            # the printer says which slot only about a minute into a print: what the start (the purge line) used is
            # the first slot's it names
            job["used"][active] = round(float(job["used"].get(active) or 0) + job["used"].pop(UNKNOWN_SLOT), 1)
        delta = used_mm - float(job.get("last") or 0)
        if delta > 0:
            where = active or job.get("active") or UNKNOWN_SLOT
            job["used"][where] = round(float(job["used"].get(where) or 0) + delta, 1)
        if active:
            job["active"] = active
        job["last"] = used_mm
        return booked

    def end(self) -> list[dict[str, Any]]:
        """The print is over: each slot's length off its spool, or onto what waits for the slot's stock number."""
        job, self.job = self.job, None
        booked: list[dict[str, Any]] = []
        for label, mm in sorted((job or {}).get("used", {}).items()):
            if mm <= 0:
                continue
            slot = self.slots.get(label) or {}
            spool = self.spool(slot.get("stock")) if slot.get("stock") else None
            if spool is not None:
                used = grams(mm, spool["type"])
                spool["left"] = round(max(0.0, spool["left"] - used), 1)
                booked.append({"slot": label, "stock": spool["stock"], "grams": round(used, 1)})
            else:
                waiting = self.pending.setdefault(label, {"mm": 0.0, "type": slot.get("type") or "", "key": slot.get("key")})
                # grams an earlier spool in this slot left unconfirmed join these: the number given takes them all
                waiting["key"] = slot.get("key")
                waiting["mm"] = round(float(waiting["mm"]) + mm, 1)
                booked.append({"slot": label, "stock": None, "grams": round(grams(mm, slot.get("type")), 1)})
        return booked

    # ------------------------------------------------------------------ the page
    def view(self) -> dict[str, Any]:
        """What the Printer page shows: the spools (with where each is), each slot's stock number, what waits for one,
        and the print under way so far, in grams."""
        def slot_type(label: str) -> str:
            slot = self.slots.get(label) or {}
            spool = self.spool(slot.get("stock")) if slot.get("stock") else None
            return spool["type"] if spool else slot.get("type") or ""

        return {
            "spools": [{**s, "slot": self.where(s["stock"])} for s in sorted(self.spools, key=lambda s: s["stock"])],
            "slots": {k: {"stock": v.get("stock"), "how": v.get("how")} for k, v in self.slots.items() if v.get("stock")},
            "pending": {k: round(grams(float(v.get("mm") or 0), slot_type(k) or v.get("type")), 1) for k, v in self.pending.items()},
            "printing": ({k: round(grams(mm, slot_type(k)), 1) for k, mm in self.job["used"].items()} if self.job else {}),
        }
