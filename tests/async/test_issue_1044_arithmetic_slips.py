#!/usr/bin/env python3
"""Pin the arithmetic fixes from issue #1044 so the slips cannot come back.

Each pin names the corrected expression and the broken one it replaced.
Comments are stripped first, so prose cannot satisfy a pin.
"""

import re

from _paths import source
from _source_contract import strip_comments


def code(name):
    return re.sub(r"\s+", " ", strip_comments(source(name).read_text(encoding="utf-8")))


PINS = (
    # Apocalypse and Judgement cast in 3.5 spell pulses (31), not 3 (27).
    ("skills.c", "7 * PULSE_SPELLCAST / 2", 2, "(7 / 2) * PULSE_SPELLCAST"),
    # NPC monk skill caps at 100 like the other monk skills.
    ("new_skills.c", "skl_lvl = MIN(100, GET_LEVEL(ch) * 3);", 5, "MAX(100, GET_LEVEL(ch)"),
    # Charisma caps at 100, so low charisma and race change prices.
    ("shop.c", "cha_app[STAT_INDEX(MIN(100, GET_C_CHA(ch)))]", 4, "MAX(100, GET_C_CHA(ch))"),
    # Wizard eye range is level * 2, capped by the max-distance property.
    ("magic.c", 'MIN(level * 2, (int)get_property("spell.wizardEye.maxDistance", 100))', 1,
     'MAX(level * 2, (int)get_property("spell.wizardEye.maxDistance"'),
    # Blue Haze gives -20 AC at level 25 instead of 0.
    ("smoke.c", "af.modifier = -(4 * level / 5) * multi;", 1, "(4 / 5)"),
    # Spinal corruption's first save uses the plain Power difference.
    ("psionics.c", "if (StatSave(victim, APPLY_POW, POW_DIFF(ch, victim))) { send_to_char(\"&+RYou feel a twinge", 1,
     "MIN(1, GET_LEVEL(ch) - GET_LEVEL(victim))"),
    # Semi-casters memorize first circles at their own speed on a 0-based circle.
    ("memorize.c", "level = MAX(0, level - 2);", 1, "MAX(1, level - 2)"),
)

for name, fixed, count, broken in PINS:
    text = code(name)
    assert text.count(fixed) == count, f"{name}: expected {count} x {fixed!r}"
    assert broken not in text, f"{name}: broken {broken!r} is back"

print("issue #1044 arithmetic pins: ok")
