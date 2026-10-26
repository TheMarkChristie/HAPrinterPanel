"""The filament register's rules, without Home Assistant: python -m pytest tests -q

The CFS slots are the Norway K2 Plus's as the Creality integration showed them on 18 Oct 2026 (tests/fixtures): three
Generic PLA spools set by hand on the printer (pink, black, blue), a Creality Hyper PLA in the fourth slot (purple, its
chip read) and another on the external holder (red)."""
import json
import math
import pathlib

import pytest

import _load  # noqa: F401
from custom_components.printer_panel import filament as f

FIXTURE = json.loads((pathlib.Path(__file__).parent / "fixtures" / "k2plus.json").read_text(encoding="utf-8"))
STATES = {s["entity_id"]: s for s in FIXTURE["states"]}
DAY = "2026-10-25"


def cfs(entity_suffix: str) -> dict:
    """A slot as register.slot_info reads it, from the fixture."""
    a = next(s for k, s in STATES.items() if k.endswith(entity_suffix))["attributes"]
    return {"loaded": True, "vendor": a["vendor"], "type": a["type"], "name": a["name"], "hex": a["color_hex"],
            "rfid": a["rfid"], "state": a["state"]}


PURPLE, BLACK = cfs("slot_4_filament"), cfs("slot_2_filament")


def test_a_spool_is_checked_in_with_the_next_stock_number_never_used_twice():
    r = f.Register()
    a = r.check_in("Creality", "Purple", "#9E007E", "Hyper PLA", 1000, DAY)
    b = r.check_in(" eSun ", "Black", "#000000", "PLA+", "750", DAY)
    assert (a["stock"], b["stock"]) == ("F001", "F002")
    assert b["brand"] == "eSun" and b["weight"] == 750.0 and b["left"] == 750.0 and a["hex"] == "#9e007e"
    r.remove("f002")
    assert r.check_in("Polymaker", "Grey", "", "PETG", 1000, DAY)["stock"] == "F003", "a number is never reused"
    assert r.spool("F003")["hex"] == "#808080", "no colour picked: a grey swatch"


@pytest.mark.parametrize("brand, colour, material, weight", [("", "x", "PLA", 1000), ("Creality", "x", "", 1000),
                                                            ("Creality", "x", "PLA", 0), ("Creality", "x", "PLA", 20000),
                                                            ("Creality", "x", "PLA", "a lot")])
def test_check_in_says_no_to_what_is_missing_or_wrong(brand, colour, material, weight):
    with pytest.raises(f.RegisterError) as err:
        f.Register().check_in(brand, colour, "#000000", material, weight, DAY)
    assert err.value.key == "invalid"


def test_grams_from_length_by_type():
    one_metre_pla = f.grams(1000, "PLA")
    assert one_metre_pla == pytest.approx(math.pi * 0.875 ** 2 * 1.24, rel=1e-9)
    assert one_metre_pla == pytest.approx(2.98, abs=0.01), "about 3 g a metre"
    assert f.grams(1000, "Hyper PLA") == one_metre_pla
    assert f.grams(1000, "PETG") > one_metre_pla > f.grams(1000, "ABS")
    assert f.base_type("PETG-CF") == "PETG-CF" and f.base_type("pla matte") == "PLA" and f.base_type("Unobtainium") == "UNOBTAINIUM"
    assert f.grams(1000, "Unobtainium") == one_metre_pla, "an unknown type weighs as PLA"


def test_the_active_slot_names():
    assert f.slot_label("box_1_slot_2") == "1B" and f.slot_label("Box 2 Slot 4") == "2D" and f.slot_label("external") == "Ext"
    assert f.slot_label("") is None and f.slot_label(None) is None


