"""The printer's rules, without Home Assistant: python -m pytest tests -q

The fixture is the Norway K2 Plus with its CFS as the Creality integration (ha_creality_ws 0.9.9) registered it on
18 Oct 2026, mid-print (address and tokens replaced)."""
import json
import pathlib

import _load  # noqa: F401
from custom_components.printer_panel import printer as p

FIXTURE = json.loads((pathlib.Path(__file__).parent / "fixtures" / "k2plus.json").read_text(encoding="utf-8"))


def test_every_part_of_the_page_finds_its_entity_by_key():
    found = p.resolve(FIXTURE["registry"])
    e = found["entities"]
    assert e["status"].endswith("_print_status") and e["time_left"].endswith("_print_time_left")
    assert e["nozzle_target"].startswith("number.") and e["speed"].endswith("_speed_factor")
    assert e["pause"].startswith("button.") and e["resume"].startswith("button.") and e["stop"].startswith("button.")
    assert e["camera"].startswith("camera.") and e["preview"].startswith("image.") and e["light"].startswith("light.")
    assert {"fan_model", "fan_side", "fan_case"} <= set(e)
    assert set(p.KEYS) - set(e) == set(), "everything the page uses is there"


def test_the_cfs_box_its_four_slots_and_the_external_spool():
    found = p.resolve(FIXTURE["registry"])
    (box,) = found["boxes"]
    assert box["box"] == 1 and box["temperature"].endswith("_box_1_temperature") and box["humidity"].endswith("_box_1_humidity")
    assert [s["label"] for s in box["slots"]] == ["1A", "1B", "1C", "1D"]
    assert box["slots"][3]["remaining"].endswith("_slot_4_remaining"), "unique id slot_3 is the fourth slot"
    assert set(box["slots"][0]) == {"slot", "label", "color", "filament", "remaining"}
    assert found["external"]["color"].endswith("_external_color") and found["external"]["label"] == "Ext"


def test_a_renamed_entity_is_still_found_and_a_disabled_one_left_out():
    entries = [dict(e) for e in FIXTURE["registry"]]
    for e in entries:
        if e["translation_key"] == "print_status":
            e["entity_id"] = "sensor.my_printer_status"
        if e["translation_key"] == "light":
            e["disabled_by"] = "user"
    found = p.resolve(entries)
    assert found["entities"]["status"] == "sensor.my_printer_status"
    assert "light" not in found["entities"]


def test_the_print_name_comes_from_the_file_without_the_slicers_suffix():
    assert p.print_name("/mnt/UDISK/printer_data/gcodes/GTA 6 stand - Warden of Bacon_PLA_9h1m52s.gcode") == "GTA 6 stand - Warden of Bacon"
    assert p.print_name("Benchy_PETG-CF_PLA_1d2h3m.gcode") == "Benchy"
    assert p.print_name("Plant pot v2_PLA_45m10s.gcode") == "Plant pot v2"
    assert p.print_name("clip_v3.gcode") == "clip_v3", "a name's own lower-case parts stay"
    assert p.print_name("C:\\prints\\Lid.gcode") == "Lid"
    assert p.print_name("") is None and p.print_name(None) is None


def test_which_changes_are_worth_a_notification():
    assert p.print_event("printing", "completed") == "finished"
    assert p.print_event("paused", "completed") == "finished"
    assert p.print_event("printing", "paused") == "paused"
    assert p.print_event("printing", "error") == "error"
    assert p.print_event("unavailable", "completed") is None, "the printer switched on, or Home Assistant restarted"
    assert p.print_event("idle", "completed") is None
    assert p.print_event("printing", "printing") is None
    assert p.print_event("paused", "printing") is None, "resuming is not news"
    assert p.print_event("printing", "stopped") is None, "a stop is somebody's own doing"
    assert p.filament_event("normal", "runout") == "runout"
    assert p.filament_event("unavailable", "runout") is None and p.filament_event("runout", "normal") is None


def test_the_words_in_english_and_norwegian():
    assert p.message("finished", "en", "GTA 6 stand", 100, 32520) == ("3D printer", "GTA 6 stand is finished, after 9 h 2 min.")
    assert p.message("paused", "en-GB", "Lid", "56.4", None) == ("3D printer", "Lid is paused at 56 %.")
    assert p.message("runout", "nb", None, 56, 0)[1] == "Utskriften: filamentet gikk tomt ved 56 %."
    assert p.message("error", "nb-NO", "Lid", 12, 0) == ("3D-skriver", "Lid stoppet med en feil ved 12 %.")
    assert p.duration(45) == "under a minute" and p.duration(3600) == "1 h" and p.duration(9240, "nb") == "2 t 34 min"
