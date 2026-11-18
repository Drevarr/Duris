#!/usr/bin/env python3
"""Combat-mind must raise a reduced attack multiplier to its configured floor,
and no multiplier above 1.0 may reach the attack divisor (#1044)."""

from _paths import SRC
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
fight = (SRC / "fight.c").read_text()

combat_mind = fight.split("if (affected_by_spell(ch, SPELL_COMBAT_MIND))", 1)[1]
combat_mind = combat_mind.split("// we ceil to not round off attacks", 1)[0]

floor = fight.split("float combat_mind_attack_floor()", 1)[1].split("}", 1)[0]
assert 'get_property("attacks.combatMind.multiplier", 0.75)' in floor
assert "float cmMulti = combat_mind_attack_floor();" in combat_mind
assert "if (attacksMultiplier < cmMulti)" in combat_mind
assert "attacksMultiplier = cmMulti;" in combat_mind
assert "cmMulti = cmMulti;" not in combat_mind

# A multiplier above 1.0 would make div_attacks 0 and index attacks[] past
# number_attacks, so the clamp must come after every assignment and before use.
clamp = "attacksMultiplier = MIN(attacksMultiplier, 1.0f);"
assert fight.count(clamp) == 1
assert fight.index("attacksMultiplier = cmMulti;") < fight.index(clamp)
assert fight.index(clamp) < fight.index("div_attacks = (int)(1 / attacksMultiplier);")

print("combat attack multiplier contract passed")
