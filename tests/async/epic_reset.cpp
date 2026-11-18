// Actual staff epic reset handler (#1089) under ASan/UBSan with bounds checks fatal.
// The loop must stay inside the 2000-entry player skill array, clear only refundable
// epic skills, keep ordinary and forge/mine/craft skills, refresh derived stats and
// tell the target and the staff member. A fatal refresh frees the target, and a
// target without a connection gets its notice at next login.
#include "core/prototypes.h"
#include "core/utils.h"
#include "magic/spells.h"
#include "classes/epic_skills.h"
#include "world/epic.h"
#include "net/gmcp.h"
#include "sql/sql.h"
#include <cassert>
#include <sanitizer/asan_interface.h>
#include <cstdarg>
#include <cstdio>
#include <string>

Skill skills[MAX_AFFECT_TYPES + 1] = {};
epic_reward epic_rewards[] = {
	{ EPIC_REWARD_SKILL, SKILL_TOUGHNESS, 0, 100, 1000000, 0 },
	{ EPIC_REWARD_SKILL, SKILL_ANATOMY, 0, 25, 250000, 0 },
	{ EPIC_REWARD_SKILL, SKILL_MINE, 0, 10, 10000, 0 },
	{ 0, 0, 0, 0, 0, 0 },
};
static char_data staff = {}, pupil = {};
static pc_only_data staff_pc = {}, pupil_pc = {};
static std::string feedback;
static int saves = 0, refreshes = 0, vitals = 0;
static P_char dying = nullptr;
static bool pupil_linked = true;

int get_property(const char *, int fallback)
{
	return fallback;
}
void argument_interpreter(char *arg, char *first, char *second)
{
	*first = *second = '\0';
	std::sscanf(arg, "%s %s", first, second);
}
P_char get_char_vis(P_char, const char *name)
{
	return std::string(name) == "Pupil" ? &pupil : nullptr;
}
void send_to_char(const char *text, P_char ch)
{
	feedback += std::string(ch == &staff ? "staff:" : "pupil:") + text;
}
bool send_to_pid(const char *text, int pid)
{
	if (pid == 2 && !pupil_linked)
		return false;
	send_to_char(text, pid == 1 ? &staff : &pupil);
	return true;
}
void send_to_pid_offline(const char *text, int pid)
{
	feedback += "offline " + std::to_string(pid) + ":" + text;
}
void send_to_char_f(P_char ch, const char *format, ...)
{
	char text[256];
	va_list args;
	va_start(args, format);
	vsnprintf(text, sizeof(text), format, args);
	va_end(args);
	send_to_char(text, ch);
}
char affect_total(P_char ch, int kill_ch)
{
	assert((ch == &pupil || ch == &staff) && kill_ch);
	++refreshes;
	if (ch != dying)
		return false;
	// die() saves and frees the character, so any later access is a use after free.
	ASAN_POISON_MEMORY_REGION(ch, sizeof(*ch));
	return true;
}
void update_group_vitals(P_char)
{
	++vitals;
}
void gmcp_char_vitals(P_char)
{
	++vitals;
}
bool do_save_silent(P_char ch, int, player_save_pipeline_result *)
{
	assert(ch == &pupil || ch == &staff);
	++saves;
	return true;
}

// PRODUCTION

static void reset_fixture(int staff_level)
{
	for (auto [ch, pc, name, pid] : { std::tuple{ &staff, &staff_pc, "Staff", 1 },
					  std::tuple{ &pupil, &pupil_pc, "Pupil", 2 } })
	{
		*pc = {};
		*ch = {};
		ch->only.pc = pc;
		ch->player.name = const_cast<char *>(name);
		ch->player.level = 30;
		pc->pid = pid;
	}
	staff.player.level = staff_level;
	feedback.clear();
	saves = refreshes = vitals = 0;
	pupil_linked = true;
}

static void learn(pc_only_data &pc, int skill, int learned)
{
	pc.skills[skill].learned = pc.skills[skill].taught = learned;
}

static void reset(const char *arg)
{
	char text[64];
	std::snprintf(text, sizeof(text), "%s", arg);
	do_epic_reset(&staff, text, 0);
}

