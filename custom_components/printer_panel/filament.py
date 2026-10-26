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
- A spool whose grams reach 0 (a print, or weighed empty) or that is taken out of the register has gone out of stock:
  noted with the day and why, kept a year, and the last 30 days are in the register's PDF ("a pdf with the list and
  what has gone out of stock recently").
- Mark asked for more the same evening: a spool's price (optional) gives each print a filament cost; a spool weighed on
  a scale, less the empty spool's weight (kept per brand), sets what is left; a print taking a spool to 10 % or less,
  or using it up, is an alert for the phones; and a spool can have an NFC tag the CFS reads, written with a phone app,
  whose colour is the spool's own nudged by a few shades no one can see, so the CFS tells every tagged spool apart
  (its telemetry carries no tag serial: two tags of the same material and colour look the same).
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta
from typing import Any, Callable

DIAMETER_MM = 1.75
# g/cm3, the first that fits wins (so PLA-CF before PLA, PETG before PET)
DENSITIES = (("PLA-CF", 1.29), ("PETG-CF", 1.30), ("PA-CF", 1.20), ("PETG", 1.27), ("PET", 1.38), ("PLA", 1.24),
             ("ABS", 1.04), ("ASA", 1.07), ("TPU", 1.21), ("PC", 1.20), ("PA", 1.14), ("NYLON", 1.14), ("PVA", 1.23),
             ("HIPS", 1.04))
DEFAULT_DENSITY = 1.24
COLOUR_NEAR = 48            # RGB distance within which a Creality spool's colour is the CFS's
MAX_WEIGHT = 10000          # g; a 10 kg spool is the largest anyone checks in
UNKNOWN_SLOT = "?"          # where grams go while the printer does not say which slot is printing
RESUME_GAP = 1000.0         # mm: a count that jumps back up to within this of the most it reached is a print resuming
RECENT_DAYS = 30            # "recently" gone out of stock, for the PDF
GONE_KEEP_DAYS = 365       # how long a spool gone out of stock is remembered
USED_UP, REMOVED, LOW = "used_up", "removed", "low"
LOW_SHARE = 0.10            # a spool with this share of its label's weight left, or less, is low
MAX_PRICE = 100000          # what a spool can have cost, in the house's currency
TAG_WEIGHTS = (250, 500, 600, 750, 1000)   # g: the weights a CFS tag can say
GENERIC_TAG = ("PLA", "PETG", "ABS", "ASA", "TPU")   # a type the CFS knows as Generic <type> for other brands' spools
TAG_SHIFT = 6               # a tag's colour is the spool's own within this much on each of red, green and blue
# the shifts a tag's colour can take, smallest first: never none, so a tag is never the colour of a Creality spool's chip
_SHIFTS = sorted(((r, g, b) for r in range(-TAG_SHIFT, TAG_SHIFT + 1) for g in range(-TAG_SHIFT, TAG_SHIFT + 1)
                  for b in range(-TAG_SHIFT, TAG_SHIFT + 1) if (r, g, b) != (0, 0, 0)),
                 key=lambda d: (d[0] ** 2 + d[1] ** 2 + d[2] ** 2, d))
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


def tag_colour(base: str, taken: set[str]) -> str:
    """A tag's colour: the spool's own, shifted by the smallest amount no other tag has."""
    r, g, b = (int(base[i:i + 2], 16) for i in (1, 3, 5))
    for dr, dg, db in _SHIFTS:
        c = (r + dr, g + dg, b + db)
        if all(0 <= v <= 255 for v in c) and (hex_ := "#%02x%02x%02x" % c) not in taken:
            return hex_
    raise RegisterError("invalid", "No tag colour is free near this one")


def tag_weight(weight: float) -> int:
    """The weight a tag says, the nearest it can (250 g, 500 g, 600 g, 750 g or 1 kg)."""
    return min(TAG_WEIGHTS, key=lambda w: (abs(w - weight), -w))


