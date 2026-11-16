#!/usr/bin/env python3
"""Every race fraglist filters on the race name the leaderboard stores (#1062 N3a).

sql_update_frag_leaderboard() stores race_names_table[].normal ("Drow Elf"), but
do_fraglist() filtered on spellings such as 'drow_elf', so the lists for Drow Elf,
Grey Elf, Mountain Dwarf, Duergar, Storm Giant, Planetbound Illithid, Wood Elf and
Kuo Toa were always empty.

Compiles the production do_fraglist() with the production race table and checks the
filter each race argument builds against the name that race stores.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

from _paths import HARNESS_STUBS, ROOT, extract_function, source

HARNESS = r'''
// INCLUDES
#include <cassert>
#include <cstdio>
#include <strings.h>

// RACE_TABLE
static std::string shown_filter;
static void show_fraglist(P_char, const std::string &filter) { shown_filter = filter; }
std::string frag_cap_runtime_status(int, int64_t) { return ""; }
bool combat_outcome_transaction_credit_pending(int) { return false; }
char *redis_get_fraglist() { return nullptr; }
bool redis_cache_fraglist(P_char) { return false; }
void update_shipfrags() {}
void display_shipfrags(P_char) {}
void show_guild_frags(P_char) {}

// FUNCTIONS

int main()
{
	char_data viewer{};
	pc_only_data pc{};
	viewer.only.pc = &pc;
	viewer.specials.position = POS_STANDING + STAT_NORMAL;
	const struct
	{
		const char *argument;
		int race;
	} cases[] = {
		{ "drow elf", RACE_DROW },	   { "grey elf", RACE_GREY },
		{ "mountain dwarf", RACE_MOUNTAIN }, { "duergar", RACE_DUERGAR },
		{ "storm giant", RACE_SGIANT },	   { "pillithid", RACE_PILLITHID },
		{ "wood elf", RACE_WOODELF },	   { "kuo toa", RACE_KUOTOA },
		{ "human", RACE_HUMAN },	   { "half-elf", RACE_HALFELF },
		{ "thri-kreen", RACE_THRIKREEN },  { "tiefling", RACE_TIEFLING },
	};
	for (const auto &test : cases)
	{
		char argument[64];
		snprintf(argument, sizeof argument, "%s", test.argument);
		shown_filter.clear();
		do_fraglist(&viewer, argument, 0);
		const std::string stored =
			std::string("race = '") + race_names_table[test.race].normal + "'";
		if (strcasecmp(shown_filter.c_str(), stored.c_str()))
		{
			std::fprintf(stderr, "fraglist %s filters on %s, but the race is stored as %s\n",
				     test.argument, shown_filter.c_str(), stored.c_str());
			return 1;
		}
	}
	std::puts("every race fraglist filters on the stored race name");
}
'''

fraglist = "combat/fraglist.c"
includes = "\n".join(line for line in source(fraglist).read_text().splitlines()
                     if line.startswith("#include"))
table = re.search(r"const struct race_names race_names_table\[LAST_RACE \+ 2\] = \{.*?\n\};",
                  source("core/common.c").read_text(), re.S)[0]
(ROOT / "bin/tests").mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="fraglist-race-", dir=ROOT / "bin/tests") as tmp:
    harness = Path(tmp) / "fraglist.cpp"
    harness.write_text(HARNESS.replace("// INCLUDES", includes).replace("// RACE_TABLE", table)
                       .replace("// FUNCTIONS", extract_function(fraglist, "void do_fraglist(")))
    binary = harness.with_suffix("")
    subprocess.run(["g++", "-std=c++20", "-g", "-O1", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=undefined", "-fno-omit-frame-pointer",
                    "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
                    "-Isrc", "-I/usr/include/mysql", "-I/usr/include/libxml2", str(harness),
                    str(HARNESS_STUBS), "-o", str(binary)], cwd=ROOT, check=True)
    subprocess.run([str(binary)], check=True, env=dict(os.environ,
        ASAN_OPTIONS="detect_leaks=1:halt_on_error=1", UBSAN_OPTIONS="halt_on_error=1"))
