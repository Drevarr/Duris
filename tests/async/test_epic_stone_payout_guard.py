#!/usr/bin/env python3
"""epic_stone_payout must never divide by a zero player count (#1044).

A grouped toucher with no counted PC and a stone whose suggested group size
is 0 leaves num_players at 0; the guard must sit before the divide.
"""

from _paths import source
from _source_contract import function_bodies

body = function_bodies(source("epic.c").read_text(encoding="utf-8"),
                       r"\bint\s+epic_stone_payout\s*\(")[0]
guard = body.index("num_players = MAX(1, num_players);")
assert guard < body.index("/ num_players")

print("epic stone payout guard passed")