int main()
{
	skills[SKILL_BASH].name = const_cast<char *>("bash");
	for (auto [skill, name] :
	     { std::pair{ SKILL_TOUGHNESS, "toughness" }, std::pair{ SKILL_ANATOMY, "anatomy" },
	       std::pair{ SKILL_MINE, "mine" }, std::pair{ SKILL_CRAFT, "craft" },
	       std::pair{ SKILL_FORGE, "forge" }, std::pair{ SKILL_LISTEN, "listen" } })
	{
		skills[skill].name = const_cast<char *>(name);
		skills[skill].targets = TAR_EPIC;
	}

	// Self target with no epic skills: the whole array is scanned and nothing changes.
	reset_fixture(MAXLVLMORTAL + 1);
	reset("reset");
	assert(saves == 1 && refreshes == 1);
	assert(feedback == "staff:&+GYour epic skills have been reset.&n\r\n");
	for (const auto &skill : staff_pc.skills)
	{
		assert(!skill.learned && !skill.taught);
	}

	// Self target with populated skills: refundable epic skills clear; ordinary,
	// forge/mine/craft and epic skills without a reward row stay.
	reset_fixture(MAXLVLMORTAL + 1);
	for (int skill : { SKILL_TOUGHNESS, SKILL_ANATOMY, SKILL_BASH, SKILL_MINE, SKILL_CRAFT,
			   SKILL_FORGE, SKILL_LISTEN })
		learn(staff_pc, skill, 40);
	learn(staff_pc, MAX_SKILLS - 1, 7);
	reset("reset");
	assert(saves == 1);
	for (int skill : { SKILL_TOUGHNESS, SKILL_ANATOMY })
	{
		assert(!staff_pc.skills[skill].learned && !staff_pc.skills[skill].taught);
	}
	for (int skill : { SKILL_BASH, SKILL_MINE, SKILL_CRAFT, SKILL_FORGE, SKILL_LISTEN })
	{
		assert(staff_pc.skills[skill].learned == 40 && staff_pc.skills[skill].taught == 40);
	}
	assert(staff_pc.skills[MAX_SKILLS - 1].learned == 7);

	// Named target: only that player's epic skills clear.
	reset_fixture(MAXLVLMORTAL + 1);
	learn(staff_pc, SKILL_TOUGHNESS, 30);
	learn(pupil_pc, SKILL_TOUGHNESS, 50);
	learn(pupil_pc, SKILL_BASH, 60);
	reset("reset Pupil");
	assert(saves == 1 && refreshes == 1 && vitals == 2);
	assert(feedback == "pupil:&+GYour epic skills have been reset.&n\r\n"
			   "staff:You reset Pupil's epic skills.\r\n");
	assert(!pupil_pc.skills[SKILL_TOUGHNESS].learned &&
	       !pupil_pc.skills[SKILL_TOUGHNESS].taught);
	assert(pupil_pc.skills[SKILL_BASH].learned == 60);
	assert(staff_pc.skills[SKILL_TOUGHNESS].learned == 30);

	// A link-dead target still in the game is told at next login.
	reset_fixture(MAXLVLMORTAL + 1);
	learn(pupil_pc, SKILL_TOUGHNESS, 50);
	pupil_linked = false;
	reset("reset Pupil");
	assert(saves == 1 && refreshes == 1);
	assert(feedback == "offline 2:&+GYour epic skills have been reset.&n\r\n"
			   "staff:You reset Pupil's epic skills.\r\n");
	assert(!pupil_pc.skills[SKILL_TOUGHNESS].learned);

	// Losing the skill's hit points kills the target: both notices go first and
	// nothing touches the freed target afterwards; die() has already saved it.
	reset_fixture(MAXLVLMORTAL + 1);
	learn(pupil_pc, SKILL_TOUGHNESS, 100);
	dying = &pupil;
	reset("reset Pupil");
	ASAN_UNPOISON_MEMORY_REGION(&pupil, sizeof(pupil));
	dying = nullptr;
	assert(refreshes == 1 && !vitals && !saves);
	assert(feedback == "pupil:&+GYour epic skills have been reset.&n\r\n"
			   "staff:You reset Pupil's epic skills.\r\n");
	assert(!pupil_pc.skills[SKILL_TOUGHNESS].learned);

	// A missing target and a mortal caller change and save nothing.
	reset_fixture(MAXLVLMORTAL + 1);
	learn(pupil_pc, SKILL_TOUGHNESS, 50);
	reset("reset Nobody");
	assert(feedback == "staff:They don't appear to be in the game.\n" && !saves && !refreshes);
	reset_fixture(MAXLVLMORTAL);
	learn(staff_pc, SKILL_TOUGHNESS, 50);
	reset("reset");
	assert(feedback.find("Epic resetting is unavailable") != std::string::npos);
	assert(!saves && !refreshes);
	assert(staff_pc.skills[SKILL_TOUGHNESS].learned == 50);

	std::puts(
		"PASS epic reset: bounded scan, self/named targets, exclusions, refresh, fatal refresh, notices, link-dead notice, refusals");
}
