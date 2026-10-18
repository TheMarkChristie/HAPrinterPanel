"""The printer as Printer Panel sees it, with no Home Assistant in it (tested on its own): which of the Creality
integration's entities is which, found by their translation keys and unique ids so a renamed entity is still found; the
print's name from its file; and which state changes are worth a notification, with the words for it."""
from __future__ import annotations

import re
from typing import Any, Iterable

# what the page shows or works -> the Creality integration's (ha_creality_ws) translation key for it
KEYS = {
    "status": "print_status", "progress": "print_progress", "time_left": "print_left_time", "job_time": "print_job_time",
    "layer": "current_layer", "layers": "total_layers", "control": "print_control", "material": "expected_material_length",
    "active_slot": "active_filament_slot", "filament_status": "filament_status", "current_object": "current_object",
    "nozzle": "nozzle_temperature", "bed": "bed_temperature", "chamber": "chamber_temperature",
    "nozzle_target": "nozzle_target", "bed_target": "bed_target", "chamber_target": "chamber_target",
    "speed": "print_tuning_pct", "flow": "flow_rate_pct",
    "fan_model": "model_fan", "fan_side": "side_fan", "fan_case": "case_fan", "light": "light",
    "pause": "pause_print", "resume": "resume_print", "stop": "stop_print",
    "camera": "printer_camera", "preview": "current_print_preview",
}
SLOT = re.compile(r"cfs_box_(\d+)_slot_(\d+)_(color|filament|percent)$")
BOX = re.compile(r"cfs_box_(\d+)_(temp|humidity)$")
EXTERNAL = re.compile(r"cfs_external_(color|filament|percent)$")
PART = {"color": "color", "filament": "filament", "percent": "remaining"}

# the slicer's materials and print time at the end of a file name: "Name_PLA_9h1m52s", "Name_PLA-CF_PETG_1d2h3m"
SLICER_SUFFIX = re.compile(r"(?:_[A-Z][A-Z0-9+-]*)+_(?:\d+d)?(?:\d+h)?\d+m(?:\d+s)?$")
GCODE_EXT = re.compile(r"\.(?:gcode|gco|g|bgcode)$", re.I)

ACTIVE = ("printing", "processing", "paused", "self-testing")
EVENTS = ("finished", "paused", "runout", "error")


def resolve(entries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """The printer's entities from its device's registry entries ({entity_id, unique_id, translation_key, disabled_by}):
    {"entities": {what: entity id}, "boxes": [{"box", "temperature", "humidity", "slots": [{"slot", "label", "color",
    "filament", "remaining"}]}], "external": {"color", "filament", "remaining"} or None}. Disabled entities are left out."""
    by_key: dict[str, str] = {}
    boxes: dict[int, dict[str, Any]] = {}
    external: dict[str, str] = {}
    for e in entries:
        if e.get("disabled_by"):
            continue
        entity_id, uid, key = str(e.get("entity_id") or ""), str(e.get("unique_id") or ""), e.get("translation_key")
        if key and key not in by_key:
            by_key[key] = entity_id
        if m := SLOT.search(uid):
            box, index = int(m.group(1)), int(m.group(2))
            slots = boxes.setdefault(box, {"box": box, "slots": {}})["slots"]
            slot = slots.setdefault(index, {"slot": index + 1, "label": f"{box}{chr(65 + index)}"})
            slot[PART[m.group(3)]] = entity_id
        elif m := BOX.search(uid):
            box = boxes.setdefault(int(m.group(1)), {"box": int(m.group(1)), "slots": {}})
            box["temperature" if m.group(2) == "temp" else "humidity"] = entity_id
        elif m := EXTERNAL.search(uid):
            external[PART[m.group(1)]] = entity_id
    entities = {what: by_key[key] for what, key in KEYS.items() if key in by_key}
    return {
        "entities": entities,
        "boxes": [{**b, "slots": [b["slots"][i] for i in sorted(b["slots"])]} for _, b in sorted(boxes.items())],
        "external": ({"label": "Ext", **external} if external else None),
    }


def print_name(path: Any) -> str | None:
    """'/mnt/UDISK/printer_data/gcodes/GTA 6 stand - Warden of Bacon_PLA_9h1m52s.gcode' -> 'GTA 6 stand - Warden of Bacon'."""
    if not path:
        return None
    name = re.split(r"[\\/]", str(path).strip())[-1]
    name = GCODE_EXT.sub("", name)
    name = SLICER_SUFFIX.sub("", name)
    return name.strip(" _-") or None


def duration(seconds: Any, lang: str = "en") -> str:
    """9 h 2 min, 45 min, under a minute (in Norwegian 9 t 2 min)."""
    try:
        total = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        return ""
    hours, minutes = divmod(total // 60, 60)
    h = "t" if lang == "nb" else "h"
    if hours and minutes:
        return f"{hours} {h} {minutes} min"
    if hours:
        return f"{hours} {h}"
    if minutes:
        return f"{minutes} min"
    return "under ett minutt" if lang == "nb" else "under a minute"


def print_event(old: str | None, new: str | None) -> str | None:
    """A print status change worth telling: finished (from printing or paused), paused (from printing), an error. A change
    from unknown or unavailable (a restart, the printer switched on) is never one."""
    if old == new or old in (None, "unknown", "unavailable") or new in (None, "unknown", "unavailable"):
        return None
    if new == "completed" and old in ACTIVE:
        return "finished"
    if new == "paused" and old in ("printing", "processing"):
        return "paused"
    if new == "error":
        return "error"
    return None


def filament_event(old: str | None, new: str | None) -> str | None:
    """The filament ran out (normal -> runout)."""
    return "runout" if new == "runout" and old == "normal" else None


WORDS = {
    "en": {
        "title": "3D printer",
        "unnamed": "The print",
        "finished": "{name} is finished, after {time}.",
        "paused": "{name} is paused at {progress} %.",
        "paused_line": "{name} is paused at line {line}, as asked.",
        "runout": "{name}: the filament ran out at {progress} %.",
        "error": "{name} stopped with an error at {progress} %.",
    },
    "nb": {
        "title": "3D-skriver",
        "unnamed": "Utskriften",
        "finished": "{name} er ferdig, etter {time}.",
        "paused": "{name} er satt på pause ved {progress} %.",
        "paused_line": "{name} er satt på pause ved linje {line}, som du ba om.",
        "runout": "{name}: filamentet gikk tomt ved {progress} %.",
        "error": "{name} stoppet med en feil ved {progress} %.",
    },
}


def language(lang: Any) -> str:
    return "nb" if re.match(r"^(nb|nn|no)\b", str(lang or ""), re.I) else "en"


def message(event: str, lang: str, name: str | None, progress: Any, job_time: Any, line: Any = None) -> tuple[str, str]:
    """The notification's title and text for an event (paused_line: a pause this integration made at a line)."""
    lang = language(lang)
    words = WORDS[lang]
    try:
        pct = int(round(float(progress)))
    except (TypeError, ValueError):
        pct = 0
    if isinstance(line, int):  # 400,018 / 400 018
        line = f"{line:,}".replace(",", " ") if lang == "nb" else f"{line:,}"
    text = words[event].format(name=name or words["unnamed"], progress=pct, time=duration(job_time, lang) or "-",
                               line=line if line is not None else "-")
    return words["title"], text