def test_a_creality_spool_is_matched_by_the_cfs_and_a_generic_one_is_not():
    r = f.Register()
    r.check_in("Creality", "Purple", "#9e007e", "Hyper PLA", 1000, DAY)
    r.check_in("Creality", "Black", "#000000", "Hyper PLA", 1000, DAY)
    r.check_in("Generic", "Black", "#000000", "PLA", 1000, DAY)
    assert r.slot_seen("1D", PURPLE) and r.slots["1D"]["stock"] == "F001" and r.slots["1D"]["how"] == "auto"
    assert r.slot_seen("1B", BLACK) and "stock" not in r.slots["1B"], "the CFS says Generic: it waits for its number"
    assert not r.slot_seen("1D", PURPLE), "the same spool seen again changes nothing"


def test_a_creality_spool_checked_in_by_its_product_name_is_matched_too():
    # Norway's 1C on 25 Oct 2026: the CFS says type PLA, name Hyper Stardust
    stardust = {"loaded": True, "vendor": "Creality", "type": "PLA", "name": "Hyper Stardust", "hex": "#2f6f7a", "rfid": "01004", "state": 2}
    for typed in ("Hyper Stardust", "Hyper Stardust PLA"):
        r = f.Register()
        r.check_in("Creality", "Teal", "#2f6f7a", typed, 1000, DAY)
        assert r.slot_seen("1C", stardust) and r.slots["1C"].get("stock") == "F001", typed


def test_two_creality_spools_alike_wait_for_the_number():
    r = f.Register()
    r.check_in("Creality", "Purple", "#9e007e", "Hyper PLA", 1000, DAY)
    r.check_in("Creality", "Purple", "#9c027c", "PLA", 1000, DAY)
    r.slot_seen("1D", PURPLE)
    assert "stock" not in r.slots["1D"]


def test_a_spool_taken_out_or_swapped_starts_its_slot_again():
    r = f.Register()
    r.check_in("Generic", "Black", "#000000", "PLA", 1000, DAY)
    r.slot_seen("1B", BLACK)
    r.confirm("1B", "f001")
    assert r.slots["1B"]["stock"] == "F001" and r.slots["1B"]["how"] == "confirmed"
    r.slot_seen("1B", {"loaded": False})
    assert "1B" not in r.slots, "an empty slot holds no spool"
    r.slot_seen("1B", BLACK)
    assert "stock" not in r.slots["1B"], "a spool put back is confirmed again"


def test_a_print_is_booked_to_the_slots_it_used_and_waits_where_there_is_no_number():
    r = f.Register()
    r.check_in("Creality", "Purple", "#9e007e", "Hyper PLA", 1000, DAY)
    r.check_in("Generic", "Black", "#000000", "PLA", 1000, DAY)
    r.slot_seen("1D", PURPLE)
    r.slot_seen("1B", BLACK)
    file = "GTA 6 stand.gcode"
    for used, active in ((0, "1D"), (4000, "1D"), (6000, "1B"), (9000, "1B"), (10000, "1D")):
        assert r.track(file, used, active) == []
    assert r.view()["printing"]["1D"] == pytest.approx(f.grams(5000, "PLA"), abs=0.1)
    booked = r.end()
    purple = f.grams(5000, "PLA")   # 4000 then 1000 more, when 1D printed again
    assert booked == [{"slot": "1B", "stock": None, "grams": round(f.grams(5000, "PLA"), 1), "cost": None},
                      {"slot": "1D", "stock": "F001", "grams": round(purple, 1), "cost": None}]
    assert r.spool("F001")["left"] == pytest.approx(1000 - purple, abs=0.05)
    assert r.view()["pending"]["1B"] == pytest.approx(f.grams(5000, "PLA"), abs=0.1) and r.job is None
    # after the print: the stock number written on the black spool
    used = r.confirm("1B", "F002")
    assert used == pytest.approx(f.grams(5000, "PLA")) and r.spool("F002")["left"] == pytest.approx(1000 - used, abs=0.05)
    assert r.view()["pending"] == {} and r.slots["1B"]["stock"] == "F002"


def test_confirmed_before_the_print_it_comes_off_at_the_end():
    r = f.Register()
    r.check_in("Generic", "Black", "#000000", "PLA", 1000, DAY)
    r.slot_seen("1B", BLACK)
    r.confirm("1B", "F001")
    r.track("a.gcode", 0, "1B")
    r.track("a.gcode", 3356, "1B")
    assert r.end() == [{"slot": "1B", "stock": "F001", "grams": 10.0, "cost": None}]
    assert r.spool("F001")["left"] == 990.0


