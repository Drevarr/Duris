#!/usr/bin/env python3
"""Run the real Rage command and skill improvement function with exact rolls."""

from pathlib import Path
import subprocess
import tempfile

from _paths import ROOT, HARNESS_STUBS, extract_function


cpp = r'''
#include "abilities/abilities.h"
#include "core/prototypes.h"
#include "core/utils.h"
#include "classes/epic_skills.h"
#include "magic/spells.h"
#include "net/comm.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>

static room_data room{};
P_room world = &room;
Skill skills[MAX_SKILLS]{};
epic_teacher_skill epic_teachers[1]{};
static char_data actor{}, opponent{};
static pc_only_data pc{};
static affected_type rage_effect{};
static bool berserking, raging, recovering, pet;
static int activation_roll, improvement_roll, activation_checks, improvement_checks;
static int lag, published, recovery;
static std::string output;

int number(int low, int high) {
    if (low == 1 && high == 105) { ++activation_checks; return activation_roll; }
    if (low == 1 && high == 10000) { ++improvement_checks; return improvement_roll; }
    assert(low == 0 && high == 1);
    return 0; // No extra notch from Learning.
}
int dice(int, int) { assert(false); return 0; }
const Rolls live_rolls = {dice, number};
int get_property(const char *key, int fallback) {
    return !strcmp(key, "skill.notch.offensive") ? 5 : fallback;
}
bool chaos_mud_enabled() { return false; }
bool affected_by_spell(P_char, int type) {
    return (type == SKILL_BERSERK && berserking) || (type == SKILL_RAGE && raging) ||
           (type == SKILL_RAGE_REORIENT && recovering);
}
int GET_CHAR_SKILL_P(P_char ch, int skill) { return ch->only.pc->skills[skill].learned; }
P_char get_linked_char(P_char ch, ush_int type) {
    assert(ch == &opponent && type == LNK_PET);
    return pet ? &actor : nullptr;
}
bool SanityCheck(P_char, const char *) { return true; }
bool affect_timer(P_char, int, int tag) { assert(tag == TAG_PHYS_SKILL_NOTCH); return true; }
void send_to_char(const char *text, P_char) { output += text; }
void act(const char *, int, P_char, P_obj, void *, int) {}
void CharWait(P_char, int delay) { lag += delay; }
affected_type *affect_to_char(P_char, affected_type *af) {
    rage_effect = *af;
    ++published;
    return &rage_effect;
}
void set_short_affected_by(P_char, int type, int duration) {
    assert(type == SKILL_RAGE_REORIENT && duration > 0);
    ++recovery;
}
'''

for file, signature in (
    ("guild.c", "static int learning_extra_notch_roll("),
    ("guild.c", "bool notch_skill(P_char ch, int skill, float chance)"),
    ("actoth.c", "static int rage_failed_lag()"),
    ("actoth.c", "static double rage_lag()"),
    ("actoth.c", "static int rage_ragelord_lag()"),
    ("actoth.c", "static int rage_duration(P_char ch)"),
    ("actoth.c", "static int rage_rest(int dura)"),
    ("actoth.c", "void do_rage("),
):
    cpp += extract_function(file, signature) + "\n"

