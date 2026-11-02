"""A filament spool's label read from a photo, to fill in the check-in form. Mark, 2 Nov 2026: "With the 3d printer can I
take a picture of the new filliment and Google ai sets the manufacturer and color and tag?"

The page uploads the photo to Home Assistant (/api/image/upload) and asks for it to be read. The house's AI Task entity
(Google Gemini in Mark's houses) is given the photo and the brands and types the form knows, and asked for the brand,
the colour's name and the colour itself, the type and the weight of filament on the label. What comes back is tidied
here into the form's fields: a known brand or type in its usual spelling, the colour as #rrggbb, the weight in grams.
Nothing is checked in: the form is filled, the person looks, and checks it in as before; the stock number and the NFC
tag follow from what is saved. The page deletes the photo afterwards. label_fields() needs no Home Assistant (tested
on its own); read_label() is the call."""
from __future__ import annotations

import re
from typing import Any

from .filament import MAX_WEIGHT, colour_hex

NO_AI = "no_ai"
TASK = "printer panel spool label"
STRUCTURE = {
    "brand": {"description": "The filament's maker, as on the label", "selector": {"text": {}}},
    "colour": {"description": "The colour's name, in English, as on the label if it gives one", "selector": {"text": {}}},
    "hex": {"description": "The filament's colour as it looks, as #rrggbb", "selector": {"text": {}}},
    "type": {"description": "The material or product (PLA, PETG, Hyper PLA...)", "selector": {"text": {}}},
    "weight": {"description": "The net weight of filament in grams (1 kg is 1000)", "selector": {"number": {"min": 0, "max": MAX_WEIGHT}}},
}
_NOTHING = {"", "unknown", "none", "n/a", "generic", "not visible", "unbranded"}


def instructions(brands: list[str], types: list[str]) -> str:
    """What the AI is asked, with the spellings the form already uses."""
    return ("This photo shows a spool of 3D printer filament, or its box or label. Read the label. Give the maker, the colour's "
            "name and the colour itself, the material, and the net weight of filament. When the maker is one of these, use "
            f"this spelling: {'; '.join(brands)}. When the material is one of these, use this spelling: {'; '.join(types)}; "
            "for Creality's own products keep the product name (Hyper PLA, Hyper PETG, CR-PLA). Leave a field empty when "
            "the label does not show it; do not guess a maker.")


def _known(value: str, known: list[str]) -> str:
    """A value in the form's own spelling when it is one it knows ('ESUN' -> 'eSun'), else as read."""
    low = value.lower()
    return next((k for k in known if k.lower() == low), value)


def label_fields(data: dict[str, Any] | None, brands: list[str], types: list[str]) -> dict[str, Any]:
    """What the AI read, as the form's fields: brand, colour, hex, type (the form's 'material'), weight in grams.
    A field it could not read is left out, so the form keeps what it has."""
    data = data or {}
    out: dict[str, Any] = {}
    brand = re.sub(r"\s+", " ", str(data.get("brand") or "")).strip()
    if brand.lower() not in _NOTHING:
        out["brand"] = _known(brand, brands)
    colour = re.sub(r"\s+", " ", str(data.get("colour") or "")).strip()
    if colour.lower() not in _NOTHING:
        out["colour"] = colour[:1].upper() + colour[1:]
    if hex_ := colour_hex(data.get("hex")):
        out["hex"] = hex_
    kind = re.sub(r"\s+", " ", str(data.get("type") or "")).strip()
    if kind.lower() not in _NOTHING:
        out["type"] = _known(kind, types)
    try:
        weight = float(data.get("weight") or 0)
    except (TypeError, ValueError):
        weight = 0.0
    if 0 < weight < 20:                       # read as kilograms (1 for 1 kg, 0.75 for 750 g)
        weight *= 1000
    if 0 < weight <= MAX_WEIGHT:
        out["weight"] = round(weight)
    return out


async def read_label(hass: Any, image_id: str, brands: list[str], types: list[str]) -> dict[str, Any]:
    """The uploaded photo read by the house's AI Task entity (the first there is), as the form's fields. Raises
    LookupError(NO_AI) when the house has none."""
    entities = sorted(hass.states.async_entity_ids("ai_task"))
    if not entities:
        raise LookupError(NO_AI)
    response = await hass.services.async_call("ai_task", "generate_data", {
        "task_name": TASK, "entity_id": entities[0], "instructions": instructions(brands, types), "structure": STRUCTURE,
        "attachments": [{"media_content_id": f"media-source://image_upload/{image_id}", "media_content_type": "image/jpeg"}],
    }, blocking=True, return_response=True)
    return label_fields((response or {}).get("data"), brands, types)