def test_a_new_print_ends_the_one_before_and_the_same_file_started_again_counts_on():
    r = f.Register()
    r.track("a.gcode", 5000, "1A")
    booked = r.track("b.gcode", 100, "1A")
    assert [b["slot"] for b in booked] == ["1A"] and r.job["file"] == "b.gcode"
    assert r.track("b.gcode", 3000, "1A") == []
    for used in (0, 500, 1500):                          # the same file started again from its beginning: new filament
        assert r.track("b.gcode", used, "1A") == []
    assert r.job["used"] == {"1A": 4500.0}


def test_a_print_going_wrong_and_resuming_is_counted_once():
    """Norway's K2 Plus on 26 Oct 2026, tag Robert in Hyper Stardust (1C): 75 m by 02:00, then a dozen errors, pauses
    and idles, two printer restarts (the count reads 0, then jumps back to where it was), the active slot unknown for a
    while, and stopped at 77,269 mm. The register booked that 75 m four times over; it is 77,269 mm, once."""
    r = f.Register()
    r.check_in("Creality", "Teal", "#2f6f7a", "Hyper Stardust PLA", 1000, DAY)
    stardust = {"loaded": True, "vendor": "Creality", "type": "PLA", "name": "Hyper Stardust", "hex": "#2f6f7a", "rfid": "01004", "state": 2}
    r.slot_seen("1C", stardust)
    file = "tag Robert_PLA_5h51m22s.gcode"
    steps = [(0, None), (104, None), (455, "1C"), (74782, "1C"), (75269, "1C"),     # error and idle from here: no reading
             (0, None), (75268, None), (75647, None), (75647, "1C"), (76022, "1C"),  # the printer restarted, resumed
             (76027, "1C"), (76305, "1C"), (76685, "1C"), (76685, None), (77267, None), (77269, None)]
    for used, slot in steps:
        assert r.track(file, used, slot) == []
    # 77,270: after a restart the printer resumes from its last checkpoint, 1 mm back, and prints that again
    assert list(r.job["used"]) == ["1C"] and r.job["used"]["1C"] == pytest.approx(77269, abs=5)
    booked = r.end()                                     # stopped
    assert booked[0]["stock"] == "F001" and booked[0]["grams"] == pytest.approx(f.grams(77269, "PLA"), abs=0.1)
    assert r.spool("F001")["left"] == pytest.approx(1000 - f.grams(77269, "PLA"), abs=0.1), "about 230 g, not 1 kg"
    # the printer comes back with the print it was on, as after a restart: its count jumps back, and adds nothing
    for used in (0, 77269, 77300):
        r.track(file, used, "1C")
    assert r.job["used"] == {"1C": 31.0}


def test_grams_waiting_on_a_slot_whose_spool_has_gone_go_to_the_number_given_but_not_into_the_slot():
    r = f.Register()
    r.check_in("Generic", "Black", "#000000", "PLA", 1000, DAY)
    r.check_in("Generic", "White", "#ffffff", "PLA", 1000, DAY)
    r.slot_seen("1B", BLACK)
    r.track("a.gcode", 0, "1B")
    r.track("a.gcode", 3356, "1B")
    r.end()
    r.slot_seen("1B", {**BLACK, "hex": "#ffffff"})        # the black spool out, a white one in, nothing confirmed
    r.confirm("1B", "F001")                              # the number on the black spool, for the grams it left
    assert r.spool("F001")["left"] == 990.0 and "stock" not in r.slots["1B"]
    r.confirm("1B", "F002")
    assert r.slots["1B"]["stock"] == "F002" and r.spool("F002")["left"] == 1000.0


