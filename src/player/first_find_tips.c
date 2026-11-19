/****************************************************************************
 *
 *  File: first_find_tips.c                                     Part of Duris
 *  Usage: the one-time tip a new character sees on first finding each kind
 *         of random drop or crafting item
 *
 *  Additions since 2025 by the Duris maintainers and since 2026 by
 *    LuminariMUD maintainers are public domain (Unlicense, see LICENSE)
 *
 ****************************************************************************/

#include "player/first_find_tips.h"
#include "core/prototypes.h"
#include "core/structs.h"
#include "core/utils.h"
#include "economy/tradeskill.h"
#include "item/named_set_origin.h"
#include "persistence/persistence_checkpoint.h"
#include "world/vnum.obj.h"

#include <string>

namespace
{
// A tip's position is its saved bit: add new tips at the end and never reorder them.
enum tip_kind
{
	RANDOM_GEAR,
	NAMED_GEAR,
	SALVAGE_MATERIAL,
	ENCRUST_STONE,
	RECIPE,
	MAGICAL_ESSENCE,
	ENHANCEMENT_ESSENCE,
	SOUL_SHARD,
	DRAGON_SCALE,
	ORE,
	GEM,
	FISH,
	FORAGE,
	TIP_COUNT
};

struct first_find_tip_text
{
	const char *title;
	const char *art[4]; // nine columns once colour codes are removed
	const char *text[3]; // at most 56 columns once colour codes are removed
};

const first_find_tip_text tips[TIP_COUNT] = {
	{ "Random Equipment",
	  { "&+W    /\\   ", "&+W    ||   ", "&+y  <=##=> ", "&+y    ||   " },
	  { "Fallen foes sometimes leave randomly forged gear. Its",
	    "shape, material and adjective set its stats, so check",
	    "it before you wear it.  &+cSee: help random equipment" } },
	{ "Named Set Equipment",
	  { "&+Y /\\/\\/\\  ", "&+Y |&+R*&+Bo&+R*&+Bo&+Y|  ", "&+Y |____|  ", "&+y  \\__/   " },
	  { "Gear tagged '&+rfrom <zone>&n' belongs to that zone's set.",
	    "Wear several pieces from one zone for bonus hit points",
	    "and set spells.  &+cSee: namedreport, help named equipment" } },
	{ "Salvaged Material",
	  { "&+c   ___   ", "&+c  /__/|  ", "&+C /__/|/| ", "&+c|__|/_|/ " },
	  { "Crafting material, found on kills or salvaged from",
	    "gear. Crafters and forgers spend it to make equipment",
	    "from known recipes.  &+cSee: help salvage, help craft" } },
	{ "Encrust Stone",
	  { "&+M   ___   ", "&+M  /. .\\  ", "&+m ( .:. ) ", "&+M  \\___/  " },
	  { "A stone that can be set into a piece of equipment to",
	    "give it a lasting magical power, using the Encrust",
	    "skill.  &+cSee: help encrust" } },
	{ "Crafting Recipe",
	  { "&+y .-----. ", "&+y | &+w~~~&+y | ", "&+y | &+w~~~&+y | ", "&+y '-----' " },
	  { "Recite it to learn the item it describes. Forge makes",
	    "armor and weapons; Craft makes cloaks, belts, jewelry.",
	    "&+cSee: help craft, help forge" } },
	{ "Magical Essence",
	  { "&+M  .  &+Y*&+M   ", "&+Y * &+M(&+Y@&+M)&+Y . ", "&+M  ' &+Y*&+M '  ",
	    "&+Y   . &+M*   " },
	  { "Salvaging magical gear can free this rare essence.",
	    "Crafters and forgers need it to make magical items",
	    "from their recipes.  &+cSee: help craft, help forge" } },
	{ "Enhancement Essence",
	  { "&+C   |~|   ", "&+C   | |   ", "&+C  /&+B~~~&+C\\  ", "&+C  \\___/  " },
	  { "Foes drop these now and then, strong ones more often.",
	    "Each is tied to one stat, and the &+Wenhance&n command",
	    "uses it to improve your gear.  &+cSee: enhance" } },
	{ "Ethereal Soul Shard",
	  { "&+W    /\\   ", "&+W   /&+r##&+W\\  ", "&+W   \\&+r##&+W/  ", "&+W    \\/   " },
	  { "Shards form when mighty creatures above level 51 die.",
	    "Carry three to the Harvester and buy a greater orb of", "magic from that list." } },
	{ "Dragon Scale",
	  { "&+L (_)(_)  ", "&+L(_)(&+g_&+L)(_)", "&+L (_)(_)  ", "&+L  (_)    " },
	  { "Every dragon you slay leaves one of these scales.",
	    "Necromancers carry them to strengthen their Wall of", "Bones spell." } },
	{ "Raw Ore",
	  { "&+L   ___   ", "&+L _/ &+co&+L \\_ ", "&+L/ &+yo&+L   &+co&+L \\",
	    "&+L\\___&+Wo&+L___/" },
	  { "Mining pulls ore of eight metals, in three sizes, from",
	    "mines across the realms. Bigger and rarer ore is worth",
	    "more coin to shopkeepers.  &+cSee: help mine" } },
	{ "Gemstone",
	  { "&+C  _____  ", "&+C /_|_|_\\ ", "&+C \\ \\|/ / ", "&+C  \\_|_/  " },
	  { "A rare find while mining, and the gem mines hold even",
	    "more. Gems fetch good coin from shopkeepers.", "&+cSee: help mine" } },
	{ "Fresh Fish",
	  { "&+b   ~ ~   ", "&+c  ><(((&+Wo&+c>", "&+b   ~ ~ ~ ", "&+b  ~~~~~~ " },
	  { "Fish are caught with a fishing pole and make a fine",
	    "meal. Fishing earns experience too.", "&+cSee: help fishing" } },
	{ "Foraged Goods",
	  { "&+r   ,&+b@&+r,   ", "&+b  @&+r,&+b@&+r,&+b@  ", "&+g   \\|/   ", "&+g    |    " },
	  { "Foraging in the wilds turns up food such as berries,",
	    "roots and mushrooms, plus the odd herb. Eat what you",
	    "find to keep hunger away.  &+cSee: help forage" } },
};

// The stat essences that enhance.c drops from eligible NPCs.
constexpr int FIRST_ENHANCEMENT_ESSENCE = 400238;
constexpr int LAST_ENHANCEMENT_ESSENCE = 400258;

int tip_for(const obj_data *object)
{
	const int vnum = OBJ_VNUM(object);
	if (vnum == VOBJ_RANDOM_ARMOR || vnum == VOBJ_RANDOM_WEAPON)
		return named_set_origin(object).zone > 0 ? NAMED_GEAR : RANDOM_GEAR;
	if (vnum >= LOWEST_MAT_VNUM && vnum <= HIGHEST_MAT_VNUM)
		return SALVAGE_MATERIAL;
	if (vnum >= ENCRUST_VNUM_BEGIN && vnum <= ENCRUST_VNUM_END)
		return ENCRUST_STONE;
	if (vnum == SALVAGE_RECIPE_VNUM)
		return RECIPE;
	if (vnum == MAG_ESSENCE_VNUM)
		return MAGICAL_ESSENCE;
	if (vnum >= FIRST_ENHANCEMENT_ESSENCE && vnum <= LAST_ENHANCEMENT_ESSENCE)
		return ENHANCEMENT_ESSENCE;
	if (vnum == VOBJ_SOUL_SHARD)
		return SOUL_SHARD;
	if (vnum == VOBJ_DRAGON_SCALE)
		return DRAGON_SCALE;
	// Mined gems also carry the ore keyword.
	if (isname("_gem_", object->name))
		return GEM;
	if (isname("_ore_", object->name))
		return ORE;
	if (isname("_fishing_", object->name))
		return FISH;
	if (vnum >= VOBJ_FORAGE_FIRST && vnum < VOBJ_FORAGE_FIRST + VOBJ_FORAGE_NUM_TYPES)
		return FORAGE;
	return -1;
}
} // namespace

void first_find_tip(P_char ch, const obj_data *object)
{
	if (!ch || !IS_PC(ch) || !ch->desc || STATE(ch->desc) != CON_PLAYING)
		return;
	const int kind = tip_for(object);
	if (kind < 0 || (ch->only.pc->first_find_tips & (uint64_t{ 1 } << kind)))
		return;
	ch->only.pc->first_find_tips |= uint64_t{ 1 } << kind;
	mark_player_dirty_components(GET_PID(ch), PLAYER_COMPONENT_STATUS);

	const first_find_tip_text &tip = tips[kind];
	std::string message =
		"\r\n&+L.--------------------------------------------------------------------.&n\r\n";
	message +=
		std::string("  ") + tip.art[0] + "&n   &+YFirst find: &+W" + tip.title + "&n\r\n";
	for (int line = 1; line < 4; ++line)
		message +=
			std::string("  ") + tip.art[line] + "&n   " + tip.text[line - 1] + "&n\r\n";
	message +=
		"&+L'---------------------------------------------- &+wthis tip shows once &+L-'&n\r\n";
	send_to_char(message.c_str(), ch);
}
