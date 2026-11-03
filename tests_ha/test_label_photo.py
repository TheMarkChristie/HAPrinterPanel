"""The label read from a photo, on every path (0.6.1): the photo is deleted from Home Assistant's image store whether
the read succeeded, failed or timed out; no preferred AI Task entity is no_ai; a second read for the same person while
one is under way is told to wait; the brand and type lists are bounded."""
from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.collection import ItemNotFound

from custom_components.printer_panel import labelread

from test_filament import _add, _ask

DOMAIN = "printer_panel"
IMAGE = "0123456789abcdef0123456789abcdef"


class Images:
    """A stand-in for the image upload integration's collection: what it holds, and what was deleted."""

    def __init__(self, *ids: str) -> None:
        self.held = set(ids)
        self.deleted: list[str] = []

    async def async_delete_item(self, item_id: str) -> None:
        if item_id not in self.held:
            raise ItemNotFound(item_id)
        self.held.discard(item_id)
        self.deleted.append(item_id)


def _msg(entry, **more: Any) -> dict[str, Any]:
    return {"type": f"{DOMAIN}/filament/read_label", "entry_id": entry.entry_id, "image_id": IMAGE, "brands": ["eSun"], "types": ["PLA+"], **more}


async def test_the_photo_is_deleted_on_success_failure_and_timeout(hass: HomeAssistant, k2plus, hass_ws_client, monkeypatch) -> None:
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    images = Images(IMAGE)
    hass.data[labelread.IMAGE_UPLOAD] = images
    answers: list[Any] = [{"data": {"brand": "esun", "weight": 1}}, HomeAssistantError("the model is down"), "slow", {"data": {"brand": "Sunlu"}}]

    async def generate(call: ServiceCall) -> dict[str, Any]:
        answer = answers.pop(0)
        if answer == "slow":
            await asyncio.sleep(1)
            return {}
        if isinstance(answer, Exception):
            raise answer
        return answer

    hass.services.async_register("ai_task", "generate_data", generate, supports_response=SupportsResponse.ONLY)
    got = await _ask(client, 1, _msg(entry))
    assert got["success"] and got["result"] == {"brand": "eSun", "weight": 1000}
    assert images.deleted == [IMAGE] and not images.held, "deleted after a good read"

    images.held.add(IMAGE)
    got = await _ask(client, 2, _msg(entry))
    assert not got["success"] and got["error"]["code"] == "failed" and "model is down" in got["error"]["message"]
    assert images.deleted == [IMAGE, IMAGE], "deleted after a failed read"

    images.held.add(IMAGE)
    monkeypatch.setattr(labelread, "TIMEOUT_S", 0.05)
    got = await _ask(client, 3, _msg(entry))
    assert not got["success"] and got["error"]["code"] == "failed" and "did not answer" in got["error"]["message"]
    assert images.deleted == [IMAGE, IMAGE, IMAGE], "deleted after a read that timed out"

    monkeypatch.setattr(labelread, "TIMEOUT_S", 5)
    got = await _ask(client, 4, _msg(entry))          # the photo already gone from the store: no error from the deletion
    assert got["success"] and got["result"] == {"brand": "Sunlu"}
    assert len(images.deleted) == 3


async def test_no_ai_task_and_no_preferred_entity_are_no_ai(hass: HomeAssistant, k2plus, hass_ws_client) -> None:
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    hass.data[labelread.IMAGE_UPLOAD] = Images(IMAGE)
    assert (await _ask(client, 1, _msg(entry)))["error"]["code"] == "no_ai", "no ai_task service at all"

    async def generate(call: ServiceCall) -> dict[str, Any]:
        raise HomeAssistantError("No entity_id provided and no preferred entity set")

    hass.services.async_register("ai_task", "generate_data", generate, supports_response=SupportsResponse.ONLY)
    assert (await _ask(client, 2, _msg(entry)))["error"]["code"] == "no_ai", "the house has not chosen an AI task entity"
    assert not hass.data[labelread.IMAGE_UPLOAD].held, "the photo is deleted on these paths too"


async def test_one_read_at_a_time_per_person(hass: HomeAssistant, k2plus, hass_ws_client) -> None:
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    hass.data[labelread.IMAGE_UPLOAD] = Images(IMAGE, "f" * 32)

    async def generate(call: ServiceCall) -> dict[str, Any]:
        await asyncio.sleep(0.3)
        return {"data": {"brand": "Creality"}}

    hass.services.async_register("ai_task", "generate_data", generate, supports_response=SupportsResponse.ONLY)
    await client.send_json({"id": 1, **_msg(entry)})
    await client.send_json({"id": 2, **_msg(entry, image_id="f" * 32)})
    answers = {a["id"]: a for a in [await client.receive_json(), await client.receive_json()]}
    assert answers[2]["error"]["code"] == "busy", answers
    assert answers[1]["success"] and answers[1]["result"] == {"brand": "Creality"}
    got = await _ask(client, 3, _msg(entry, image_id="f" * 32))       # the first is done: a new read is taken
    assert got["success"], got


async def test_the_lists_are_bounded(hass: HomeAssistant, k2plus, hass_ws_client) -> None:
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    got = await _ask(client, 1, _msg(entry, brands=["x" * 61]))
    assert got["error"]["code"] == "invalid_format"
    got = await _ask(client, 2, _msg(entry, types=["PLA"] * 201))
    assert got["error"]["code"] == "invalid_format"