def test_grams_from_a_slot_not_known_go_to_the_number_given_and_the_next_print_asks_again():
    r = f.Register()
    r.check_in("Generic", "Black", "#000000", "PLA", 1000, DAY)
    r.track("a.gcode", 0, None)
    r.track("a.gcode", 3356, None)
    assert r.end() == [{"slot": "?", "stock": None, "grams": 10.0, "cost": None}]
    assert r.confirm("?", "F001") == pytest.approx(10.0, abs=0.05) and r.spool("F001")["left"] == 990.0
    assert "?" not in r.slots, "not a slot: the next print with no slot said waits for its number again"
    r.track("b.gcode", 3356, None)
    assert r.end()[0]["stock"] is None


def test_the_start_of_a_print_before_the_printer_names_its_slot_is_that_slots():
    # as the K2 Plus did on 25 Oct 2026: printing, active slot unknown for the first minute (104 mm), then box_1_slot_3
    r = f.Register()
    r.track("tag Robert.gcode", 0, None)
    r.track("tag Robert.gcode", 104, None)
    r.track("tag Robert.gcode", 500, "1C")
    r.track("tag Robert.gcode", 900, "1D")
    assert r.job["used"] == {"1C": 500.0, "1D": 400.0}


def test_grams_from_a_spool_not_in_the_register_can_be_dropped():
    r = f.Register()
    r.check_in("Generic", "Black", "#000000", "PLA", 1000, DAY)
    r.slot_seen("1B", BLACK)
    r.track("a.gcode", 0, "1B")
    r.track("a.gcode", 3356, "1B")
    r.end()
    assert r.forget("1B") == pytest.approx(10.0, abs=0.05)
    assert r.view()["pending"] == {} and r.spool("F001")["left"] == 1000.0, "no spool loses anything"
    with pytest.raises(f.RegisterError) as err:
        r.forget("1B")
    assert err.value.key == "not_found"


def test_an_unknown_stock_number_is_refused_and_an_empty_one_clears():
    r = f.Register()
    r.check_in("Generic", "Black", "#000000", "PLA", 1000, DAY)
    r.slot_seen("1B", BLACK)
    with pytest.raises(f.RegisterError) as err:
        r.confirm("1B", "F099")
    assert err.value.key == "not_found"
    r.confirm("1B", "F001")
    r.confirm("1B", "")
    assert "stock" not in r.slots["1B"] and r.slots["1B"]["key"]


def test_a_spool_confirmed_in_another_slot_moves_there():
    r = f.Register()
    r.check_in("Generic", "Black", "#000000", "PLA", 1000, DAY)
    r.slot_seen("1A", BLACK)
    r.slot_seen("1B", BLACK)
    r.confirm("1A", "F001")
    r.confirm("1B", "F001")
    assert "stock" not in r.slots["1A"] and r.slots["1B"]["stock"] == "F001"
    assert r.view()["spools"][0]["slot"] == "1B"


def test_an_edited_spool_and_one_weighed():
    r = f.Register()
    r.check_in("Generic", "Black", "#000000", "PLA", 1000, DAY)
    s = r.update("F001", {"brand": "Elegoo", "left": 412, "hex": "#111111", "type": "PLA Matte"})
    assert (s["brand"], s["left"], s["hex"], s["type"], s["weight"]) == ("Elegoo", 412.0, "#111111", "PLA Matte", 1000.0)
    with pytest.raises(f.RegisterError):
        r.update("F001", {"left": -5})


def test_a_spool_used_up_or_removed_has_gone_out_of_stock():
    r = f.Register()
    r.today = lambda: DAY
    r.check_in("Generic", "Black", "#000000", "PLA", 10, DAY)
    r.check_in("Sunlu", "White", "#ffffff", "PLA", 1000, DAY)
    r.check_in("eSun", "Pink", "#ff37af", "PLA+", 1000, DAY)
    r.slot_seen("1B", BLACK)
    r.confirm("1B", "F001")
    r.track("a.gcode", 0, "1B")
    r.track("a.gcode", 5000, "1B")                       # 15 g from a 10 g spool
    r.end()
    assert r.spool("F001")["left"] == 0.0
    assert [(g["stock"], g["why"], g["out"]) for g in r.gone] == [("F001", "used_up", DAY)]
    r.remove("F001")
    assert [(g["stock"], g["why"]) for g in r.gone] == [("F001", "used_up")], "removed once used up: still used up"
    r.remove("F002")
    r.update("F003", {"left": 0})
    assert [(g["stock"], g["why"]) for g in r.gone_since()] == [("F003", "used_up"), ("F002", "removed"), ("F001", "used_up")]
    r.update("F003", {"left": 250})
    assert "F003" not in [g["stock"] for g in r.gone], "weighed, and not empty after all"
    assert f.Register(json.loads(json.dumps(r.to_dict()))).gone == r.gone


