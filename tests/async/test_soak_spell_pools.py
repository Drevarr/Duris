#!/usr/bin/env python3
"""The soak's casting pools hold only spells a class can cast.

skills.c keeps commented-out SPELL_ADD lines (and a commented-out healing blade). A
parser that read them gave the bots spells the server refuses ("You don't know that
spell!"), and praying bots then waited for prayers that never came.
"""

import sys

from _paths import ROOT

sys.path.insert(0, str(ROOT / "tests/scenarios"))
import soak  # noqa: E402

druid = {name for _, name in soak.SPELLS["DRUID"]}
ranger = {name for _, name in soak.SPELLS["RANGER"]}
assert not {"harmonic resonance", "firestorm", "mass barkskin"} & druid, druid
assert not {"firestorm", "healing blade", "mass barkskin"} & ranger, ranger
assert "nova" in druid  # an active SPELL_ADD still counts
print("PASS soak casting pools skip commented-out spells")