def tag_material(spool: dict[str, Any]) -> str:
    """The material to pick in the tag-writing app: a Creality spool's own product, another brand's Generic <type>."""
    kind = str(spool.get("type") or "").strip()
    if "creality" in str(spool.get("brand") or "").lower():
        return kind
    base = base_type(kind)
    return f"Generic {base}" if base in GENERIC_TAG else base


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
        self.gone: list[dict[str, Any]] = [dict(g) for g in data.get("gone") or []]
        self.tares: dict[str, float] = dict(data.get("tares") or {})      # brand (lower case) -> its empty spool, g
        self.last_print: dict[str, Any] | None = dict(data["last_print"]) if data.get("last_print") else None
        self.recent: dict[str, Any] | None = dict(data["recent"]) if data.get("recent") else None   # the print last ended: file, high
        self.alerts: list[dict[str, Any]] = []      # spools a print took low or used up, for the phones (not kept)
        self.today: Callable[[], str] = lambda: date.today().isoformat()
        self.now: Callable[[], str] = lambda: datetime.now().isoformat(timespec="minutes")

    def to_dict(self) -> dict[str, Any]:
        return {"next": self.next, "spools": self.spools, "slots": self.slots, "pending": self.pending, "job": self.job,
                "gone": self.gone, "tares": self.tares, "last_print": self.last_print, "recent": self.recent}

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

    @staticmethod
    def _price(value: Any) -> float | None:
        if value is None or str(value).strip() == "":
            return None
        try:
            price = round(float(value), 2)
        except (TypeError, ValueError):
            raise RegisterError("invalid", "The price is not a number") from None
        if not 0 <= price <= MAX_PRICE:
            raise RegisterError("invalid", f"The price should be between 0 and {MAX_PRICE}")
        return price

    @staticmethod
    def _cost(spool: dict[str, Any], used: float) -> float | None:
        """What grams of a spool cost, from its price for the label's weight; None when it has no price."""
        return used * spool["price"] / spool["weight"] if spool.get("price") is not None and spool["weight"] > 0 else None

    def check_in(self, brand: Any, colour: Any, hex_: Any, material: Any, weight: Any, day: str,
                 price: Any = None) -> dict[str, Any]:
        """A new spool, with the next stock number."""
        weight_g = self._weight(weight, "weight")
        if weight_g <= 0:
            raise RegisterError("invalid", "The weight should be more than 0 g")
        spool = {"stock": f"F{self.next:03d}", "brand": self._text(brand, "brand"), "colour": self._text(colour, "colour", False),
                 "hex": colour_hex(hex_) or "#808080", "type": self._text(material, "type"), "weight": weight_g,
                 "left": weight_g, "checked_in": day}
        if (price_ := self._price(price)) is not None:
            spool["price"] = price_
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
        if "price" in fields:
            if (price := self._price(fields["price"])) is None:
                spool.pop("price", None)
            else:
                spool["price"] = price
        if fields.get("tare") is not None:
            self.tares[spool["brand"].lower()] = self._weight(fields["tare"], "empty spool's weight")
        if fields.get("weighed") is not None:
            # weighed on a scale: what is left is the spool less an empty one of its brand
            weighed, tare = self._weight(fields["weighed"], "weighed spool"), self.tares.get(spool["brand"].lower())
            if tare is None:
                raise RegisterError("invalid", f"The weight of an empty {spool['brand']} spool is needed once")
            if weighed < tare:
                raise RegisterError("invalid", "The spool weighs less than an empty one")
            fields = {**fields, "left": round(weighed - tare, 1)}
        if "left" in fields:
            before, spool["left"] = spool["left"], self._weight(fields["left"], "weight left")
            if before > 0 and spool["left"] <= 0:
                self._gone(spool, USED_UP)
            elif spool["left"] > 0:
                self.gone = [g for g in self.gone if g["stock"] != spool["stock"]]  # weighed, and not empty after all
        return spool

    def remove(self, stock: Any) -> None:
        spool = self._need(stock)
        self.spools.remove(spool)
        if not any(g["stock"] == spool["stock"] for g in self.gone):     # one used up already says so
            self._gone(spool, REMOVED)
        for slot in self.slots.values():
            if slot.get("stock") == spool["stock"]:
                slot.pop("stock", None)
                slot.pop("how", None)

    def _take(self, spool: dict[str, Any], used: float) -> None:
        """A print's grams off a spool; one that runs out has gone out of stock. Taken low or used up, it is an alert."""
        before = spool["left"]
        spool["left"] = round(max(0.0, before - used), 1)
        if before > 0 and spool["left"] <= 0:
            self._gone(spool, USED_UP)
            self.alerts.append(self._alert(spool, USED_UP))
        elif spool["weight"] > 0 and before > spool["weight"] * LOW_SHARE >= spool["left"]:
            self.alerts.append(self._alert(spool, LOW))

    @staticmethod
    def _alert(spool: dict[str, Any], what: str) -> dict[str, Any]:
        return {"what": what, "stock": spool["stock"], "name": " ".join(filter(None, (spool["brand"], spool.get("colour")))),
                "type": spool["type"], "left": spool["left"],
                "share": round(spool["left"] / spool["weight"] * 100) if spool["weight"] > 0 else 0}

    def tag(self, stock: Any) -> dict[str, Any]:
        """What to write on a spool's NFC tag: its colour (the spool's own, a few shades off, given it once and kept), the
        material to pick and the weight a tag can say."""
        spool = self._need(stock)
        if not spool.get("tag"):
            spool["tag"] = tag_colour(spool["hex"], {s["tag"] for s in self.spools if s.get("tag")})
        return {"stock": spool["stock"], "tag": spool["tag"], "material": tag_material(spool), "weight": tag_weight(spool["weight"])}

    def _gone(self, spool: dict[str, Any], why: str) -> None:
        day = self.today()
        kept = (date.fromisoformat(day) - timedelta(days=GONE_KEEP_DAYS)).isoformat()
        self.gone = [g for g in self.gone if g["stock"] != spool["stock"] and g["out"] >= kept]
        self.gone.append({**{k: spool.get(k) for k in ("stock", "brand", "colour", "hex", "type", "weight", "checked_in")},
                          "out": day, "why": why})

    def gone_since(self, days: int = RECENT_DAYS) -> list[dict[str, Any]]:
        """The spools gone out of stock in the last days, the latest first."""
        since = (date.fromisoformat(self.today()) - timedelta(days=days)).isoformat()
        return sorted((g for g in self.gone if g["out"] > since), key=lambda g: (g["out"], g["stock"]), reverse=True)

    def where(self, stock: str) -> str | None:
        return next((label for label, s in self.slots.items() if s.get("stock") == stock), None)

    # ------------------------------------------------------------------ the CFS
    def slot_seen(self, label: str, info: dict[str, Any] | None) -> bool:
        """The CFS's word on a slot ({loaded, vendor, type, name, hex, rfid, state}, or None): a different spool, or
        none, drops the stock number the slot had, and a Creality spool is matched again. A number given while the CFS
        could not say what was in the slot (the printer off) is the spool it then reads. True when something changed."""
        key = slot_key(info)
        slot = self.slots.get(label) or {}
        if slot and slot.get("key") == key and (key or not slot.get("stock")):
            return False
        if key and slot.get("stock") and slot.get("key") is None:
            self.slots[label] = {**slot, "key": key, "type": (info or {}).get("type") or ""}
            return True
        fresh: dict[str, Any] = {"key": key, "type": (info or {}).get("type") or ""} if key else {}
        if key and (stock := self.match(label, info or {})):
            fresh.update(stock=stock, how="auto")
        if fresh:
            self.slots[label] = fresh
        else:
            self.slots.pop(label, None)
        return True

    def match(self, label: str, info: dict[str, Any]) -> str | None:
        """The spool whose tag the CFS read (its colour is that tag's own), whatever its brand; else the one Creality
        spool in the register of the CFS's type (or the product it names, Hyper Stardust say) and colour, not in another
        slot and not empty."""
        elsewhere = {s.get("stock") for k, s in self.slots.items() if k != label}
        read = colour_hex(info.get("hex"))
        tagged = [s for s in self.spools if read and s.get("tag") == read and s["stock"] not in elsewhere]
        if len(tagged) == 1:
            return tagged[0]["stock"]
        if "creality" not in str(info.get("vendor") or "").lower():
            return None
        product = str(info.get("name") or "").strip().lower()
        found = [s for s in self.spools
                 if "creality" in s["brand"].lower()
                 and (base_type(s["type"]) == base_type(info.get("type")) or (product and product in s["type"].lower()))
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
        self._take(spool, used)
        last = self.last_print
        if last and waiting.get("print") == last.get("ended") and (cost := self._cost(spool, used)) is not None:
            # grams the last print left waiting: now they have a spool, and so a price
            last["cost"] = round((last.get("cost") or 0) + cost, 2)
            last["uncosted"] = round(max(0.0, float(last.get("uncosted") or 0) - used), 1)
        return used

    def forget(self, label: str) -> float:
        """What waits on a slot for a stock number, dropped: it came from a spool not in the register. Returns the grams."""
        waiting = self.pending.pop(label, None)
        if not waiting:
            raise RegisterError("not_found", f"Nothing waits on slot {label}")
        return grams(float(waiting.get("mm") or 0), (self.slots.get(label) or {}).get("type") or waiting.get("type"))

    # ------------------------------------------------------------------ prints
    def track(self, file: str, used_mm: float, active: str | None) -> list[dict[str, Any]]:
        """The printer's count of filament used in the print under way, and the slot printing now. A new file ends the
        print before it. Returns what an ended print booked ([] usually).

        The count is the print's running total, and only what it adds is booked. Norway's K2 Plus on 26 Oct 2026, a
        print going wrong: error, paused, idle and printing again a dozen times, and two restarts of the printer. After
        each the count reads 0 for a moment, then jumps back up to where it was (75 m): that jump is the print resuming
        and adds nothing; a count climbing from 0 instead is the print started again, and that filament is new."""
        booked: list[dict[str, Any]] = []
        job = self.job
        if job is not None and job.get("file") != file:
            booked = self.end()
            job = None
        if job is None:
            # counted from 0, so a print's first reading (often a few cm already) is booked too; the same file as the
            # print last ended starts from how far that got, so if it is that print resuming its jump adds nothing
            recent = self.recent if self.recent and self.recent.get("file") == file else {}
            self.job = job = {"file": file, "last": 0.0, "high": float(recent.get("high") or 0), "used": {}}
        if active and not job.get("active") and UNKNOWN_SLOT in job["used"]:
            # the printer says which slot only about a minute into a print: what the start (the purge line) used is
            # the first slot's it names
            job["used"][active] = round(float(job["used"].get(active) or 0) + job["used"].pop(UNKNOWN_SLOT), 1)
        last = float(job.get("last") or 0)
        high = max(float(job.get("high") or 0), last)
        if used_mm < last:
            delta = 0.0                         # the count dropped: the printer restarting, or the print starting again
        elif last < high - RESUME_GAP <= used_mm:
            delta = max(0.0, used_mm - high)    # back up to where it was: resuming, nothing new
        else:
            delta = used_mm - last
        if delta > 0:
            where = active or job.get("active") or UNKNOWN_SLOT
            job["used"][where] = round(float(job["used"].get(where) or 0) + delta, 1)
        if active:
            job["active"] = active
        job["last"] = used_mm
        job["high"] = max(high, used_mm)
        return booked

    def end(self) -> list[dict[str, Any]]:
        """The print is over: each slot's length off its spool, or onto what waits for the slot's stock number. The print
        is the last print: its grams, and what they cost where the spools have a price."""
        job, self.job = self.job, None
        if job:
            self.recent = {"file": job.get("file"), "high": max(float(job.get("high") or 0), float(job.get("last") or 0))}
        booked: list[dict[str, Any]] = []
        ended = self.now()
        total = cost = uncosted = 0.0
        priced = False
        for label, mm in sorted((job or {}).get("used", {}).items()):
            if mm <= 0:
                continue
            slot = self.slots.get(label) or {}
            spool = self.spool(slot.get("stock")) if slot.get("stock") else None
            if spool is not None:
                used = grams(mm, spool["type"])
                self._take(spool, used)
                worth = self._cost(spool, used)
                booked.append({"slot": label, "stock": spool["stock"], "grams": round(used, 1),
                               "cost": round(worth, 2) if worth is not None else None})
                total += used
                if worth is None:
                    uncosted += used
                else:
                    cost, priced = cost + worth, True
            else:
                waiting = self.pending.setdefault(label, {"mm": 0.0, "type": slot.get("type") or "", "key": slot.get("key")})
                # grams an earlier spool in this slot left unconfirmed join these: the number given takes them all
                waiting["key"] = slot.get("key")
                waiting["mm"] = round(float(waiting["mm"]) + mm, 1)
                waiting["print"] = ended
                used = grams(mm, slot.get("type"))
                booked.append({"slot": label, "stock": None, "grams": round(used, 1), "cost": None})
                total += used
                uncosted += used
        if total > 0:
            self.last_print = {"file": (job or {}).get("file"), "ended": ended, "grams": round(total, 1),
                               "cost": round(cost, 2) if priced else None, "uncosted": round(uncosted, 1)}
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
            "printing": self.printing(),
            "tares": self.tares,
            "last_print": self.last_print,
        }

    def printing(self) -> dict[str, float]:
        """The print under way so far, in grams by slot."""
        def slot_type(label: str) -> str:
            slot = self.slots.get(label) or {}
            spool = self.spool(slot.get("stock")) if slot.get("stock") else None
            return spool["type"] if spool else slot.get("type") or ""

        return {k: round(grams(mm, slot_type(k)), 1) for k, mm in self.job["used"].items()} if self.job else {}