def test_recently_is_30_days_and_a_year_is_kept():
    r = f.Register()
    r.gone = [{"stock": "F001", "out": "2025-10-01", "why": "removed"}, {"stock": "F002", "out": "2026-09-20", "why": "removed"},
              {"stock": "F003", "out": "2026-10-01", "why": "used_up"}]
    r.today = lambda: DAY
    r.next = 4
    assert [g["stock"] for g in r.gone_since()] == ["F003"]
    r.check_in("Sunlu", "White", "#ffffff", "PLA", 1000, DAY)
    r.remove("F004")
    assert [g["stock"] for g in r.gone] == ["F002", "F003", "F004"], "older than a year: forgotten"


def test_the_register_keeps_through_storage():
    r = f.Register()
    r.check_in("Creality", "Purple", "#9e007e", "PLA", 1000, DAY)
    r.slot_seen("1D", PURPLE)
    r.track("a.gcode", 1200, "1D")
    again = f.Register(json.loads(json.dumps(r.to_dict())))
    assert again.to_dict() == r.to_dict() and again.next == 2


def test_a_price_gives_each_print_its_cost_and_grams_confirmed_later_join_it():
    r = f.Register()
    r.now = lambda: "2026-10-25T23:00"
    r.check_in("Sunlu", "Black", "#000000", "PLA", 1000, DAY, price=199)
    r.check_in("eSun", "Pink", "#ff37af", "PLA+", 1000, DAY, price="")
    r.check_in("Creality", "Purple", "#9e007e", "Hyper PLA", 1000, DAY, price=249.5)
    assert "price" not in r.spool("F002") and r.spool("F003")["price"] == 249.5
    r.slot_seen("1B", BLACK)
    r.slot_seen("1D", PURPLE)
    r.confirm("1B", "F001")
    for used, slot in ((0, "1B"), (3356, "1B"), (6712, "1D"), (10068, "1A")):
        r.track("tag Robert.gcode", used, slot)
    booked = r.end()
    assert [b["cost"] for b in booked] == [None, 1.99, 2.5], "1A has no spool yet; 10 g of 199 kr a kg; 10 g of 249.50"
    last = r.last_print
    assert (last["file"], last["ended"], last["grams"], last["cost"], last["uncosted"]) == ("tag Robert.gcode", "2026-10-25T23:00", 30.0, 4.49, 10.0)
    r.slot_seen("1A", {**BLACK, "hex": "#ff37af"})
    r.confirm("1A", "F003")                      # 1A was the purple spool: its 10 g join the print at 249.50 a kg
    assert r.last_print["cost"] == pytest.approx(6.99, abs=0.01) and r.last_print["uncosted"] == 0.0
    with pytest.raises(f.RegisterError):
        r.update("F001", {"price": -1})
    r.update("F001", {"price": None})
    assert "price" not in r.spool("F001")


