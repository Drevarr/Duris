#!/usr/bin/env python3
"""Issue 1041 regression: NPC thief procs are flavor emotes with no in-game consequences."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from _paths import extract_function


HARNESS_HEAD = r"""
#include <cassert>
#include <cstring>
#include <string>
#include <vector>

#define FALSE 0
#define TRUE 1
#define NOWHERE -1
#define TO_ROOM 0
#define TO_VICT 1
#define TO_NOTVICT 2
#define TO_CHAR 3

#define ACT_TEACHER (1 << 0)
#define ACT_SPEC_TEACHER (1 << 1)
#define ACT_ISNPC (1 << 2)
#define ROOM_SAFE (1 << 0)
#define ROOM_SINGLE_FILE (1 << 1)

#define STAT_SLEEPING 4
#define STAT_NORMAL 0
#define WEAR_FEET 8
#define MAX_WEAR 24

struct obj_data {
    int id;
    obj_data *next_content;
};
using P_obj = obj_data *;

struct specials_data {
    unsigned int act;
    int fighting;
    int stat;
};

struct money_data {
    int platinum;
    int gold;
    int silver;
    int copper;
};

struct char_data {
    int in_room;
    int level;
    bool npc;
    bool alive;
    bool trusted;
    bool pet;
    specials_data specials;
    money_data points;
    P_obj equipment[MAX_WEAR];
    P_obj carrying;
};
using P_char = char_data *;

struct room_data {
    unsigned int room_flags;
};
static room_data world[4]{};

static bool IS_ALIVE(P_char c) { return c && c->alive; }
static bool IS_NPC(P_char c) { return c && c->npc; }
static bool IS_PC_PET(P_char c) { return c && c->pet; }
static bool IS_TRUSTED(P_char c) { return c && c->trusted; }
static bool IS_SET(unsigned int f, unsigned int b) { return (f & b) != 0; }
static bool IS_ROOM(int r, unsigned int f) {
    assert(r >= 0 && r < 4);
    return (world[r].room_flags & f) != 0;
}
static bool CHAR_IN_SAFE_ROOM(P_char c) { return IS_ROOM(c->in_room, ROOM_SAFE); }
static bool IS_FIGHTING(P_char c) { return c && c->specials.fighting != 0; }

static bool adjacent_in_room = true;
static bool AdjacentInRoom(P_char, P_char) { return adjacent_in_room; }

static int forced_roll = 0;
static int number(int from, int to) {
    if (from == 0 && to == 1) return forced_roll;
    return from;
}

struct ActCall {
    std::string msg;
    int hide_invisible;
    P_char ch;
    P_obj obj;
    void *vict;
    int type;
};
static std::vector<ActCall> act_calls;

static void act(const char *str, int hide_invis, P_char ch, P_obj obj, void *vict_obj, int type) {
    act_calls.push_back({str ? str : "", hide_invis, ch, obj, vict_obj, type});
}

// Poison symbols that must never be reached or called by npc_steal.
[[maybe_unused]] static P_obj unequip_char(P_char, int) { assert(false && "unequip_char must not be called"); return nullptr; }
[[maybe_unused]] static void obj_from_char(P_obj) { assert(false && "obj_from_char must not be called"); }
[[maybe_unused]] static int obj_to_char(P_obj, P_char) { assert(false && "obj_to_char must not be called"); return 0; }
[[maybe_unused]] static int SUB_MONEY(P_char, int, int) { assert(false && "SUB_MONEY must not be called"); return 1; }
[[maybe_unused]] static void ADD_MONEY(P_char, int) { assert(false && "ADD_MONEY must not be called"); }
[[maybe_unused]] static void do_wake(P_char, char *, int) { assert(false && "do_wake must not be called"); }
[[maybe_unused]] static void CharWait(P_char, int) { assert(false && "CharWait must not be called"); }
"""

HARNESS_TAIL = r"""
static char_data make_char(bool npc, int level, int room) {
    char_data c{};
    c.in_room = room;
    c.level = level;
    c.npc = npc;
    c.alive = true;
    c.specials.stat = STAT_NORMAL;
    return c;
}

