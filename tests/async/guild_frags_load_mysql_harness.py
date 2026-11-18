#!/usr/bin/env python3
"""A guild's frag total and top fragger are recounted from its members when it loads.

The total is the members' frags, which leaving subtracts again. A PvP outcome commits
apart from the guild's own save, so a crash between them could leave the saved total
apart from its members (#1062 N13). sql_load_guild() now recounts it from the saved
players.

Runs the production sql_load_guild() against the full disposable schema: a stale saved
total is replaced by the members' frags, a member saved before rosters kept pids is
matched by name, a non-member or a listed enemy is not counted, and a guild with no
members has no top fragger.
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from _paths import ROOT, extract_function

HARNESS = r'''
#include "core/prototypes.h"
#include "core/utils.h"
#include "guild/assocs.h"
#include "guild/artifact_guild_delivery_ids.h"
#include "sql/sql.h"
#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>

MYSQL *DB = nullptr;
Guild::Guild()
{
	members = nullptr;
	member_count = 0;
	frags = {};
}
Guild::~Guild()
{
	while (members)
	{
		P_member next = members->next;
		delete members;
		members = next;
	}
}
MYSQL_RES *db_query_at(persistence_query_site, const char *format, ...)
{
	char statement[2048];
	va_list arguments;
	va_start(arguments, format);
	std::vsnprintf(statement, sizeof statement, format, arguments);
	va_end(arguments);
	if (mysql_query(DB, statement))
	{
		std::cerr << "query failed: " << mysql_error(DB) << '\n';
		return nullptr;
	}
	return mysql_store_result(DB);
}
void logit(const char *, const char *, ...) {}
void fatal_boot_error(const char *, const char *, ...) { std::abort(); }

// SQL_LOAD_GUILD

static void execute(const char *statement)
{
	if (mysql_query(DB, statement))
	{
		std::cerr << "fixture query failed: " << mysql_error(DB) << '\n';
		std::abort();
	}
}

static const char *required_env(const char *name)
{
	const char *value = std::getenv(name);
	assert(value && *value);
	return value;
}

int main()
{
	DB = mysql_init(nullptr);
	const char *port = std::getenv("DB_PORT");
	assert(mysql_real_connect(DB, required_env("DB_HOST"), required_env("DB_USER"),
				  required_env("DB_PASSWD"), required_env("DB_NAME"),
				  port ? std::strtoul(port, nullptr, 10) : 3306, nullptr, 0));
	execute("INSERT INTO player_data (pid, name, frags) VALUES "
		"(1, 'Alpha', 500), (2, 'Beta', -200), (3, 'Gamma', 50), (4, 'Delta', 100), "
		"(5, 'Foe', 900)");
	execute("INSERT INTO guilds (id, name, frags, top_frags, topfragger) VALUES "
		"(7, 'Stale', 9999, 9999, 'Ghost'), (8, 'Empty', 12, 12, 'Ghost')");
	// The roster lists members and the guild's enemies; only members count.
	char roster[512];
	const unsigned int member = A_SF2 | A_NORMAL, enemy = A_ENEMY;
	std::snprintf(roster, sizeof roster,
		      "INSERT INTO guild_members (guild_id, player_name, player_pid, bits) VALUES "
		      "(7, 'Alpha', 1, %u), (7, 'Beta', 2, %u), (7, 'Delta', NULL, %u), "
		      "(7, 'Foe', 5, %u), (8, 'Foe', 5, %u)",
		      member, member, member, enemy, enemy);
	execute(roster);

	Guild *stale = sql_load_guild(7);
	assert(stale && stale->get_num_members() == 4);
	assert(stale->get_frags() == 400 && stale->get_top_frags() == 500 &&
	       !std::strcmp(stale->get_top_fragger(), "Alpha"));
	Guild *empty = sql_load_guild(8);
	assert(empty && empty->get_frags() == 0 && empty->get_top_frags() == 0 &&
	       !*empty->get_top_fragger());
	delete stale;
	delete empty;
	mysql_close(DB);
	std::cout << "guild frag totals are recounted from their members on load\n";
}
'''

build_root = ROOT / "bin/tests"
build_root.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="guild-frags-load-", dir=build_root) as directory:
    source = Path(directory) / "guild_frags_load.cpp"
    binary = source.with_suffix("")
    source.write_text(HARNESS.replace(
        "// SQL_LOAD_GUILD", extract_function("sql_player.c", "Guild *sql_load_guild(unsigned int guild_id)")))
    cflags = shlex.split(subprocess.check_output(["mysql_config", "--cflags"], text=True))
    libs = shlex.split(subprocess.check_output(["mysql_config", "--libs"], text=True))
    subprocess.run(["g++", "-std=c++20", "-g", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=undefined", "-Wall", "-Wextra", "-Werror",
                    "-Isrc", *cflags, str(source), *libs, "-o", str(binary)],
                   cwd=ROOT, check=True)
    subprocess.run([str(binary)], check=True, env=os.environ.copy())