def test_a_print_taking_a_spool_low_or_using_it_up_is_an_alert():
    r = f.Register()
    r.today = lambda: DAY
    r.check_in("Sunlu", "Black", "#000000", "PLA", 1000, DAY)
    r.update("F001", {"left": 110})
    r.slot_seen("1B", BLACK)
    r.confirm("1B", "F001")
    r.track("a.gcode", 0, "1B")
    r.track("a.gcode", 3356, "1B")                   # 10 g: 100 g left, 10 %
    r.end()
    assert r.alerts == [{"what": "low", "stock": "F001", "name": "Sunlu Black", "type": "PLA", "left": 100.0, "share": 10}]
    r.alerts.clear()
    r.track("b.gcode", 3356, "1B")                   # 10 g more: still low, said once
    r.end()
    assert r.alerts == []
    r.track("c.gcode", 40000, "1B")                  # used up
    r.end()
    assert [a["what"] for a in r.alerts] == ["used_up"] and r.gone[-1]["why"] == "used_up"
    r.alerts.clear()
    r.update("F001", {"left": 50})                    # weighed by hand: no alert
    assert r.alerts == []


def test_weighed_on_a_scale_less_the_brands_empty_spool():
    r = f.Register()
    r.check_in("Sunlu", "Black", "#000000", "PLA", 1000, DAY)
    r.check_in("sunlu", "White", "#ffffff", "PLA", 1000, DAY)
    with pytest.raises(f.RegisterError) as err:
        r.update("F001", {"weighed": 800})
    assert "empty Sunlu spool" in str(err.value)
    assert r.update("F001", {"weighed": 800, "tare": 180.5})["left"] == 619.5
    assert r.tares == {"sunlu": 180.5}
    assert r.update("F002", {"weighed": 500})["left"] == 319.5, "the brand's empty spool, kept"
    with pytest.raises(f.RegisterError):
        r.update("F002", {"weighed": 100})
    assert f.Register(json.loads(json.dumps(r.to_dict()))).tares == {"sunlu": 180.5}


def test_a_tag_says_the_material_a_weight_it_can_and_a_colour_of_its_own():
    r = f.Register()
    for brand, colour, hex_, kind, weight in (("Sunlu", "Black", "#000000", "PLA", 1000), ("Sunlu", "Black", "#000000", "PLA", 1000),
                                              ("eSun", "Pink", "#ff37af", "PETG", 750), ("Creality", "Teal", "#2f6f7a", "Hyper Stardust PLA", 1000),
                                              ("Polymaker", "Grey", "#808080", "PA-CF", 3000)):
        r.check_in(brand, colour, hex_, kind, weight, DAY)
    tags = [r.tag(f"F00{i}") for i in range(1, 6)]
    assert [t["material"] for t in tags] == ["Generic PLA", "Generic PLA", "Generic PETG", "Hyper Stardust PLA", "PA-CF"]
    assert [t["weight"] for t in tags] == [1000, 1000, 750, 1000, 1000]
    colours = [t["tag"] for t in tags]
    assert len(set(colours)) == 5 and "#000000" not in colours, "every tag its own colour, none a Creality chip's"
    assert all(f._near(c, h) and math.dist(*(tuple(int(x[i:i + 2], 16) for i in (1, 3, 5)) for x in (c, h))) < 11
               for c, h in zip(colours, ("#000000", "#000000", "#ff37af", "#2f6f7a", "#808080"))), "a few shades at most"
    assert r.tag("F001")["tag"] == colours[0], "given once, kept"
    assert f.tag_weight(300) == 250 and f.tag_weight(520) == 500 and f.tag_weight(675) == 750


def test_a_tagged_spool_is_found_by_the_colour_the_cfs_reads_whatever_its_brand():
    r = f.Register()
    r.check_in("Sunlu", "Black", "#000000", "PLA", 1000, DAY)
    r.check_in("Sunlu", "Black", "#000000", "PLA", 1000, DAY)
    second = r.tag("F002")["tag"]
    first = r.tag("F001")["tag"]
    read = {"loaded": True, "vendor": "Creality", "type": "PLA", "name": "Generic PLA", "rfid": "00001", "state": 2}
    r.slot_seen("1A", {**read, "hex": first})
    r.slot_seen("1B", {**read, "hex": second})
    assert (r.slots["1A"].get("stock"), r.slots["1B"].get("stock")) == ("F001", "F002"), "two spools alike, told apart"
    r.slot_seen("1C", {**read, "hex": "#000000"})
    assert "stock" not in r.slots["1C"], "an untagged black spool still waits for its number"
