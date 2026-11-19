#!/usr/bin/env python3
"""Enchant weapon's MAGIC flag survives an earlier bless fading (issue #1124).

Bless saves the weapon's extra2 flags as a baseline, and its fade rebuilds the
flags from that baseline. The production object-affect code, set_obj_extra2_flags()
and spell_enchant_weapon() run here: bless, enchant, then the hit path's fade.
"""
from pathlib import Path
import subprocess
import tempfile

from _paths import ROOT, HARNESS_STUBS, extract_function, source

affects = "".join(extract_function("affects.c", signature) + "\n" for signature in (
    "struct obj_affect *get_obj_affect(", "void recalculate_obj_extra(",
    "void set_obj_base_extra2_flag(", "void obj_affect_remove(",
    "void set_obj_affected_extra(", "int affect_from_obj("))
magic = "".join(extract_function("magic.c", signature) + "\n" for signature in (
    "static int enchant_weapon_hitroll(", "static int enchant_weapon_damroll(",
    "static int enchant_weapon_added_hitroll(", "void spell_enchant_weapon("))
fight = source("fight.c").read_text(encoding="utf-8")
fade = fight[fight.index("\t\taffect_from_obj(weapon, SPELL_BLESS);"):]
fade = fade[: fade.index("\t}")]

PRELUDE = r"""
#include "core/prototypes.h"
#include "core/utils.h"
#include "core/mm.h"
#include "magic/spells.h"
#include "world/events.h"
#include "net/comm.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
mm_ds *dead_obj_affect_pool;
mm_ds *mm_create(const char *, size_t, size_t, unsigned) { return nullptr; }
void *_mm_get(mm_ds *, const char *, int) { return new obj_affect{}; }
void mm_release(mm_ds *, void *af) { delete static_cast<obj_affect *>(af); }
void event_obj_affect(P_char, P_char, P_obj, void *) {}
// Bless here never times out, so no object-affect event is scheduled or cancelled.
nevent_schedule_result add_event(event_func, int, P_char, P_char, P_obj, int, const void *, int) { std::abort(); }
nevent_handle nevent_handle_from_event(P_nevent) { std::abort(); }
nevent_cancel_result nevent_cancel(nevent_handle) { std::abort(); }
"""

DRIVER = r"""
static void fade_bless(P_obj weapon)
{
FADE
}

int main()
{
    char_data caster{};
    obj_data weapon{};
    weapon.type = ITEM_WEAPON;
    set_obj_affected_extra(&weapon, -1, SPELL_BLESS, 50, ITEM2_BLESS);
    spell_enchant_weapon(30, &caster, nullptr, 0, nullptr, &weapon);
    assert(IS_SET(weapon.extra2_flags, ITEM2_MAGIC) && IS_SET(weapon.extra2_flags, ITEM2_BLESS));
    fade_bless(&weapon);
    assert(IS_SET(weapon.extra2_flags, ITEM2_MAGIC) && !IS_SET(weapon.extra2_flags, ITEM2_BLESS));
    assert(!weapon.affects);

    // After a reload the bless comes back without its old baseline, so the new one already
    // holds BLESS; the fade's own REMOVE_BIT is what clears it then.
    obj_data reloaded{};
    reloaded.type = ITEM_WEAPON;
    reloaded.extra2_flags = ITEM2_BLESS;
    set_obj_affected_extra(&reloaded, -1, SPELL_BLESS, 50, ITEM2_BLESS);
    spell_enchant_weapon(30, &caster, nullptr, 0, nullptr, &reloaded);
    fade_bless(&reloaded);
    assert(IS_SET(reloaded.extra2_flags, ITEM2_MAGIC) && !IS_SET(reloaded.extra2_flags, ITEM2_BLESS));
    std::puts("PASS enchant weapon keeps MAGIC when an earlier bless fades");
}
"""

out = ROOT / "bin/tests"
out.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="enchant-bless-fade-", dir=out) as temporary:
    cpp, binary = Path(temporary) / "test.cpp", Path(temporary) / "test"
    cpp.write_text(PRELUDE + affects + magic + DRIVER.replace("FADE", fade))
    subprocess.run(
        ["g++", "-std=c++20", "-g", "-Wall", "-Wextra", "-Isrc",
         "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie",
         "-ffunction-sections", "-fdata-sections", str(cpp), str(HARNESS_STUBS),
         "-Wl,--gc-sections", "-o", str(binary)],
        cwd=ROOT,
        check=True,
    )
    subprocess.run([str(binary)], check=True, timeout=30)