cpp += r'''
static void reset() {
    actor = {}; opponent = {}; pc = {}; room = {}; rage_effect = {};
    actor.only.pc = &pc;
    actor.specials.position = STAT_NORMAL + POS_STANDING;
    actor.player.m_class = CLASS_BERSERKER;
    actor.player.level = 50;
    actor.in_room = 0;
    opponent.specials.act = ACT_ISNPC;
    opponent.player.level = 50;
    pc.skills[SKILL_RAGE].learned = 40;
    pc.skills[SKILL_RAGE].taught = 100;
    skills[SKILL_RAGE].name = "rage";
    skills[SKILL_RAGE].targets = TAR_PHYS;
    berserking = true;
    raging = recovering = pet = false;
    activation_roll = 105;
    improvement_roll = 1;
    activation_checks = improvement_checks = lag = published = recovery = 0;
    output.clear();
}

int main() {
    // Every possible improvement roll: exact 2.5% failure and 5% success rates,
    // including non-berserkers with access and Ragelords.
    for (int cls : {CLASS_WARRIOR, CLASS_BERSERKER}) {
        for (int spec : {0, SPEC_RAGELORD}) {
            for (bool failed : {true, false}) {
                int gains = 0;
                for (int roll = 1; roll <= 10000; ++roll) {
                    reset();
                    actor.player.m_class = cls;
                    actor.player.spec = spec;
                    activation_roll = failed ? 41 : 40;
                    improvement_roll = roll;
                    do_rage(&actor, nullptr, 0);
                    const bool improved = roll <= (failed ? 250 : 500);
                    assert(pc.skills[SKILL_RAGE].learned == 40 + improved);
                    assert(activation_checks == 1 && improvement_checks == 1);
                    assert((output.find("improving") != std::string::npos) == improved);
                    assert(published == !failed && recovery == !failed);
                    if (failed) {
                        assert(lag == 2 * PULSE_VIOLENCE);
                        assert(output.find("unable to call forth") != std::string::npos);
                        assert(actor.specials.combat_tics == 0);
                    } else {
                        assert(lag == (cls == CLASS_BERSERKER && spec == SPEC_RAGELORD ?
                                       PULSE_VIOLENCE / 2 : 3 * PULSE_VIOLENCE / 2));
                        assert(rage_effect.type == SKILL_RAGE);
                        assert(rage_effect.bitvector2 == AFF2_FLURRY);
                    }
                    gains += improved;
                }
                assert(gains == (failed ? 250 : 500));
            }
        }
    }

    // Refused commands never count as failed attempts and cannot improve Rage.
    for (int refusal = 0; refusal < 7; ++refusal) {
        reset();
        switch (refusal) {
        case 0: actor.specials.position = STAT_DEAD; break;
        case 1: actor.specials.act2 |= PLR2_WAIT; break;
        case 2: actor.specials.affected_by2 |= AFF2_MAJOR_PARALYSIS; break;
        case 3: berserking = false; break;
        case 4: pc.skills[SKILL_RAGE].learned = 0; break;
        case 5: raging = true; break;
        case 6: recovering = true; break;
        }
        const int before = pc.skills[SKILL_RAGE].learned;
        do_rage(&actor, nullptr, 0);
        assert(pc.skills[SKILL_RAGE].learned == before);
        assert(activation_checks == 0 && improvement_checks == 0);
        assert(lag == 0 && published == 0 && recovery == 0);
    }

    // Failed attempts still obey the shared training cap and room/opponent rules.
    for (int restriction = 0; restriction < 5; ++restriction) {
        reset();
        switch (restriction) {
        case 0: pc.skills[SKILL_RAGE].learned = pc.skills[SKILL_RAGE].taught; break;
        case 1: room.room_flags = ROOM_SAFE; break;
        case 2: room.room_flags = ROOM_GUILD; break;
        case 3: actor.specials.fighting = &opponent; opponent.player.level = 1; break;
        case 4: actor.specials.fighting = &opponent; pet = true; break;
        }
        const int before = pc.skills[SKILL_RAGE].learned;
        do_rage(&actor, nullptr, 0);
        assert(pc.skills[SKILL_RAGE].learned == before);
        assert(activation_checks == 1 && improvement_checks == 0);
        assert(lag == 2 * PULSE_VIOLENCE && published == 0 && recovery == 0);
    }
    std::puts("PASS Rage notching: exact 2.5% failed / 5% successful rolls, class/spec parity, "
              "failed-attempt lag and effects, prerequisites and shared eligibility rules");
}
'''

build_root = ROOT / "bin/tests"
build_root.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="rage-notching-", dir=build_root) as tmp:
    path, binary = Path(tmp) / "harness.cpp", Path(tmp) / "harness"
    path.write_text(cpp)
    subprocess.run(
        ["g++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-Isrc",
         "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
         "-fno-omit-frame-pointer", "-no-pie", str(path), str(HARNESS_STUBS),
         "-o", str(binary)],
        cwd=ROOT, check=True,
    )
    subprocess.run([str(binary)], cwd=ROOT, check=True, timeout=30)
