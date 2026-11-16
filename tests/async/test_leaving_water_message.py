#!/usr/bin/env python3
"""Coming up for air says so, once and only then (#1062 N7).

Leaving the water cleared the holding-breath and drowning flags without a word:
char_to_room() cleared holding breath on entering a dry room, and the breath event
cleared whatever was left. Both now call breathe_air(). Compiles the production
breathe_air() and event_underwatersector() and checks that a character who was holding
their breath or drowning is told once when they reach air, whether room entry or the
event gets there first, and that no one else is: a dry character, or one who gained
water breathing below.
"""

import os
import subprocess
import tempfile
from pathlib import Path

from _paths import HARNESS_STUBS, ROOT, extract_function, source

HARNESS = r'''
// INCLUDES
#include <cassert>
#include <cstdlib>
#include <cstdio>
#include <string>

P_room world;
static std::string told;
static int events;
// Neither the drowning damage nor a death is reached by these cases.
void StartRegen(P_char, regen_resource) { std::abort(); }
void die(P_char, P_char) { std::abort(); }
void send_to_char(const char *text, P_char) { told += text; }
nevent_schedule_result add_event(event_func, int, P_char, P_char, P_obj, int, const void *, int)
{
	++events;
	return {};
}

// FUNCTIONS

static char_data diver{};
static pc_only_data diver_pc{};

static void dive(int room, unsigned long breath, unsigned long affects = 0)
{
	diver = {};
	diver.only.pc = &diver_pc;
	diver.in_room = room;
	diver.specials.affected_by = affects;
	diver.specials.affected_by2 = breath;
	told.clear();
}

static bool breath_event_told()
{
	event_underwatersector(&diver, nullptr, nullptr, nullptr);
	assert(!(diver.specials.affected_by2 & (AFF2_HOLDING_BREATH | AFF2_IS_DROWNING)));
	return told.find("fresh air") != std::string::npos;
}

int main()
{
	world = new room_data[2]{};
	world[0].sector_type = SECT_UNDERWATER;
	world[1].sector_type = SECT_FIELD;
	for (unsigned long breath : { AFF2_HOLDING_BREATH, AFF2_IS_DROWNING })
	{
		dive(1, breath); // char_to_room() reaches a dry room first
		breathe_air(&diver);
		assert(told.find("fresh air") != std::string::npos);
		told.clear();
		assert(!breath_event_told()); // and the event that follows says nothing more
		dive(1, breath); // otherwise the event announces it
		assert(breath_event_told());
	}
	dive(1, 0); // never under
	breathe_air(&diver);
	assert(!breath_event_told());
	dive(0, AFF2_HOLDING_BREATH, AFF_WATERBREATH); // still under
	assert(!breath_event_told());
	assert(events == 0);
	delete[] world;
	std::puts("reaching air is announced once, and only for a real transition");
}
'''

specials = "mob/specials.c"
includes = "\n".join(line for line in source(specials).read_text().splitlines()
                     if line.startswith("#include"))
(ROOT / "bin/tests").mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="leave-water-", dir=ROOT / "bin/tests") as tmp:
    harness = Path(tmp) / "water.cpp"
    harness.write_text(HARNESS.replace("// INCLUDES", includes).replace(
        "// FUNCTIONS", extract_function(specials, "void breathe_air(") + "\n" +
        extract_function(specials, "void event_underwatersector(")))
    binary = harness.with_suffix("")
    subprocess.run(["g++", "-std=c++20", "-g", "-O1", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=undefined", "-fno-omit-frame-pointer",
                    "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
                    "-Isrc", "-I/usr/include/mysql", "-I/usr/include/libxml2", str(harness),
                    str(HARNESS_STUBS), "-o", str(binary)], cwd=ROOT, check=True)
    subprocess.run([str(binary)], check=True, env=dict(os.environ,
        ASAN_OPTIONS="detect_leaks=1:halt_on_error=1", UBSAN_OPTIONS="halt_on_error=1"))
