#!/usr/bin/env python3
"""Run the named preparation handler and its real two-stage callback against a pulse clock."""
from pathlib import Path
import subprocess
import tempfile

from _paths import HARNESS_STUBS, ROOT, extract_function

production = "\n".join(extract_function("memorize.c", prefix) for prefix in (
    "bool book_class(", "bool praying_class(", "bool meming_class(", "static bool uses_slot_recovery(",
    "static bool schedule_memorize(", "static bool has_preparation_book(", "void handle_memorize(P_char ch)",
    "void event_memorize(P_char ch,", "void do_prioritize(",
))
prelude = r'''
#include "core/prototypes.h"
#include "core/utils.h"
#include "cmd/interp.h"
#include "net/comm.h"
#include "net/gmcp.h"
#include "magic/spells.h"
#include "world/events.h"
#include "persistence/persistence_checkpoint.h"
#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <string>
#include <vector>

Skill skills[MAX_SKILLS];
const char *spells[MAX_SKILLS], *command[] = {"\n"};
char Gbuf1[MAX_STRING_LENGTH];
static int tick, dirty, submissions, interval, missing_book, max_circle = 2;
static bool reject, chaos, rudiments;
static nevent_data event;
static std::string output;
static obj_data book;
void event_memorize(P_char, P_char, P_obj, void *);
int GET_PRIME_CLASS(P_char ch, uint cls) { return ch->player.m_class & cls; }
int GET_SECONDARY_CLASS(P_char ch, uint cls) { return ch->player.secondary_class & cls; }
int GET_CLASS(P_char ch, uint cls) { return GET_PRIME_CLASS(ch, cls) || GET_SECONDARY_CLASS(ch, cls); }
int is_wearing_necroplasm(P_char) { return 0; }
bool chaos_mud_enabled() { return chaos; }
bool has_innate(P_char, int innate) { assert(innate == INNATE_ARCANE_RUDIMENTS); return rudiments; }
P_obj SpellInSpellBook(P_char, int spell, int mode) {
    assert(mode == (SBOOK_MODE_IN_INV | SBOOK_MODE_AT_HAND | SBOOK_MODE_ON_BELT | SBOOK_MODE_ON_GROUND));
    return spell == missing_book ? nullptr : &book;
}
int get_max_circle(P_char) { return max_circle; }
int get_spell_circle(P_char, int spell) { return spell == SPELL_FULL_HEAL ? 2 : 1; }
static int get_circle_memtime(P_char, int circle) { return 20 * circle; }
void send_to_char(const char *message, P_char) { output += message; }
void send_to_char_f(P_char, const char *fmt, ...) {
    char buf[256]; va_list args; va_start(args, fmt);
    vsnprintf(buf, sizeof(buf), fmt, args); va_end(args); output += buf;
}
void act(const char *, int, P_char, P_obj, void *, int) {}
void handle_undead_mem(P_char) { assert(false); }
void stop_meditation(P_char ch) { REMOVE_BIT(ch->specials.affected_by, AFF_MEDITATE); }
void show_stop_memorizing(P_char ch, memorization_stop_reason) {
    REMOVE_BIT(ch->specials.affected_by2, AFF2_MEMORIZING); stop_meditation(ch);
}
int get_property(const char *, int fallback) { return fallback; }
bool notch_skill(P_char, int, float) { return false; }
int GET_CHAR_SKILL_P(P_char, int) { return 0; }
int number(int, int high) { return high; } // Complete after both halves.
void disarm_char_nevents(P_char ch, event_func_type f) { assert(f == event_memorize); ch->nevents = nullptr; }
P_nevent get_scheduled(P_char ch, event_func_type f) { assert(f == event_memorize); return ch->nevents; }
void mark_player_dirty_components(int, player_component_mask_t mask) { assert(mask == PLAYER_COMPONENT_AFFECTS); ++dirty; }
nevent_schedule_result add_event(event_func f, int delay, P_char ch, P_char, P_obj,
                                 int, const void *data, int size) {
    assert(f == event_memorize && !ch->nevents); ++submissions;
    if (reject) return {nevent_schedule_status::null_callback, {}};
    interval = data ? *static_cast<const int *>(data) : 0;
    assert(size == (data ? sizeof(int) : 0));
    event.data = data ? &interval : nullptr;
    event.due_tick = tick + delay; ch->nevents = &event;
    return {nevent_schedule_status::scheduled, {}};
}
'''
driver = r'''
struct Fixture {
    char_data ch{};
    pc_only_data pc{};
    descriptor_data desc{};
    affected_type head{}, a{}, ready{}, b{}, other{}, c{}, tail{};
    Fixture() {
        dirty = submissions = tick = missing_book = 0;
        reject = rudiments = chaos = false; max_circle = 2;
        ch.only.pc = &pc; ch.player.m_class = CLASS_CLERIC; ch.player.race = RACE_HUMAN;
        SET_POS(&ch, STAT_RESTING | POS_SITTING);
        ch.desc = &desc; desc.character = &ch; desc.gmcp_interests = GMCP_SUPPORT_SPELL_PREPARATION;
        a.type = b.type = c.type = ready.type = TAG_MEMORIZE;
        a.modifier = SPELL_BLESS; b.modifier = c.modifier = ready.modifier = SPELL_FULL_HEAL;
        ready.flags = MEMTYPE_FULL; b.level = 7; c.level = 11;
        ch.affected = &head; head.next = &a; a.next = &ready; ready.next = &b;
        b.next = &other; other.next = &c; c.next = &tail;
    }
    void order(std::initializer_list<affected_type *> expected) {
        auto *af = ch.affected;
        for (auto *node : expected) { assert(af == node); af = af->next; }
        assert(!af && ready.flags == MEMTYPE_FULL && b.level == 7 && c.level == 11);
    }
    void prioritize(std::string name) { output.clear(); do_prioritize(&ch, name.data(), 0); }
    void arm(bool second_half) {
        ch.specials.affected_by2 |= AFF2_MEMORIZING; ch.specials.affected_by |= AFF_MEDITATE;
        int first_interval = 20;
        assert(schedule_memorize(&ch, 10, second_half ? nullptr : &first_interval));
        tick = 9; desc.gmcp_spell_preparation_pending = false;
    }
    void fire() {
        assert(ch.nevents); tick = event.due_tick; int time = interval;
        ch.nevents = nullptr; event_memorize(&ch, nullptr, nullptr, time ? &time : nullptr);
    }
};

int main() {
    std::fill_n(spells, LAST_SPELL + 1, "!unused!");
    for (auto [spell, name] : {std::pair{SPELL_BLESS, "bless"}, {SPELL_FULL_HEAL, "full heal"},
                               {SPELL_ARMOR, "armor"}, {SPELL_INVISIBILITY, "invisibility"}}) {
        spells[spell] = skills[spell].name = name; skills[spell].targets = TAR_SPELL;
        skills[spell].spell_pointer = [](int,P_char,char*,int,P_char,P_obj){};
    }
    spells[LAST_SPELL + 1] = "\n";
    for (bool second_half : {false, true}) {
        Fixture f; f.arm(second_half);
        f.prioritize(" \tFuLl He \t"); f.order({&f.head,&f.b,&f.c,&f.a,&f.ready,&f.other,&f.tail});
        assert(output.find("2 pending copies of full heal") != std::string::npos);
        assert(submissions == 2 && dirty == 1 && event.due_tick == 29 && interval == 40);
        assert(IS_AFFECTED(&f.ch, AFF_MEDITATE) && IS_AFFECTED2(&f.ch, AFF2_MEMORIZING));
        assert(f.desc.gmcp_spell_preparation_pending);
        f.desc.gmcp_spell_preparation_pending = false;
        f.prioritize("full heal");
        assert(output.find("already first") != std::string::npos && !f.desc.gmcp_spell_preparation_pending);
        assert(submissions == 2 && dirty == 1 && event.due_tick == 29);
        f.fire(); assert(event.due_tick == 49 && !f.b.flags && !f.c.flags);
        f.fire(); assert(f.b.flags == MEMTYPE_FULL && !f.c.flags && !f.a.flags);
        f.prioritize("bless"); assert(dirty == 2 && interval == 20);
        f.order({&f.head,&f.b,&f.a,&f.c,&f.ready,&f.other,&f.tail});
        Fixture same; same.a.modifier = SPELL_FULL_HEAL; same.b.modifier = SPELL_BLESS;
        same.arm(second_half); same.prioritize("full heal");
        same.order({&same.head,&same.a,&same.ready,&same.c,&same.b,&same.other,&same.tail});
        assert(dirty == 1 && submissions == 1 && event.due_tick == 10 && (interval == 0) == second_half);
    }
    Fixture f; f.arm(false);
    for (auto [bad, expected] : {std::pair{" ", "Usage:"}, {"nonexistent", "Which spell"},
                                 {"armor", "no pending copy"}, {"improved invisibility", "no pending copy"}}) {
        f.prioritize(bad); assert(output.find(expected) != std::string::npos); assert(dirty == 0 && submissions == 1 && !f.desc.gmcp_spell_preparation_pending);
    }
    f.b.flags = f.c.flags = MEMTYPE_FULL; f.prioritize("full heal");
    assert(output.find("no pending copy") != std::string::npos); f.b.flags = f.c.flags = 0;
    max_circle = 1; f.prioritize("full heal"); assert(dirty == 0); max_circle = 2;
    f.ch.player.m_class = CLASS_SORCERER; missing_book = SPELL_FULL_HEAL;
    f.prioritize("full heal"); assert(output.find("spellbooks") != std::string::npos && dirty == 0);
    for (auto cls : {CLASS_DRUID, CLASS_WARLOCK, CLASS_PSIONICIST, CLASS_WARRIOR}) {
        f.ch.player.m_class = cls; f.prioritize("full heal"); assert(output.find("by name") != std::string::npos);
    }
    f.ch.specials.act |= ACT_ISNPC; f.prioritize("full heal"); assert(output.empty());
    f.order({&f.head,&f.a,&f.ready,&f.b,&f.other,&f.c,&f.tail});
    assert(!dirty && submissions == 1 && event.due_tick == 10 && IS_AFFECTED(&f.ch,AFF_MEDITATE));
    for (auto cls : {CLASS_SHAMAN, CLASS_WARRIOR, CLASS_SORCERER, CLASS_CONJURER}) {
        Fixture idle; idle.ch.player.m_class = cls;
        if (cls == CLASS_WARRIOR) idle.ch.player.secondary_class = CLASS_CLERIC;
        missing_book = SPELL_FULL_HEAL; rudiments = cls == CLASS_CONJURER; chaos = cls == CLASS_SORCERER;
        idle.prioritize("full heal"); assert(dirty == 1 && !submissions && !idle.ch.nevents);
    }
    // Bless has no book, so preparation skips it: full heal is already in progress and keeps
    // its deadline when it moves to the front.
    Fixture skipped; skipped.ch.player.m_class = CLASS_SORCERER; missing_book = SPELL_BLESS;
    skipped.arm(false); skipped.prioritize("full heal");
    skipped.order({&skipped.head,&skipped.b,&skipped.c,&skipped.a,&skipped.ready,&skipped.other,&skipped.tail});
    assert(dirty == 1 && submissions == 1 && event.due_tick == 10 && skipped.desc.gmcp_spell_preparation_pending);
    assert(output.find("Switching") == std::string::npos);
    Fixture fail; fail.ch.player.m_class = CLASS_SORCERER;
    fail.arm(true); reject = true; fail.prioritize("full heal");
    assert(dirty == 1 && !fail.ch.nevents && !IS_AFFECTED2(&fail.ch,AFF2_MEMORIZING));
    assert(!IS_AFFECTED(&fail.ch,AFF_MEDITATE) && output.find("try again") != std::string::npos);
    fail.order({&fail.head,&fail.b,&fail.c,&fail.a,&fail.ready,&fail.other,&fail.tail});
    reject = false; fail.arm(false); fail.fire(); fail.fire(); assert(fail.b.flags == MEMTYPE_FULL);
}
'''
helpers = "\n".join(extract_function(file, signature) for file, signature in (
    ("wikihelp.c", "string trim(string const &str,"),
    ("interp.c", "int old_search_block(const char *argument"),
    ("sparser.c", "int lookup_spell(const char *name,"),
))
build = ROOT / "bin/tests"
build.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="prioritize-", dir=build) as tmp:
    cpp, binary = Path(tmp) / "test.cpp", Path(tmp) / "test"
    cpp.write_text(prelude + helpers + production + driver)
    subprocess.run(["g++", "-std=c++20", "-g", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all", "-Isrc",
                    str(cpp), str(HARNESS_STUBS), "-o", str(binary)], cwd=ROOT, check=True)
    subprocess.run([binary], check=True)
print("PASS prioritize queue identity, eligibility, timing, scheduler rejection and retry")
