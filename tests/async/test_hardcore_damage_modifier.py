#!/usr/bin/env python3
"""The Hardcore damage modifier is applied once, from lib/hardcore.cfg (issue #1087).

Every Hardcore predicate in the raw-damage table runs with the global -75% cut
through raw_damage's own profile code, so a second copy of the modifier, or a
hard-coded value, changes the damage a pairing deals and fails the test.
"""

from pathlib import Path
import os
import subprocess
import tempfile

from _paths import ROOT, extract_function, source


def predicates(table: str) -> list[str]:
    """Each MAKE_DAM_MOD_PRED() lambda in a predicate table, in table order."""
    found = []
    start = table.find("MAKE_DAM_MOD_PRED()")
    while start != -1:
        depth, end = 0, table.index("{", start)
        while True:
            depth += (table[end] == "{") - (table[end] == "}")
            end += 1
            if not depth:
                break
        found.append(table[start:end])
        start = table.find("MAKE_DAM_MOD_PRED()", end)
    return found


dam_mods = source("dam_mods.c").read_text(encoding="utf-8")
raw_table = dam_mods[dam_mods.index("dam_mod_predicate raw_damage_modifiers[]") :]
raw_table = raw_table[: raw_table.index("static_assert(ARRAY_SIZE(raw_damage_modifiers)")]
raw_predicates = predicates(raw_table)
hardcore = [body for body in raw_predicates if "IS_HARDCORE" in body]
global_cut = [body for body in raw_predicates if "dam_mod->mod += -0.75;" in body]
assert hardcore, "no Hardcore raw-damage predicate"
assert len(global_cut) == 1, len(global_cut)

raw_damage = extract_function("fight.c", "int raw_damage(")
profile = raw_damage[
    raw_damage.index("damage_profile damProf;") : raw_damage.index("dam = MAX(1, dam);")
]

PRELUDE = r"""
#include "core/prototypes.h"
#include "core/utils.h"
#include "combat/damage.h"
#include "combat/dam_mods.h"
#include "world/hardcore_config.h"
#include <cmath>
#include <cstdio>
#include <cstdlib>

static hardcore_config config;
const hardcore_config *hardcore_config_get(void) { return &config; }
"""

DRIVER = r"""
static double profile(P_char ch, P_char victim, double dam, uint flags,
                      struct damage_messages *messages)
{
PROFILE
    return dam;
}

static char_data normal{}, other{}, hardcore{}, rival{};

// Damage this pairing deals, relative to the same hit between two ordinary characters.
static double ratio(P_char ch, P_char victim, uint flags)
{
    return profile(ch, victim, 400, flags, nullptr) / profile(&normal, &other, 400, flags, nullptr);
}

static void expect(const char *label, double actual, double expected)
{
    if (std::fabs(actual - expected) > 1e-4) {
        std::fprintf(stderr, "%s: %.6f x normal damage, expected %.6f\n", label, actual, expected);
        std::abort();
    }
}

int main()
{
    SET_BIT(hardcore.specials.act2, PLR2_HARDCORE_CHAR);
    SET_BIT(rival.specials.act2, PLR2_HARDCORE_CHAR);
    config.bonus_damage_outgoing_multiplier = 1.09f;
    config.bonus_damage_incoming_multiplier = 0.91f;
    expect("ordinary pairing", profile(&normal, &other, 400, 0, nullptr), 100);
CHECKS
    std::puts("PASS hardcore damage modifier applied once, from hardcore.cfg");
}
"""

# A More mod multiplies damage, so 1.09 / 0.91 in hardcore.cfg mean exactly that, with or
# without the -0.75 cut. As an Increased mod it would sum with the cut and be worth +-36%.
CHECKS = r"""
    expect("Hardcore attacker", ratio(&hardcore, &normal, 0), 1.09);
    expect("Hardcore victim", ratio(&normal, &hardcore, 0), 0.91);
    // Each side's multiplier applies, so they do not cancel out between two Hardcore characters.
    expect("Hardcore pair", ratio(&hardcore, &rival, 0), 1.09 * 0.91);
    expect("Hardcore attacker, no reduction", ratio(&hardcore, &normal, PHSDAM_NOREDUCE), 1.09);
    expect("Hardcore victim, no reduction", ratio(&normal, &hardcore, PHSDAM_NOREDUCE), 0.91);
    config.bonus_damage_outgoing_multiplier = 1.25f;
    config.bonus_damage_incoming_multiplier = 0.95f;
    expect("configured attacker", ratio(&hardcore, &normal, 0), 1.25);
    expect("configured victim", ratio(&normal, &hardcore, 0), 0.95);
    expect("configured pair", ratio(&hardcore, &rival, 0), 1.25 * 0.95);
"""

table = (
    "dam_mod_predicate raw_damage_modifiers[] = {\n"
    + ",\n".join(hardcore + global_cut)
    + "\n};\n"
)
production = extract_function("utility.c", "float BOUNDEDF(") + "\n" + table
out = ROOT / "bin/tests"
out.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="hardcore-damage-", dir=out) as temporary:
    cpp, binary = Path(temporary) / "test.cpp", Path(temporary) / "test"
    cpp.write_text(
        PRELUDE + production + DRIVER.replace("PROFILE", profile).replace("CHECKS", CHECKS)
    )
    subprocess.run(
        [
            "g++", "-std=c++20", "-g", "-Wall", "-Wextra", "-Werror", "-Isrc",
            "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie",
            str(cpp), "-o", str(binary),
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [str(binary)],
        check=True,
        timeout=30,
        env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0",
             "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1"},
    )
