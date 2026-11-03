"""The label read from a photo, on every path (0.6.1): the photo is deleted from Home Assistant's image store whether
the read succeeded, failed or timed out; no AI Task entity that can read a photo is no_ai, and with none preferred the
first that can is asked (0.6.2); a busy AI is asked again; a second read for the same person while one is under way is
told to wait; the brand and type lists are bounded."""
from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
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
    images = hass.data[labelread.IMAGE_UPLOAD]
    images.held.add(IMAGE)
    assert (await _ask(client, 2, _msg(entry)))["error"]["code"] == "no_ai", "no AI task entity in the house at all"
    hass.states.async_set("ai_task.text_only", "2026-11-03T12:00:00+00:00", {"supported_features": 1})
    hass.states.async_set("ai_task.gone", "unavailable", {"supported_features": 7})
    images.held.add(IMAGE)
    assert (await _ask(client, 3, _msg(entry)))["error"]["code"] == "no_ai", "text-only and unavailable entities cannot read a photo"
    assert images.deleted == [IMAGE, IMAGE, IMAGE], "the photo is deleted on each of these paths"


async def test_without_a_preferred_entity_the_one_that_reads_photos_is_used(hass: HomeAssistant, k2plus, hass_ws_client) -> None:
    """Mark's houses had a Gemini AI task but no preferred entity (3 Nov 2026): the page said there was no AI task.
    The first by id of those that can read a photo and are there; the whole request goes to it; the same from
    2026.11, where Home Assistant raises the translation key instead of the words."""
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    images = Images(IMAGE)
    hass.data[labelread.IMAGE_UPLOAD] = images
    hass.states.async_set("ai_task.aaa_gone", "unavailable", {"supported_features": 7})
    hass.states.async_set("ai_task.bbb_text_only", "2026-11-03T12:00:00+00:00", {"supported_features": 1})
    hass.states.async_set("ai_task.google_ai_task", "unknown", {"supported_features": 7})
    hass.states.async_set("ai_task.zzz_other_reader", "2026-11-03T12:00:00+00:00", {"supported_features": 3})
    asked: list[dict[str, Any]] = []
    refusal: list[Exception] = [HomeAssistantError("No entity_id provided and no preferred entity set"),
                                ServiceValidationError(translation_domain="ai_task", translation_key="no_entity")]

    async def generate(call: ServiceCall) -> dict[str, Any]:
        asked.append(dict(call.data))
        if "entity_id" not in call.data:
            raise refusal[0]
        return {"data": {"brand": "esun", "type": "pla+", "weight": 1}}

    hass.services.async_register("ai_task", "generate_data", generate, supports_response=SupportsResponse.ONLY)
    got = await _ask(client, 1, _msg(entry))
    assert got["success"] and got["result"] == {"brand": "eSun", "type": "PLA+", "weight": 1000}
    assert len(asked) == 2 and "entity_id" not in asked[0], "the preferred entity is asked first, then one more"
    assert asked[1] == {**asked[0], "entity_id": "ai_task.google_ai_task"}, "the whole request, to the first that can read a photo"
    assert images.deleted == [IMAGE]

    refusal.pop(0)                                  # 2026.11: a ServiceValidationError carrying the key, no words
    images.held.add(IMAGE)
    got = await _ask(client, 2, _msg(entry))
    assert got["success"] and len(asked) == 4 and asked[3]["entity_id"] == "ai_task.google_ai_task", got


async def test_a_busy_ai_is_asked_again_but_a_failing_one_is_not(hass: HomeAssistant, k2plus, hass_ws_client, monkeypatch) -> None:
    """Google's 503 "high demand" (3 Nov 2026): three tries, then ai_busy for the page to say in its own language; any
    other failure, a used-up quota included, is told at once in Google's words."""
    entry = await _add(hass, k2plus)
    client = await hass_ws_client(hass)
    images = Images(IMAGE)
    hass.data[labelread.IMAGE_UPLOAD] = images
    monkeypatch.setattr(labelread, "RETRY_WAITS", (0, 0))
    busy = ('Sorry, I had a problem getting a response from Google Generative AI.: {"error": {"code": 503, '
            '"message": "This model is currently experiencing high demand.", "status": "UNAVAILABLE"}}')
    quota = ('Sorry, I had a problem getting a response from Google Generative AI.: {"error": {"code": 429, '
             '"message": "You exceeded your current quota. Please retry in 9h 3m 2s.", "status": "RESOURCE_EXHAUSTED", '
             '"details": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}}')
    answers: list[Any] = [busy, busy, {"data": {"brand": "Creality"}}, busy, busy, busy, "the model is down", quota]
    asked = 0

    async def generate(call: ServiceCall) -> dict[str, Any]:
        nonlocal asked
        asked += 1
        answer = answers.pop(0)
        if isinstance(answer, str):
            raise HomeAssistantError(answer)
        return answer

    hass.services.async_register("ai_task", "generate_data", generate, supports_response=SupportsResponse.ONLY)
    got = await _ask(client, 1, _msg(entry))
    assert got["success"] and got["result"] == {"brand": "Creality"} and asked == 3, "busy twice, then read"
    images.held.add(IMAGE)
    got = await _ask(client, 2, _msg(entry))
    assert not got["success"] and got["error"]["code"] == "ai_busy" and asked == 6, "busy three times: given up, in a code of its own"
    assert got["error"]["message"] == "The AI is busy (high demand): try again in a minute", got["error"]
    images.held.add(IMAGE)
    got = await _ask(client, 3, _msg(entry))
    assert not got["success"] and "model is down" in got["error"]["message"] and asked == 7, "a real failure is told at once"
    images.held.add(IMAGE)
    got = await _ask(client, 4, _msg(entry))
    assert not got["success"] and got["error"]["code"] == "failed" and asked == 8, "a used-up quota is asked once"
    assert got["error"]["message"] == "You exceeded your current quota. Please retry in 9h 3m 2s.", "in Google's words, not its JSON"
    assert images.deleted == [IMAGE] * 4, "the photo is deleted on every path"


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
