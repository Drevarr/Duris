#!/usr/bin/env python3
"""A Bard can dismiss a named pet, and naming another follower answers (#1062 N12).

do_dismiss() returned from its Bard branch before reading the argument, so a Bard
could never dismiss a single pet, only mirror images. Naming a creature that is
not your pet printed nothing at all.

Compiles the production do_dismiss() and checks a Bard and a non-Bard dismissing
their pet by name, a bare Bard dismiss, and a named follower that is not a pet.
"""

import os
import subprocess
import tempfile
from pathlib import Path

from _paths import HARNESS_STUBS, ROOT, extract_function, source

HARNESS = r'''
// INCLUDES
#include <cassert>
#include <cstdio>
#include <string>

P_index mob_index = nullptr; // no followers, so no vnum is read
static char_data owner{}, pet{}, stray{};
static P_char named = nullptr;
static std::vector<P_char> extracted;
static std::string told;
int GET_CLASS(P_char ch, uint cls) { return (ch->player.m_class & cls) != 0; }
P_char parse_victim(P_char, char *, unsigned int) { return named; }
P_char get_linked_char(P_char ch, ush_int) { return ch == &pet ? &owner : nullptr; }
void extract_char(P_char ch) { extracted.push_back(ch); }
void act(const char *text, int, P_char, P_obj, void *, int type)
{
	if (type == TO_CHAR)
		told += text;
}
void send_to_char(const char *text, P_char) { told += text; }

// FUNCTIONS

static void dismiss(const char *argument, P_char target)
{
	char buffer[32];
	snprintf(buffer, sizeof buffer, "%s", argument);
	named = target;
	extracted.clear();
	told.clear();
	do_dismiss(&owner, buffer, 0);
}

int main()
{
	pc_only_data pc{};
	npc_only_data pet_npc{}, stray_npc{};
	owner.only.pc = &pc;
	pet.only.npc = &pet_npc;
	stray.only.npc = &stray_npc;
	pet.specials.act = stray.specials.act = ACT_ISNPC;
	for (P_char ch : { &owner, &pet, &stray })
	{
		ch->in_room = 1;
		ch->specials.position = POS_STANDING + STAT_NORMAL;
	}

	owner.player.m_class = CLASS_BARD;
	dismiss("pet", &pet);
	assert(extracted.size() == 1 && extracted[0] == &pet);
	dismiss("", nullptr); // no mirror images among no followers
	assert(extracted.empty() && told.find("Just stop singing") != std::string::npos);

	owner.player.m_class = CLASS_CONJURER;
	dismiss("pet", &pet);
	assert(extracted.size() == 1 && extracted[0] == &pet);
	dismiss("stray", &stray);
	assert(extracted.empty() && told.find("is not your pet") != std::string::npos);
	std::puts("a Bard dismisses a named pet, and a stray is told apart");
}
'''

drannak = "classes/drannak.c"
includes = "\n".join(line for line in source(drannak).read_text().splitlines()
                     if line.startswith("#include"))
(ROOT / "bin/tests").mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="dismiss-", dir=ROOT / "bin/tests") as tmp:
    harness = Path(tmp) / "dismiss.cpp"
    harness.write_text(HARNESS.replace("// INCLUDES", includes).replace(
        "// FUNCTIONS", extract_function(drannak, "void do_dismiss(P_char ch, char *argument, int cmd)")))
    binary = harness.with_suffix("")
    subprocess.run(["g++", "-std=c++20", "-g", "-O1", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=undefined", "-fno-omit-frame-pointer",
                    "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
                    "-Isrc", "-I/usr/include/mysql", "-I/usr/include/libxml2", str(harness),
                    str(HARNESS_STUBS), "-o", str(binary)], cwd=ROOT, check=True)
    subprocess.run([str(binary)], check=True, env=dict(os.environ,
        ASAN_OPTIONS="detect_leaks=1:halt_on_error=1", UBSAN_OPTIONS="halt_on_error=1"))
