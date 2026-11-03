"""A filament spool's label read from a photo, to fill in the check-in form. Mark, 2 Nov 2026: "With the 3d printer can I
take a picture of the new filliment and Google ai sets the manufacturer and color and tag?"

The page uploads the photo to Home Assistant (/api/image/upload) and asks for it to be read. The house's preferred AI
Task entity (Settings > Voice assistants > AI tasks; Google Gemini in Mark's houses), or with none preferred the first
AI Task entity that can read a photo, is given the photo and the brands and types the form knows, and asked for the
brand, the colour's name and the colour itself, the type and the weight of filament on the label. What comes back is tidied here into the form's fields: a known brand or type in its usual
spelling, the colour as #rrggbb, the weight in grams. Nothing is checked in: the form is filled, the person looks, and
checks it in as before; the stock number and the NFC tag follow from what is saved.

The photo is deleted from Home Assistant's image store here, on every path, so a page that was closed, a read that
failed or one that timed out leaves nothing behind (3 Nov 2026 review: the page used to delete it, best-effort, and only
an administrator could). The AI is given TIMEOUT_S to answer. label_fields() needs no Home Assistant (tested on its
own); read_label() is the call."""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from .filament import MAX_WEIGHT, colour_hex

# Home Assistant is imported inside the two calls that need it, so label_fields() stays testable with no Home Assistant

NO_AI = "no_ai"
TASK = "printer panel spool label"
TIMEOUT_S = 90                     # a metered call that hangs must not hold the page or the websocket for good
IMAGE_UPLOAD = "image_upload"      # where Home Assistant keeps the uploaded images' collection in hass.data
READS_PHOTOS = 1 | 2               # ai_task's AITaskEntityFeature.GENERATE_DATA | SUPPORT_ATTACHMENTS, as supported_features carries them
RETRY_WAITS = (5, 15)              # seconds before the second and the third try when the AI is busy: Google's 503 "high demand"
                                   # spikes pass in seconds (3 Nov 2026, Mark's houses), and the 90 s budget covers three tries
_BUSY = ("high demand", "503", "unavailable", "429", "resource_exhausted", "overloaded")
# a used-up quota answers 429 too, but it is not a spike: Google says when to try again (a day's quota, for hours), so it
# is not asked again and is told in Google's words (second review, 3 Nov 2026; a GenerateRequestsPerDay 429 seen in the wild)
_QUOTA = ("exceeded your current quota", "perday", "per day", "daily quota")
AI_BUSY = "ai_busy"
_PREFACE = "Sorry, I had a problem getting a response from Google Generative AI."   # Home Assistant's, before Google's own text
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


async def forget_image(hass: Any, image_id: str) -> bool:
    """The uploaded photo out of Home Assistant's image store. False when it was not there (already gone, or the image
    upload integration is not loaded)."""
    from homeassistant.helpers.collection import ItemNotFound

    collection = hass.data.get(IMAGE_UPLOAD)
    if collection is None:
        return False
    try:
        await collection.async_delete_item(image_id)
    except ItemNotFound:
        return False
    return True


def readers(hass: Any) -> list[str]:
    """The AI Task entities that can read a photo (generate data, with attachments) and are there, by id. A fresh
    entity's state is 'unknown' until its first task, so only 'unavailable' (its integration not loaded) is skipped."""
    found = []
    for state in hass.states.async_all("ai_task"):
        features = state.attributes.get("supported_features")
        if state.state != "unavailable" and isinstance(features, int) and features & READS_PHOTOS == READS_PHOTOS:
            found.append(state.entity_id)
    return sorted(found)


def _no_preferred(err: BaseException) -> bool:
    """Home Assistant's 'No entity_id provided and no preferred entity set': the words today, the translation key from
    2026.11 (ai_task's exceptions.no_entity)."""
    text = str(err).lower()
    return "no preferred entity" in text or "no entity_id provided" in text or getattr(err, "translation_key", None) == "no_entity"


async def _generate(hass: Any, call: dict[str, Any]) -> Any:
    """ai_task.generate_data by the house's preferred AI Task entity or, when none is preferred, by the first entity
    that can read a photo: a house with one Gemini needs no setting (Mark's, 3 Nov 2026: "Home Assistant has no AI
    task to read photos with" on a house that had one). LookupError(NO_AI) when no entity can read a photo."""
    from homeassistant.exceptions import HomeAssistantError, ServiceNotFound

    try:
        return await hass.services.async_call("ai_task", "generate_data", call, blocking=True, return_response=True)
    except ServiceNotFound:
        raise
    except HomeAssistantError as err:
        if not _no_preferred(err):
            raise
        reader = next(iter(readers(hass)), None)
        if reader is None:
            raise LookupError(NO_AI) from err
        return await hass.services.async_call("ai_task", "generate_data", {**call, "entity_id": reader}, blocking=True, return_response=True)


def is_busy(err: BaseException) -> bool:
    """A failure that is the AI's capacity, not the request: worth another try, and told as such. A used-up quota is not."""
    text = str(err).lower()
    return not any(word in text for word in _QUOTA) and any(word in text for word in _BUSY)


def reason(err: BaseException) -> str:
    """What went wrong, in Google's words where it gave any: Home Assistant's fixed preface taken off, and the message
    inside Google's JSON when that is what follows (the page showed the JSON before)."""
    text = str(err).strip()
    if text.startswith(_PREFACE):
        text = text[len(_PREFACE):].lstrip(":").strip()
    try:
        text = str(json.loads(text)["error"]["message"]) or text
    except (ValueError, TypeError, KeyError):
        pass
    return re.sub(r"\s+", " ", text).strip() or type(err).__name__


async def _generate_patiently(hass: Any, call: dict[str, Any]) -> Any:
    """_generate, asked again after RETRY_WAITS when the AI is busy; any other failure, or the last, is raised as it came."""
    from homeassistant.exceptions import HomeAssistantError, ServiceNotFound

    for wait in (*RETRY_WAITS, None):
        try:
            return await _generate(hass, call)
        except ServiceNotFound:
            raise
        except HomeAssistantError as err:
            if wait is None or not is_busy(err):
                raise
            await asyncio.sleep(wait)
    return None     # not reached: the last try returns or raises


async def read_label(hass: Any, image_id: str, brands: list[str], types: list[str]) -> dict[str, Any]:
    """The uploaded photo read by the house's AI Task entity (_generate, asked again when the AI is busy), as the form's
    fields. Raises LookupError(NO_AI) when the house has no AI task that can read a photo, TimeoutError after TIMEOUT_S.
    The photo is deleted whatever happens."""
    from homeassistant.exceptions import ServiceNotFound

    call = {"task_name": TASK, "instructions": instructions(brands, types), "structure": STRUCTURE,
            "attachments": [{"media_content_id": f"media-source://image_upload/{image_id}", "media_content_type": "image/jpeg"}]}
    try:
        try:
            async with asyncio.timeout(TIMEOUT_S):
                response = await _generate_patiently(hass, call)
        except ServiceNotFound as err:
            raise LookupError(NO_AI) from err
    finally:
        await forget_image(hass, image_id)
    return label_fields((response or {}).get("data"), brands, types)
