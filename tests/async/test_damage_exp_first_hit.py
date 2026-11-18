#!/usr/bin/env python3
"""A first hit that takes an NPC below 0 HP earns its damage experience (soak finding).

raw_damage() gives damage experience for HP an NPC loses below the lowest it
has been, MIN(dam, lowest_hit - hit). lowest_hit starts at INT_MAX, so the
first hit that leaves the NPC below 0 HP overflowed int (UBSan, found by the
ASan/UBSan soak: "2147483647 - -11 cannot be represented in type 'int'"). In
practice the wrapped negative reached gain_exp(), which starts from a base of 1.

Compiles the production experience block of raw_damage() under UBSan and checks
the experience for a fresh NPC hit from full HP to -11, and for a later hit.
"""

import os
import subprocess
import tempfile
from pathlib import Path

from _paths import ROOT, extract_function

HARNESS = r'''
#include "core/prototypes.h"
#include "core/utils.h"
#include "combat/damage.h"
#include <cassert>
#include <climits>
#include <cstdio>

static int last_exp = -1;
int gain_exp(P_char, P_char, const int value, int type)
{
	assert(type == EXP_DAMAGE);
	last_exp = value;
	return value;
}

static void damage_exp(P_char ch, P_char victim, double dam, uint flags)
{
// BLOCK
}

int main()
{
	char_data attacker{}, mob{};
	npc_only_data npc{};
	mob.specials.act = ACT_ISNPC;
	mob.only.npc = &npc;
	npc.lowest_hit = INT_MAX; // as every mobile starts (mobconv.c)

	mob.points.hit = -11; // a 20-point first hit from 9 HP
	damage_exp(&attacker, &mob, 20, 0);
	assert(last_exp == 20 && npc.lowest_hit == -11);

	mob.points.hit = -30; // a later hit only pays for the new ground
	damage_exp(&attacker, &mob, 25, 0);
	assert(last_exp == 19 && npc.lowest_hit == -30);
	std::puts("first-hit damage experience neither overflows nor shrinks to 1");
}
'''

raw = extract_function("fight.c", "int raw_damage(")
start = raw.index("\t\t// Exps for damage")
end = raw.index("\t\tif (damAccumulator)", start)
(ROOT / "bin/tests").mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="damage-exp-", dir=ROOT / "bin/tests") as tmp:
    source = Path(tmp) / "damage_exp.cpp"
    source.write_text(HARNESS.replace("// BLOCK", raw[start:end]))
    binary = source.with_suffix("")
    subprocess.run(["g++", "-std=c++20", "-g", "-O1", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=undefined", "-Isrc", "-I/usr/include/mysql",
                    str(source), "-o", str(binary)], cwd=ROOT, check=True)
    subprocess.run([str(binary)], check=True, env=dict(os.environ, UBSAN_OPTIONS="halt_on_error=1"))
