#!/usr/bin/env python3
"""afire runs room/mob/object specials against the enemy it fires at, not the named tank.

A non-killable shopkeeper refuses "fire <keeper>" through its special. afire must hit the
same refusal when the keeper is the tank's opponent, and must not be refused just because
the tank it names is protected.
"""
from pathlib import Path
import subprocess
import tempfile

from _paths import ROOT, extract_function

AFIRE = extract_function("range.c", "void do_afire(P_char ch, char *argument, int /*cmd*/)\n{")

HARNESS = f"""
#include <cassert>
#include <cstring>
#include <string>
#include "core/prototypes.h"
#include "core/utils.h"
#include "cmd/interp.h"
#include "net/comm.h"
#include "world/handler.h"

int no_specials = 0;
P_char room_char = nullptr;     // what get_char_room_vis finds
bool refuse = false;            // the special's verdict
int special_calls = 0, special_cmd = 0, fired = 0;
std::string special_arg, fired_arg;

char *one_argument(const char *argument, char *first) {{ strcpy(first, argument); return first; }}
P_char get_char_room_vis(P_char, const char *) {{ return room_char; }}
bool get_char_room_target(P_char, P_char, char *out, size_t) {{ strcpy(out, "2.keeper"); return true; }}
bool special(P_char, int cmd, char *arg)
{{
    ++special_calls; special_cmd = cmd; special_arg = arg;
    return refuse;
}}
void do_fire(P_char, char *argument, int) {{ ++fired; fired_arg = argument; }}
void act(const char *, int, P_char, P_obj, void *, int) {{}}
void send_to_char(const char *, P_char) {{}}

{AFIRE}

int main()
{{
    char_data archer{{}}, tank{{}}, keeper{{}};
    room_char = &tank;
    tank.specials.fighting = &keeper;
    char name[] = "tank";

    // Specials see the enemy as "fire" would, and a refusal stops the shot.
    refuse = true;
    do_afire(&archer, name, CMD_AFIRE);
    assert(special_calls == 1 && special_cmd == CMD_FIRE && special_arg == "2.keeper");
    assert(fired == 0);

    // Allowed: one special pass, then the shot at the same enemy.
    refuse = false;
    special_calls = 0;
    do_afire(&archer, name, CMD_AFIRE);
    assert(special_calls == 1 && fired == 1 && fired_arg == "2.keeper");

    // No opponent: nothing is judged or fired.
    tank.specials.fighting = nullptr;
    special_calls = fired = 0;
    do_afire(&archer, name, CMD_AFIRE);
    assert(special_calls == 0 && fired == 0);

    // Specials disabled at boot stay disabled.
    tank.specials.fighting = &keeper;
    no_specials = 1;
    do_afire(&archer, name, CMD_AFIRE);
    assert(special_calls == 0 && fired == 1);
    return 0;
}}
"""

directory = ROOT / "bin/tests"
directory.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="afire-specials-", dir=directory) as temporary:
    root = Path(temporary)
    harness = root / "afire_specials.cpp"
    binary = root / "afire_specials"
    harness.write_text(HARNESS, encoding="utf-8")
    subprocess.run(
        ["g++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-Og", "-g",
         "-fsanitize=address,undefined", "-Isrc", str(harness), "-o", str(binary)],
        check=True, cwd=ROOT, timeout=180,
    )
    subprocess.run([str(binary)], check=True, timeout=30)

print("afire specials regression passed")
