"""AP/GS event requirement rules. Run: pytest"""

from bot.views import _requirements_error


def character(ap=133715, gs=2449):
    return {
        "char_name": "Meilink",
        "combat_power": ap,
        "item_level": gs,
    }


def test_no_requirements_accepts_anyone():
    assert _requirements_error({"min_ap": None, "min_gs": None}, None) is None


def test_requirements_need_a_linked_character():
    error = _requirements_error({"min_ap": 100000, "min_gs": None}, None)
    assert "linked character" in error


def test_ap_requirement_is_enforced():
    error = _requirements_error({"min_ap": 140000, "min_gs": None}, character())
    assert "140,000" in error and "133,715" in error


def test_gs_requirement_is_enforced():
    error = _requirements_error({"min_ap": None, "min_gs": 2500}, character())
    assert "2,500" in error and "2,449" in error


def test_character_meeting_both_requirements_is_allowed():
    assert (
        _requirements_error(
            {"min_ap": 120000, "min_gs": 2400},
            character(),
        )
        is None
    )
