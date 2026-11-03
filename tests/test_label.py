"""A spool's label read from a photo, tidied into the check-in form's fields, without Home Assistant:
python -m pytest tests -q. The answers are the shapes Gemini gives through Home Assistant's AI Task (2 Nov 2026)."""
import _load  # noqa: F401
from custom_components.printer_panel import labelread as lr

BRANDS = ["Creality", "Generic", "Bambu Lab", "eSun", "Elegoo", "RS Pro"]
TYPES = ["PLA", "Hyper PLA", "PLA+", "PLA Matte", "PETG", "TPU"]


def _google(code, message, status, extra=""):
    """A Gemini failure as Home Assistant's Google integration words it (3 Nov 2026): its preface, then Google's JSON."""
    return (lr._PREFACE + ': {\n  "error": {\n    "code": %d,\n    "message": "%s",\n    "status": "%s"%s\n  }\n}\n'
            % (code, message, status, extra))


def test_a_busy_ai_and_a_used_up_quota_are_told_apart():
    busy = _google(503, "This model is currently experiencing high demand. Please try again later.", "UNAVAILABLE")
    quota = _google(429, "You exceeded your current quota, please check your plan and billing details. Please retry in 9h 3m 2s.",
                    "RESOURCE_EXHAUSTED", ',\n    "details": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]')
    gone = _google(404, "This model models/gemini-2.5-flash is no longer available to new users.", "NOT_FOUND")
    assert lr.is_busy(Exception(busy)), "a 503 spike is worth another try"
    assert not lr.is_busy(Exception(quota)), "a day's quota is not"
    assert not lr.is_busy(Exception(gone)), "'no longer available' is not 'unavailable'"
    assert lr.reason(Exception(quota)) == "You exceeded your current quota, please check your plan and billing details. Please retry in 9h 3m 2s."
    assert lr.reason(Exception(gone)) == "This model models/gemini-2.5-flash is no longer available to new users."
    assert lr.reason(Exception(lr._PREFACE + ": This model is overloaded.")) == "This model is overloaded.", "plain text after the preface"
    assert lr.reason(Exception("AI Task entity ai_task.x not found")) == "AI Task entity ai_task.x not found", "not Google's: as it is"
    assert lr.reason(Exception("")) == "Exception"


def test_a_full_label():
    got = lr.label_fields({"brand": "ESUN", "colour": "fire engine red", "hex": "#C8102E", "type": "pla+", "weight": 1000}, BRANDS, TYPES)
    assert got == {"brand": "eSun", "colour": "Fire engine red", "hex": "#c8102e", "type": "PLA+", "weight": 1000}


def test_a_creality_product_keeps_its_name():
    got = lr.label_fields({"brand": "creality", "colour": "Teal", "hex": "008080", "type": "Hyper Stardust PLA", "weight": 1}, BRANDS, TYPES)
    assert got == {"brand": "Creality", "colour": "Teal", "hex": "#008080", "type": "Hyper Stardust PLA", "weight": 1000}


def test_kilograms_and_odd_weights():
    assert lr.label_fields({"weight": 0.75}, BRANDS, TYPES) == {"weight": 750}
    assert lr.label_fields({"weight": "250"}, BRANDS, TYPES) == {"weight": 250}
    assert lr.label_fields({"weight": 0}, BRANDS, TYPES) == {}
    assert lr.label_fields({"weight": 50000}, BRANDS, TYPES) == {}
    assert lr.label_fields({"weight": "a lot"}, BRANDS, TYPES) == {}


def test_nothing_read_leaves_the_form_alone():
    assert lr.label_fields(None, BRANDS, TYPES) == {}
    assert lr.label_fields({"brand": "Unknown", "colour": "", "hex": "not a colour", "type": "n/a"}, BRANDS, TYPES) == {}
    # "Generic" is what the CFS calls any other brand: no maker read, so the brand is not filled in
    assert "brand" not in lr.label_fields({"brand": "generic"}, BRANDS, TYPES)


def test_a_new_brand_is_kept_as_read():
    assert lr.label_fields({"brand": "  Sunlu  ", "type": "Silk  PLA"}, BRANDS, TYPES) == {"brand": "Sunlu", "type": "Silk PLA"}


def test_the_instructions_carry_the_forms_spellings():
    text = lr.instructions(BRANDS, TYPES)
    assert "eSun" in text and "Hyper PLA" in text and "do not guess a maker" in text
    assert set(lr.STRUCTURE) == {"brand", "colour", "hex", "type", "weight"}
