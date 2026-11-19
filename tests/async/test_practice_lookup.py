#!/usr/bin/env python3
"""Run the production do_practice() lookup with a guildmaster and in a guildhall library.

The practicing player is taught directly, never found again by name (their mirror images
share it). A name that is not exact falls back to the first prefix match, and a name that
matches nothing is refused before any skill table is indexed with it. A guildhall
library with no guildmaster copies spells to the player but teaches no skills, so
practicing a skill there says no teacher is present.
"""
from pathlib import Path
import subprocess
import tempfile

from _paths import HARNESS_STUBS, ROOT, extract_function

HARNESS = r'''
#include "core/structs.h"
#include "core/prototypes.h"
#include "core/utils.h"
#include "core/utility.h"
#include "cmd/interp.h"
#include "magic/spells.h"
#include <cassert>
#include <cstring>
#include <string>
#include <strings.h>

Skill skills[MAX_AFFECT_TYPES + 1];
char *spells[MAX_AFFECT_TYPES + 1];
static char_data *present_teacher;
static obj_data library_tome, held_book;
static bool in_library;
static std::string said;
static char_data *taught;
static int taught_spell = -1;
static char_data *taught_by;
static obj_data *taught_book;

static void valid_skill(int skill) { assert(skill >= 0 && skill < MAX_SKILLS); }
P_char FindTeacher(P_char) { return present_teacher; }
P_obj find_gh_library_book_obj(P_char) { return in_library ? &library_tome : nullptr; }
bool meming_class(P_char) { return true; }
int GET_LVL_FOR_SKILL(P_char, int skill) { valid_skill(skill); return 1; }
ClassSkillInfo SKILL_DATA_ALL(P_char, int skill) {
    valid_skill(skill);
    ClassSkillInfo result{};
    result.rlevel[0] = 1;
    return result;
}
int GET_CHAR_SKILL_P(P_char ch, int skill) { valid_skill(skill); return ch->only.pc->skills[skill].learned; }
int knows_spell(P_char, int skill) { valid_skill(skill); return TRUE; }
int get_spell_circle(P_char, int skill) { valid_skill(skill); return 1; }
int get_max_circle(P_char) { return 12; }
int SkillRaiseCost(P_char, int) { return 0; }
int SUB_MONEY(P_char, int, int) { return TRUE; }
float get_property(const char *, double fallback) { return fallback; }
P_obj SpellInSpellBook(P_char, int, int) { return nullptr; }
int ScriberSillyChecks(P_char, int) { return TRUE; }
P_obj SpellBookAtHand(P_char) { return &held_book; }
void add_scribing(P_char ch, int spl, P_obj book, int flag, P_obj obj, P_char teacher) {
    assert(!flag && !obj);
    taught = ch; taught_spell = spl; taught_book = book; taught_by = teacher;
}
void send_to_char(const char *text, P_char) { said += text; }
void mobsay(P_char, const char *text) { said += text; said += "\n"; }
char *skip_spaces(char *text) { while (*text == ' ') ++text; return text; }
int strn_cmp(const char *a, const char *b, unsigned n) { return strncasecmp(a, b, n); }
char *coin_stringv(int, int) { static char none[] = "nothing"; return none; }
void prac_all_spells(P_char) { assert(false); }
bool is_spec_spell(P_char, int) { return false; }
int IS_CASTER(P_char) { return TRUE; }
int IS_SEMI_CASTER(P_char) { return FALSE; }
int SpellCopyCost(P_char, int) { return 0; }
void page_string(descriptor_data *, char *, int) { assert(false); }
int number(int low, int) { return low; }

// PRODUCTION

static void practice(char_data &ch, const char *what) {
    said.clear(); taught = taught_by = nullptr; taught_spell = -1; taught_book = nullptr;
    char arg[64];
    std::strcpy(arg, what);
    do_practice(&ch, arg, CMD_PRACTICE);
}

int main() {
    for (int i = 0; i < MAX_AFFECT_TYPES; ++i) spells[i] = const_cast<char *>("Undefined");
    spells[MAX_AFFECT_TYPES] = const_cast<char *>("\n");
    spells[SPELL_FEEBLEMIND] = const_cast<char *>("feeblemind");
    spells[SPELL_GUARDIAN_SPIRITS] = const_cast<char *>("guardian spirits");
    spells[SKILL_GUARD] = const_cast<char *>("guard");
    spells[SKILL_BASH] = const_cast<char *>("bash");
    skills[SPELL_FEEBLEMIND].name = "feeblemind";
    skills[SPELL_FEEBLEMIND].targets = TAR_SPELL;

    pc_only_data pc{};
    char_data player{}, master{};
    player.only.pc = &pc;
    player.player.level = master.player.level = 30;
    player.specials.position = master.specials.position = STAT_RESTING | POS_SITTING;
    SET_BIT(master.specials.act, ACT_ISNPC | ACT_TEACHER);

    // A guildmaster teaches the player who asked, by full name or by its start.
    present_teacher = &master;
    for (const char *name : {"feeblemind", "feeblem"}) {
        practice(player, name);
        assert(taught == &player && taught_by == &master);
        assert(taught_spell == SPELL_FEEBLEMIND && taught_book == &held_book);
    }

    // An exact name wins over an earlier entry it is the start of.
    pc.skills[SKILL_GUARD].taught = 100;
    practice(player, "guard");
    assert(pc.skills[SKILL_GUARD].learned == 1 && !taught);

    // A name that matches nothing never reaches a skill table.
    practice(player, "zzqqxx");
    assert(said == "You have never heard of such a skill or spell.\n" && !taught);

    // A guildhall library copies spells and teaches no skills.
    present_teacher = nullptr;
    in_library = true;
    practice(player, "feeblemind");
    assert(taught == &player && !taught_by && taught_spell == SPELL_FEEBLEMIND);
    pc.skills[SKILL_BASH].taught = 100;
    practice(player, "bash");
    assert(said == "And just who did you plan on teaching you?!?\n" && !taught);
    assert(pc.skills[SKILL_BASH].learned == 0);

    std::puts("practice teaches the player and refuses names it cannot find");
}
'''

(ROOT / "bin/tests").mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="practice-lookup-", dir=ROOT / "bin/tests") as build:
    source = Path(build) / "harness.cpp"
    binary = Path(build) / "harness"
    source.write_text(HARNESS.replace(
        "// PRODUCTION",
        extract_function("interp.c", "int search_block(char *arg, const char **list, int exact)")
        + extract_function("guild.c", "int IsTaughtHere(P_char ch, int skl)")
        + extract_function("guild.c", "void do_practice(P_char ch, char *arg, int")))
    subprocess.run(["g++", "-std=c++20", "-g", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-Isrc", "-I/usr/include/mysql",
                    str(source), str(HARNESS_STUBS), "-o", str(binary)], cwd=ROOT, check=True)
    subprocess.run([str(binary)], check=True, timeout=10)