int main() {
    world[1].room_flags = 0;
    world[2].room_flags = ROOM_SAFE;
    world[3].room_flags = ROOM_SINGLE_FILE;

    obj_data boots{38418, nullptr};
    obj_data carried{1234, nullptr};

    // 1. Level-37 thief vs level-33 awake victim wearing boots and carrying gear/coins.
    for (int roll : {0, 1}) {
        act_calls.clear();
        forced_roll = roll;
        char_data thief = make_char(true, 37, 1);
        char_data vict = make_char(false, 33, 1);
        vict.equipment[WEAR_FEET] = &boots;
        vict.carrying = &carried;
        vict.points = {10, 20, 30, 40};

        npc_steal(&thief, &vict);

        assert(act_calls.size() == 2);
        assert(act_calls[0].type == TO_VICT && act_calls[0].vict == &vict);
        assert(act_calls[1].type == TO_NOTVICT && act_calls[1].vict == &vict);
        assert(vict.equipment[WEAR_FEET] == &boots);
        assert(vict.carrying == &carried);
        assert(vict.points.platinum == 10 && vict.points.gold == 20 &&
               vict.points.silver == 30 && vict.points.copper == 40);
        assert(thief.carrying == nullptr);
        assert(thief.points.platinum == 0 && thief.points.gold == 0 &&
               thief.points.silver == 0 && thief.points.copper == 0);
    }

    // 2. Sleeping victim stays asleep and keeps all gear/coins.
    {
        act_calls.clear();
        forced_roll = 0;
        char_data thief = make_char(true, 37, 1);
        char_data vict = make_char(false, 33, 1);
        vict.specials.stat = STAT_SLEEPING;
        vict.equipment[WEAR_FEET] = &boots;

        npc_steal(&thief, &vict);

        assert(vict.specials.stat == STAT_SLEEPING);
        assert(vict.equipment[WEAR_FEET] == &boots);
    }

    // 3. Guards (safe room, NOWHERE/mismatched room, trusted, fighting, teacher, single-file).
    {
        char_data thief = make_char(true, 37, 2);
        char_data vict = make_char(false, 33, 2);
        act_calls.clear();
        npc_steal(&thief, &vict);
        assert(act_calls.empty());

        thief.in_room = NOWHERE;
        vict.in_room = 1;
        npc_steal(&thief, &vict);
        assert(act_calls.empty());

        thief.in_room = 1;
        vict.in_room = 2;
        npc_steal(&thief, &vict);
        assert(act_calls.empty());

        vict.in_room = 1;
        vict.trusted = true;
        npc_steal(&thief, &vict);
        assert(act_calls.empty());

        vict.trusted = false;
        vict.specials.fighting = 1;
        npc_steal(&thief, &vict);
        assert(act_calls.empty());

        vict.specials.fighting = 0;
        thief.specials.act = ACT_TEACHER;
        npc_steal(&thief, &vict);
        assert(act_calls.empty());

        thief.specials.act = 0;
        thief.in_room = 3;
        vict.in_room = 3;
        adjacent_in_room = false;
        npc_steal(&thief, &vict);
        assert(act_calls.empty());
    }

    return 0;
}
"""


class NpcStealBypassTests(unittest.TestCase):
    def test_npc_steal_runtime_emits_flavor_emotes_only(self):
        fn = extract_function("specials.c", "void npc_steal(")
        cpp = HARNESS_HEAD + "\n" + fn + "\n" + HARNESS_TAIL
        with tempfile.TemporaryDirectory() as tmp:
            src_path = Path(tmp) / "test_npc_steal.cpp"
            bin_path = Path(tmp) / "test_npc_steal"
            src_path.write_text(cpp)
            subprocess.run(
                [
                    "g++",
                    "-std=c++20",
                    "-UNDEBUG",
                    "-Wall",
                    "-Wextra",
                    "-Wpedantic",
                    "-Werror",
                    str(src_path),
                    "-o",
                    str(bin_path),
                ],
                check=True,
            )
            subprocess.run([str(bin_path)], check=True)


if __name__ == "__main__":
    unittest.main()
