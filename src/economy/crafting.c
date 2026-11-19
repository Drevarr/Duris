/*
 * Craft and Forge: configuration, recipe books, material plans and the shared
 * `craft`/`forge` command. Preview and execution use the same plan, so they
 * cannot drift on material costs.
 */
#include "abilities/abilities.h"
#include "core/prototypes.h"
#include "core/structs.h"
#include "net/comm.h"
#include "core/config.h"
#include "core/config_parse.h"
#include "world/db.h"
#include "world/events.h"
#include "cmd/interp.h"
#include "item/objmisc.h"
#include "item/item_value.h"
#include "magic/spells.h"
#include "world/vnum.obj.h"
#include "economy/crafting.h"
#include "combat/chaos_materials.h"
#include "core/utils.h"
#include "sql/sql_player.h"
#include <math.h>
#include <limits.h>
#include <float.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

namespace
{
bool grant_crafted_item(P_char ch, P_obj object)
{
	if (obj_to_char(object, ch))
		return true;
	send_to_char("The crafted item could not be delivered.\r\n", ch);
	return false;
}
}

static int crafting_level_gate = 3;
static int crafting_recipe_max_player_level = MAXLVLMORTAL;
static int crafting_experience_per_item_value = 1000;
static double crafting_material_quantity_multiplier = 1.0;
static bool crafting_recipe_examine_materials = TRUE;
static bool crafting_recipe_display_vnums = TRUE;
static bool crafting_craft_enabled = TRUE;
static bool crafting_forge_enabled = TRUE;
static int crafting_craft_essence_vnum = VOBJ_CRAFTING_ESSENCE;
static int crafting_craft_tool_vnum = VOBJ_CRAFTING_TOOLS;
static int crafting_forge_essence_vnum = VOBJ_FORGING_ESSENCE;
static int crafting_forge_tool_vnum = VOBJ_FORGING_FLUX;
static int crafting_scientific_tools_vnum_value = VOBJ_EPIC_LANTAN_TOOLS;
static bool crafting_scientific_tools_prevent_breakage_value = TRUE;
static int crafting_scientific_tools_recipe_roll_divisor_value = 15;
static int crafting_scientific_tools_recipe_player_multiplier_value = 2;
static double crafting_salvage_essence_luck_multiplier_value = 1.0;
static double crafting_salvage_essence_chance_multiplier_value = 1.0;

static void crafting_validate_content_vnum(int *configured_vnum, int default_vnum, const char *key)
{
	if (real_object(*configured_vnum) >= 0)
		return;
	logit(LOG_STATUS, "WARNING: %s vnum %d does not exist; using default %d.", key,
	      *configured_vnum, default_vnum);
	*configured_vnum = default_vnum;
}

static int crafting_config_int(const char *key, const char *text, int previous, int low, int high)
{
	int value;
	if (!config_parse_int(text, value) || value < low || value > high)
	{
		logit(LOG_STATUS, "Invalid crafting config %s=%s; retaining previous value.", key,
		      text);
		return previous;
	}
	return value;
}

static double crafting_config_real(const char *key, const char *text, double previous,
				   bool allow_zero, double maximum)
{
	double value;
	if (!config_parse_double(text, value) || value < 0 || (!allow_zero && value == 0) ||
	    value > maximum)
	{
		logit(LOG_STATUS, "Invalid crafting config %s=%s; retaining previous value.", key,
		      text);
		return previous;
	}
	return value;
}

static void load_crafting_config(void)
{
	FILE *fp;
	char line[512];
	char *key, *value, *equals, *end;

	/* A restart/boot always starts from historical defaults. */
	crafting_level_gate = 3;
	crafting_recipe_max_player_level = MAXLVLMORTAL;
	crafting_experience_per_item_value = 1000;
	crafting_material_quantity_multiplier = 1.0;
	crafting_recipe_examine_materials = TRUE;
	crafting_recipe_display_vnums = TRUE;
	crafting_craft_enabled = TRUE;
	crafting_forge_enabled = TRUE;
	crafting_craft_essence_vnum = VOBJ_CRAFTING_ESSENCE;
	crafting_craft_tool_vnum = VOBJ_CRAFTING_TOOLS;
	crafting_forge_essence_vnum = VOBJ_FORGING_ESSENCE;
	crafting_forge_tool_vnum = VOBJ_FORGING_FLUX;
	crafting_scientific_tools_vnum_value = VOBJ_EPIC_LANTAN_TOOLS;
	crafting_scientific_tools_prevent_breakage_value = TRUE;
	crafting_scientific_tools_recipe_roll_divisor_value = 15;
	crafting_scientific_tools_recipe_player_multiplier_value = 2;
	crafting_salvage_essence_luck_multiplier_value = 1.0;
	crafting_salvage_essence_chance_multiplier_value = 1.0;

	fp = fopen("lib/crafting.cfg", "r");
	if (fp == NULL)
	{
		fprintf(stderr, "WARNING: Cannot open lib/crafting.cfg — using defaults.\n");
		logit(LOG_STATUS, "WARNING: Cannot open lib/crafting.cfg — using defaults.");
		return;
	}

	while (fgets(line, sizeof(line), fp) != NULL)
	{
		// Judge by length: an embedded NUL must not make a complete line look cut off.
		if (strlen(line) == sizeof(line) - 1 && line[sizeof(line) - 2] != '\n')
		{
			int next = fgetc(fp);
			if (next != EOF && next != '\n')
			{
				while (next != EOF && next != '\n')
					next = fgetc(fp);
				logit(LOG_STATUS, "Ignoring overlong crafting config line.");
				continue;
			}
		}
		key = line;
		while (*key == ' ' || *key == '\t')
			key++;
		if (*key == '\0' || *key == '\n' || *key == '#')
			continue;
		equals = strchr(key, '=');
		if (equals == NULL)
			continue;
		*equals = '\0';
		end = equals;
		while (end > key && (end[-1] == ' ' || end[-1] == '\t'))
			*--end = '\0';
		value = equals + 1;
		while (*value == ' ' || *value == '\t')
			value++;
		end = value + strlen(value);
		while (end > value &&
		       (end[-1] == '\n' || end[-1] == '\r' || end[-1] == ' ' || end[-1] == '\t'))
			*--end = '\0';

		if (!strcmp(key, "crafting.level.gate.multiplier"))
			crafting_level_gate =
				crafting_config_int(key, value, crafting_level_gate, 1, INT_MAX);
		else if (!strcmp(key, "crafting.recipe.max.player.level"))
			crafting_recipe_max_player_level = crafting_config_int(
				key, value, crafting_recipe_max_player_level, 1, MAXLVLMORTAL);
		else if (!strcmp(key, "crafting.recipe.examine.materials"))
			crafting_recipe_examine_materials = crafting_config_int(
				key, value, crafting_recipe_examine_materials, 0, 1);
		else if (!strcmp(key, "crafting.recipe.display.vnums"))
			crafting_recipe_display_vnums = crafting_config_int(
				key, value, crafting_recipe_display_vnums, 0, 1);
		else if (!strcmp(key, "crafting.experience.per.ival"))
			crafting_experience_per_item_value = crafting_config_int(
				key, value, crafting_experience_per_item_value, 0, INT_MAX);
		else if (!strcmp(key, "crafting.material.quantity.multiplier"))
			crafting_material_quantity_multiplier = crafting_config_real(
				key, value, crafting_material_quantity_multiplier, false, INT_MAX);
		else if (!strcmp(key, "crafting.craft.enabled"))
			crafting_craft_enabled =
				crafting_config_int(key, value, crafting_craft_enabled, 0, 1);
		else if (!strcmp(key, "crafting.forge.enabled"))
			crafting_forge_enabled =
				crafting_config_int(key, value, crafting_forge_enabled, 0, 1);
		else if (!strcmp(key, "crafting.craft.essence.vnum"))
			crafting_craft_essence_vnum = crafting_config_int(
				key, value, crafting_craft_essence_vnum, 1, INT_MAX);
		else if (!strcmp(key, "crafting.craft.tool.vnum"))
			crafting_craft_tool_vnum = crafting_config_int(
				key, value, crafting_craft_tool_vnum, 1, INT_MAX);
		else if (!strcmp(key, "crafting.forge.essence.vnum"))
			crafting_forge_essence_vnum = crafting_config_int(
				key, value, crafting_forge_essence_vnum, 1, INT_MAX);
		else if (!strcmp(key, "crafting.forge.tool.vnum"))
			crafting_forge_tool_vnum = crafting_config_int(
				key, value, crafting_forge_tool_vnum, 1, INT_MAX);
		else if (!strcmp(key, "crafting.salvage.scientific.tools.vnum"))
			crafting_scientific_tools_vnum_value = crafting_config_int(
				key, value, crafting_scientific_tools_vnum_value, 1, INT_MAX);
		else if (!strcmp(key, "crafting.salvage.scientific.tools.prevent.breakage"))
			crafting_scientific_tools_prevent_breakage_value = crafting_config_int(
				key, value, crafting_scientific_tools_prevent_breakage_value, 0, 1);
		else if (!strcmp(key, "crafting.salvage.scientific.tools.recipe.roll.divisor"))
			crafting_scientific_tools_recipe_roll_divisor_value = crafting_config_int(
				key, value, crafting_scientific_tools_recipe_roll_divisor_value, 1,
				INT_MAX);
		else if (!strcmp(key, "crafting.salvage.scientific.tools.recipe.player.multiplier"))
			crafting_scientific_tools_recipe_player_multiplier_value =
				crafting_config_int(
					key, value,
					crafting_scientific_tools_recipe_player_multiplier_value, 1,
					INT_MAX);
		else if (!strcmp(key, "crafting.salvage.essence.luck.multiplier"))
			crafting_salvage_essence_luck_multiplier_value = crafting_config_real(
				key, value, crafting_salvage_essence_luck_multiplier_value, false,
				DBL_MAX);
		else if (!strcmp(key, "crafting.salvage.essence.chance.multiplier"))
			crafting_salvage_essence_chance_multiplier_value = crafting_config_real(
				key, value, crafting_salvage_essence_chance_multiplier_value, true,
				DBL_MAX);
	}
	fclose(fp);

	// Recipes are offered up to gate * max level; say so when that plan cannot be represented.
	const int64_t top_item_value = std::min<int64_t>(static_cast<int64_t>(crafting_level_gate) *
								 crafting_recipe_max_player_level,
							 INT_MAX);
	int high, low;
	if (top_item_value * crafting_experience_per_item_value > INT_MAX ||
	    !item_value_material_quantities(static_cast<int>(top_item_value),
					    crafting_material_quantity_multiplier, high, low))
		logit(LOG_STATUS,
		      "WARNING: lib/crafting.cfg experience rate or material multiplier is too large; some recipes up to item value %lld cannot be made.",
		      static_cast<long long>(top_item_value));

	/* Content references are configurable, but invalid entries must not turn a
	 * recipe into an unfulfillable or silently free transaction. */
	crafting_validate_content_vnum(&crafting_craft_essence_vnum, VOBJ_CRAFTING_ESSENCE,
				       "crafting.craft.essence.vnum");
	crafting_validate_content_vnum(&crafting_craft_tool_vnum, VOBJ_CRAFTING_TOOLS,
				       "crafting.craft.tool.vnum");
	crafting_validate_content_vnum(&crafting_forge_essence_vnum, VOBJ_FORGING_ESSENCE,
				       "crafting.forge.essence.vnum");
	crafting_validate_content_vnum(&crafting_forge_tool_vnum, VOBJ_FORGING_FLUX,
				       "crafting.forge.tool.vnum");
	crafting_validate_content_vnum(&crafting_scientific_tools_vnum_value,
				       VOBJ_EPIC_LANTAN_TOOLS,
				       "crafting.salvage.scientific.tools.vnum");
}

int crafting_scientific_tools_vnum(void)
{
	return crafting_scientific_tools_vnum_value;
}
bool crafting_scientific_tools_prevent_breakage(void)
{
	return crafting_scientific_tools_prevent_breakage_value;
}
int crafting_scientific_tools_recipe_roll_divisor(void)
{
	return crafting_scientific_tools_recipe_roll_divisor_value;
}
int crafting_scientific_tools_recipe_player_multiplier(void)
{
	return crafting_scientific_tools_recipe_player_multiplier_value;
}
double crafting_salvage_essence_luck_multiplier(void)
{
	return crafting_salvage_essence_luck_multiplier_value;
}
double crafting_salvage_essence_chance_multiplier(void)
{
	return crafting_salvage_essence_chance_multiplier_value;
}

/* Any fifth-bitvector affect makes a recipe magical. */
bool has_affect(P_obj obj)
{
	if (IS_SET(obj->bitvector, AFF_STONE_SKIN) || IS_SET(obj->bitvector, AFF_HIDE) ||
	    IS_SET(obj->bitvector, AFF_SNEAK) || IS_SET(obj->bitvector, AFF_FLY) ||
	    IS_SET(obj->bitvector4, AFF4_NOFEAR) || IS_SET(obj->bitvector2, AFF2_AIR_AURA) ||
	    IS_SET(obj->bitvector2, AFF2_EARTH_AURA) ||
	    IS_SET(obj->bitvector3, AFF3_INERTIAL_BARRIER) ||
	    IS_SET(obj->bitvector3, AFF3_REDUCE) || IS_SET(obj->bitvector2, AFF2_GLOBE) ||
	    IS_SET(obj->bitvector, AFF_HASTE) || IS_SET(obj->bitvector, AFF_DETECT_INVISIBLE) ||
	    IS_SET(obj->bitvector4, AFF4_DETECT_ILLUSION) || obj->bitvector5)
	{
		return TRUE;
	}
	return FALSE;
}

bool crafting_build_plan(P_obj item, struct crafting_plan *plan)
{
	int item_value;
	int low_material_vnum;
	int high_material_count, low_material_count;

	if (item == NULL || plan == NULL)
	{
		return FALSE;
	}

	item_value = itemvalue(item);
	low_material_vnum = get_matstart(item);
	if (item_value < 1 || low_material_vnum <= 0)
	{
		return FALSE;
	}

	const int64_t experience =
		static_cast<int64_t>(item_value) * crafting_experience_per_ival();
	if (experience < 0 || experience > INT_MAX ||
	    !item_value_material_quantities(item_value, crafting_material_quantity_multiplier,
					    high_material_count, low_material_count))
		return FALSE;
	plan->item_value = item_value;
	plan->low_material_vnum = low_material_vnum;
	plan->high_material_vnum = low_material_vnum + 4;
	plan->high_material_count = high_material_count;
	plan->low_material_count = low_material_count;
	plan->experience = static_cast<int>(experience);
	plan->magical = has_affect(item);
	return TRUE;
}

bool crafting_validate_recipe_target(P_obj item)
{
	struct crafting_plan plan;

	return item != NULL && !IS_OBJ_STAT2(item, ITEM2_QUESTITEM) && is_salvageable(item) &&
	       crafting_build_plan(item, &plan);
}

bool crafting_recipe_target_is_available(P_obj item)
{
	struct crafting_plan plan;

	if (!crafting_validate_recipe_target(item) ||
	    (!crafting_craft_enabled && !crafting_forge_enabled) ||
	    !crafting_build_plan(item, &plan))
		return FALSE;
	return plan.item_value <=
	       static_cast<int64_t>(crafting_level_gate) * crafting_recipe_max_player_level;
}

void crafting_configure_recipe_scroll(P_obj recipe, P_obj target)
{
	struct crafting_plan plan;
	P_obj low, high;
	char text[MAX_STRING_LENGTH];

	if (!crafting_recipe_examine_materials || recipe == NULL ||
	    !crafting_build_plan(target, &plan))
		return;
	low = read_object(plan.low_material_vnum, VIRTUAL);
	high = read_object(plan.high_material_vnum, VIRTUAL);
	if (!low || !high)
	{
		if (low)
			extract_obj(low);
		if (high)
			extract_obj(high);
		return;
	}
	snprintf(text, sizeof(text),
		 "This recipe teaches %s.\r\n\r\nRequired materials:\r\n  %d %s\r\n  %d %s\r\n",
		 target->short_description, plan.high_material_count, high->short_description,
		 plan.low_material_count, low->short_description);
	if (plan.magical)
	{
		char requirement[160];
		snprintf(requirement, sizeof(requirement),
			 "  1 magical essence (required for magical items)\r\n");
		strncat(text, requirement, sizeof(text) - strlen(text) - 1);
	}
	strncat(text, "\r\nDiscipline consumables (in addition to the materials above):\r\n",
		sizeof(text) - strlen(text) - 1);
	{
		char requirement[256];
		snprintf(requirement, sizeof(requirement),
			 "  Craft: 1 gnomish crafting tool box (configured item vnum %d)\r\n"
			 "  Forge: 1 blacksmithing flux (configured item vnum %d)\r\n",
			 crafting_craft_tool_vnum, crafting_forge_tool_vnum);
		strncat(text, requirement, sizeof(text) - strlen(text) - 1);
	}
	strncat(text,
		"\r\nUse the recipe to learn it, then `craft` or `forge` to view and make it.\r\n",
		sizeof(text) - strlen(text) - 1);
	if ((recipe->str_mask & STRUNG_DESC3) && recipe->action_description)
		FREE(recipe->action_description);
	recipe->action_description = str_dup(text);
	recipe->str_mask |= STRUNG_DESC3;
	extract_obj(low);
	extract_obj(high);
}

void boot_crafting_system(void)
{
	load_crafting_config();
	chaos_materials_initialize();
}

int crafting_level_gate_multiplier(void)
{
	return crafting_level_gate;
}

// The most valuable recipe a character's level can make.
static int64_t crafting_value_limit(P_char ch)
{
	return static_cast<int64_t>(GET_LEVEL(ch)) * crafting_level_gate_multiplier();
}

static std::string crafting_facts(P_char ch, const char *tool)
{
	return fact("Highest recipe value you can make",
		    std::to_string(crafting_value_limit(ch)) + ", " +
			    std::to_string(crafting_level_gate_multiplier()) + " per level") +
	       "  Each recipe also takes its materials and " + tool +
	       ".\n"
	       "  You can know only one of forge, mine and craft.\n";
}

std::string craft_facts(P_char ch)
{
	if (!GET_CHAR_SKILL(ch, SKILL_CRAFT))
		return "  You have not learned to craft.\n";
	return crafting_facts(ch, "a tool box") +
	       "  Name a strange stone after `craft make` to give the item its magic.\n";
}

std::string forge_facts(P_char ch)
{
	if (!GET_CHAR_SKILL(ch, SKILL_FORGE))
		return "  You have not learned to forge.\n";
	return crafting_facts(ch, "flux");
}

int crafting_experience_per_ival(void)
{
	return crafting_experience_per_item_value;
}

bool crafting_mode_enabled(enum crafting_mode mode)
{
	return mode == CRAFTING_MODE_CRAFT ? crafting_craft_enabled : crafting_forge_enabled;
}

int crafting_essence_vnum(enum crafting_mode mode)
{
	return mode == CRAFTING_MODE_CRAFT ? crafting_craft_essence_vnum :
					     crafting_forge_essence_vnum;
}

int crafting_tool_vnum(enum crafting_mode mode)
{
	return mode == CRAFTING_MODE_CRAFT ? crafting_craft_tool_vnum : crafting_forge_tool_vnum;
}

void crafting_examine_support_item(P_char ch, P_obj item)
{
	if (!ch || !item)
		return;
	if (OBJ_VNUM(item) == crafting_tool_vnum(CRAFTING_MODE_FORGE) &&
	    GET_CHAR_SKILL(ch, SKILL_FORGE))
		send_to_char(
			"&+yForge insight:&n This flux is consumed to bind the materials when you forge a recipe. Use `forge info <number>` to see what else you need.\r\n",
			ch);
	else if (OBJ_VNUM(item) == crafting_tool_vnum(CRAFTING_MODE_CRAFT) &&
		 GET_CHAR_SKILL(ch, SKILL_CRAFT))
		send_to_char(
			"&+yCraft insight:&n This tool box is consumed while shaping a recipe. Use `craft info <number>` to see what else you need.\r\n",
			ch);
}

/* SQL is canonical. The legacy file is read only when a player has no SQL
 * recipes, and each valid entry is imported through the idempotent SQL API. */
int *crafting_get_player_recipes(P_char ch, int *count)
{
	int *recipes;
	int recipe_vnum;
	int capacity = 0;
	FILE *fp;
	char name[256];
	char path[512];
	char *p;

	if (count == NULL)
		return NULL;
	*count = 0;
	if (ch == NULL)
		return NULL;

	recipes = sql_get_player_recipes(GET_PID(ch), count);
	if (recipes != NULL || *count != 0)
	{
		int i, kept = 0;
		for (i = 0; i < *count; i++)
		{
			P_obj target = read_object(recipes[i], VIRTUAL);
			if (target && crafting_recipe_target_is_available(target))
				recipes[kept++] = recipes[i];
			if (target)
				extract_obj(target);
		}
		*count = kept;
		return recipes;
	}

	snprintf(name, sizeof(name), "%s", GET_NAME(ch));
	for (p = name; *p; p++)
		*p = LOWER(*p);
	snprintf(path, sizeof(path), "Players/Tradeskills/%c/%s.crafting", name[0], name);
	fp = fopen(path, "r");
	if (fp == NULL)
		return NULL;

	while (fscanf(fp, "%d", &recipe_vnum) == 1)
	{
		int *grown;
		int i;
		bool duplicate = FALSE;
		P_obj target;
		if (recipe_vnum <= 0 || real_object(recipe_vnum) < 0)
			continue;
		target = read_object(recipe_vnum, VIRTUAL);
		if (!target || !crafting_recipe_target_is_available(target))
		{
			if (target)
				extract_obj(target);
			continue;
		}
		extract_obj(target);
		for (i = 0; i < *count; i++)
			if (recipes[i] == recipe_vnum)
				duplicate = TRUE;
		if (duplicate)
			continue;
		if (*count == capacity)
		{
			capacity = capacity ? capacity * 2 : 16;
			grown = (int *)realloc(recipes, sizeof(*recipes) * capacity);
			if (grown == NULL)
			{
				free(recipes);
				fclose(fp);
				*count = 0;
				return NULL;
			}
			recipes = grown;
		}
		recipes[(*count)++] = recipe_vnum;
		sql_add_player_recipe(GET_PID(ch), recipe_vnum);
	}
	fclose(fp);
	return recipes;
}

namespace
{
/* What sets Craft and Forge apart. Recipe selection, costs, consumption and the
 * single save are shared, so the two disciplines cannot drift apart. */
struct crafting_discipline
{
	enum crafting_mode mode;
	int skill;
	const char *verb; /* the command word */
	const char *title;
	const char *past;
	const char *not_learned;
	const char *tool_needed;
	const char *tool_missing;
	const char *work_to_room;
	const char *work_to_char;
	bool takes_stone;
};

const crafting_discipline craft_discipline = {
	CRAFTING_MODE_CRAFT,
	SKILL_CRAFT,
	"craft",
	"Craft",
	"crafted",
	"You do not know how to &+rcraft&n items.\r\n",
	"You will also need one gnomish crafting tool box; it is consumed as you work.\r\n",
	"You must have &+ma &+ybox &+mof &+Rgnomish &+rcrafting &+mtools&n to create your item.\r\n",
	"&+W$n &+Ldelicately opens their &+ybox &+mof &+Rgnomish &+rcrafting &+mtools&+L and starts their work...\r\n"
	"&+W$n &+Lremoves the &+Wim&+wpur&+Lities &+Lfrom their &+ymaterials &+Land gently assembles a masterpiece...\r\n"
	"&+L...hands shaking, &+W$n &+Lraises their head and &+Ysmiles&+L, admiring their new $p.&N",
	"You &+Ldelicately open your &+ybox &+mof &+Rgnomish &+rcrafting &+mtools&+L and get to work...\r\n"
	"you &+Lremove the &+Wim&+wpur&+Lities &+Lfrom your &+ymaterials &+Land gently assemble a masterpiece...\r\n"
	"&+L...hands shaking, &+Wyou &+Lraise your head and &+Ysmile&+L, admiring your new $p.&N",
	true,
};

const crafting_discipline forge_discipline = {
	CRAFTING_MODE_FORGE,
	SKILL_FORGE,
	"forge",
	"Forge",
	"forged",
	"You do not know how to &+Lforge&n.\r\n",
	"You will also need one blacksmithing flux; it is consumed to bind the work.\r\n",
	"You must have a &+Lblacksmithing &nflux to complete the smithing process!\r\n",
	"&+W$n &+Lgently takes their &+ymaterials&+L, their &nflux&+L, and places them into the &+rf&+Ro&+Yr&+Rg&+re&+L.\r\n"
	"&+W$n &+Lremoves the &+yitems &+Lfrom the &+rheat &+Land starts to &nhammer &+Laway at the mixture..\r\n"
	"&+L...after shedding plenty of &+Wsweat&+L, &+W$n &+Lsteps back, admiring their new $p.&N",
	"You &+Lgently take your &+ymaterials&+L, the &nflux&+L, and place them into the &+rf&+Ro&+Yr&+Rg&+re&+L.\r\n"
	"You &+Lremove the &+yitems &+Lfrom the &+rheat &+Land start to &nhammer &+Laway at the mixture..\r\n"
	"&+L...after shedding plenty of &+Wsweat&+L, you &+Lstep back, admiring your new $p.&N",
	false,
};

const char *const crafting_tome_line =
	"&+yYou open your &+Ltome &+yof &+Ycra&+yftsm&+Lanship &+yand examine the &+Litem&n.\r\n";
const char *const crafting_unknown_materials =
	"You can't work out what this is made of. Please report it with `bug`.\r\n";

/* Strange stones (random drops) carry their magic as plain affect bits. */
bool crafting_is_stone(P_obj obj)
{
	return OBJ_VNUM(obj) >= ENCRUST_VNUM_BEGIN && OBJ_VNUM(obj) <= ENCRUST_VNUM_END;
}

bool crafting_stone_adds_magic(P_obj stone, P_obj item)
{
	return (stone->bitvector & ~item->bitvector) || (stone->bitvector2 & ~item->bitvector2) ||
	       (stone->bitvector3 & ~item->bitvector3) || (stone->bitvector4 & ~item->bitvector4) ||
	       (stone->bitvector5 & ~item->bitvector5);
}

void crafting_apply_stone(P_obj item, P_obj stone)
{
	item->bitvector |= stone->bitvector;
	item->bitvector2 |= stone->bitvector2;
	item->bitvector3 |= stone->bitvector3;
	item->bitvector4 |= stone->bitvector4;
	item->bitvector5 |= stone->bitvector5;
}

void crafting_award_experience(P_char ch, const crafting_plan &plan)
{
	if (plan.experience > 0)
		gain_exp(ch, NULL, plan.experience, EXP_BOON);
}

int crafting_select_recipe(const int *recipes, int count, int choice)
{
	if (choice <= 0)
		return 0;
	for (int i = 0; i < count; ++i)
		if (recipes[i] == choice)
			return choice;
	if (choice <= count)
		return recipes[choice - 1] > 0 ? recipes[choice - 1] : 0;
	return 0;
}

void crafting_show_recipes(P_char ch, const crafting_discipline &d, const int *recipes, int count)
{
	const char *const rule =
		"----------------------------------------------------------------------------\r\n";
	std::string header = std::string("&+w") + d.title + " Syntax:\r\n";
	const auto usage = [&](const char *line) { header += std::string("&+w") + d.verb + line; };
	header += std::string("&+w") + d.verb + " or " + d.verb +
		  " list       - list your recipes\r\n";
	usage(" info <number>      - show costs and requirements\r\n");
	usage(" stat <number>      - inspect the finished item\r\n");
	usage(" make <number>      - consume requirements and create it\r\n");
	if (d.takes_stone)
		usage(" make <number> <stone> - also give it a strange stone's magic\r\n");
	header += std::string("&+yYou know the following recipes:&n\r\n") + rule +
		  "&+B#     Recipe vnum       &+MItem&n\r\n";
	send_to_char(header.c_str(), ch);
	// One write per recipe: a large book in one string would pass the output limit
	// and be dropped whole.
	for (int i = 0; i < count; i++)
	{
		P_obj target = read_object(recipes[i], VIRTUAL);
		if (!target)
		{
			logit(LOG_DEBUG, "%s: '%s' has bad recipe vnum %d.", d.verb, J_NAME(ch),
			      recipes[i]);
			continue;
		}
		char line[MAX_STRING_LENGTH];
		if (crafting_recipe_display_vnums)
			snprintf(line, sizeof line, "   &+W%-4d  %-18d&n%s&n\r\n%s", i + 1,
				 recipes[i], target->short_description, rule);
		else
			snprintf(line, sizeof line, "   &+W%-4d  &n%s&n\r\n%s", i + 1,
				 target->short_description, rule);
		send_to_char(line, ch);
		extract_obj(target);
	}
}

void crafting_show_info(P_char ch, const crafting_discipline &d, P_obj target)
{
	struct crafting_plan plan;
	if (!crafting_build_plan(target, &plan))
	{
		send_to_char(crafting_unknown_materials, ch);
		return;
	}
	P_obj low = read_object(plan.low_material_vnum, VIRTUAL);
	P_obj high = read_object(plan.high_material_vnum, VIRTUAL);
	if (!low || !high)
	{
		send_to_char(crafting_unknown_materials, ch);
		debug("%s info: missing a material for '%s' (%d).", d.verb,
		      target->short_description, OBJ_VNUM(target));
	}
	else
	{
		char text[MAX_STRING_LENGTH];
		send_to_char(crafting_tome_line, ch);
		if (plan.low_material_count)
			snprintf(text, sizeof text,
				 "To %s this item, you will need %d of %s and %d of %s.\r\n&n",
				 d.verb, plan.high_material_count, high->short_description,
				 plan.low_material_count, low->short_description);
		else
			snprintf(text, sizeof text,
				 "To %s this item, you will need %d of %s.\r\n&n", d.verb,
				 plan.high_material_count, high->short_description);
		send_to_char(text, ch);
		if (plan.magical)
			send_to_char(
				"...as well as &+W1 &nof &+ma &+Mm&+Ya&+Mg&+Yi&+Mc&+Ya&+Ml &+messence&n due to the &+mmagical &nproperties this item possesses.\r\n",
				ch);
		send_to_char(d.tool_needed, ch);
		if (d.takes_stone)
			send_to_char(
				"You may add a strange stone too: `craft make <number> <stone>` gives the item the stone's magic.\r\n",
				ch);
	}
	if (low)
		extract_obj(low);
	if (high)
		extract_obj(high);
}

/* Finds the stone named for a make, or explains why it can't be used. */
bool crafting_find_stone(P_char ch, const crafting_discipline &d, const char *name, P_obj target,
			 P_obj *stone)
{
	*stone = NULL;
	if (!*name)
		return true;
	if (!d.takes_stone)
	{
		send_to_char("Only Craft can work a stone's magic into an item.\r\n", ch);
		return false;
	}
	P_obj found = get_obj_in_list_vis(ch, name, ch->carrying);
	if (!found)
	{
		send_to_char("You aren't carrying that stone.\r\n", ch);
		return false;
	}
	if (!crafting_is_stone(found))
	{
		act("$p holds no magic you can craft with.", FALSE, ch, found, 0, TO_CHAR);
		return false;
	}
	if (!crafting_stone_adds_magic(found, target))
	{
		act("$p would add nothing to $P.", FALSE, ch, found, target, TO_CHAR);
		return false;
	}
	*stone = found;
	return true;
}

/* Removes exactly what the plan charges; the pouch stands in for materials. */
void crafting_consume_inputs(P_char ch, const crafting_discipline &d, const crafting_plan &plan,
			     bool chaos_pouch, P_obj made, P_obj stone)
{
	int low = chaos_pouch ? 0 : plan.low_material_count;
	int high = chaos_pouch ? 0 : plan.high_material_count;
	bool essence = plan.magical;
	bool tool = true;
	P_obj next;
	for (P_obj obj = ch->carrying; obj; obj = next)
	{
		next = obj->next_content;
		if (obj == made)
			continue;
		const int vnum = OBJ_VNUM(obj);
		if (low > 0 && vnum == plan.low_material_vnum)
			low--;
		else if (high > 0 && vnum == plan.high_material_vnum)
			high--;
		else if (essence && vnum == crafting_essence_vnum(d.mode))
			essence = false;
		else if (tool && vnum == crafting_tool_vnum(d.mode))
			tool = false;
		else
			continue;
		extract_obj(obj, TRUE);
	}
	if (stone)
		extract_obj(stone, TRUE);
}

/* Takes ownership of target: it is delivered on success and discarded otherwise. */
void crafting_make(P_char ch, const crafting_discipline &d, P_obj target, const char *stone_name)
{
	struct crafting_plan plan;
	if (!crafting_build_plan(target, &plan))
	{
		send_to_char(crafting_unknown_materials, ch);
		extract_obj(target);
		return;
	}
	if (plan.item_value > crafting_value_limit(ch))
	{
		char text[MAX_STRING_LENGTH];
		snprintf(text, sizeof text,
			 "You need level %d to %s this recipe (you are level %d).\r\n",
			 1 + (plan.item_value - 1) / crafting_level_gate_multiplier(), d.verb,
			 GET_LEVEL(ch));
		send_to_char(text, ch);
		extract_obj(target);
		return;
	}
	P_obj stone;
	if (!crafting_find_stone(ch, d, stone_name, target, &stone))
	{
		extract_obj(target);
		return;
	}

	const bool chaos_pouch = chaos_material_pouch_available(ch);
	int low = 0, high = 0, essences = 0, tools = 0;
	for (P_obj obj = ch->carrying; obj; obj = obj->next_content)
	{
		const int vnum = OBJ_VNUM(obj);
		if (vnum == plan.low_material_vnum)
			low++;
		else if (vnum == plan.high_material_vnum)
			high++;
		else if (vnum == crafting_essence_vnum(d.mode))
			essences++;
		else if (vnum == crafting_tool_vnum(d.mode))
			tools++;
	}
	const char *missing = NULL;
	if (!chaos_pouch && (low < plan.low_material_count || high < plan.high_material_count))
		missing =
			"You do not have the required &+ysalvaged &+Ymaterials &nin your inventory.\r\n";
	else if (tools < 1)
		missing = d.tool_missing;
	else if (plan.magical && essences < 1)
		missing =
			"You must have &+W1 &nof &+ma &+Mm&+Ya&+Mg&+Yi&+Mc&+Ya&+Ml &+messence&n due to the &+mmagical &nproperties this item possesses.\r\n";
	if (missing)
	{
		send_to_char(missing, ch);
		extract_obj(target);
		return;
	}

	const chaos_material_pouch_usage generated[] = {
		{ plan.low_material_vnum, static_cast<uint64_t>(plan.low_material_count) },
		{ plan.high_material_vnum, static_cast<uint64_t>(plan.high_material_count) },
	};
	if (chaos_pouch &&
	    !chaos_material_pouch_can_record_generated(ch, generated, ARRAY_SIZE(generated)))
	{
		chaos_material_pouch_report_generated_failure(ch, d.verb);
		extract_obj(target);
		return;
	}

	SET_BIT(target->extra2_flags, ITEM2_CRAFTED);
	SET_BIT(target->extra_flags, ITEM_NOREPAIR);
	set_obj_extra_flags(target, target->extra_flags & ~(ITEM_SECRET));
	if (stone)
		crafting_apply_stone(target, stone);
	char text[MAX_STRING_LENGTH];
	snprintf(text, sizeof text, "%s %s tradeskill", target->name, GET_NAME(ch));
	set_keywords(target, text);
	snprintf(text, sizeof text, "%s &+ymade by&n &+r%s&n", target->short_description,
		 GET_NAME(ch));
	set_short_description(target, text);

	// Deliver and record the pouch first; inputs go only once both have succeeded,
	// and the single save below writes the output and the removed inputs together.
	if (!grant_crafted_item(ch, target))
		return;
	if (chaos_pouch &&
	    !chaos_material_pouch_record_generated(ch, generated, ARRAY_SIZE(generated)))
	{
		extract_obj(target);
		chaos_material_pouch_report_generated_failure(ch, d.verb);
		return;
	}

	act(d.work_to_room, TRUE, ch, target, 0, TO_ROOM);
	act(d.work_to_char, FALSE, ch, target, 0, TO_CHAR);
	if (stone)
	{
		act("$n sets $p into $s work, and its magic flows into $P.", TRUE, ch, stone,
		    target, TO_ROOM);
		act("You set $p into your work, and its magic flows into $P.", FALSE, ch, stone,
		    target, TO_CHAR);
	}
	const int stone_vnum = stone ? OBJ_VNUM(stone) : 0;
	crafting_consume_inputs(ch, d, plan, chaos_pouch, target, stone);

	notch_skill(ch, d.skill, 50);
	wizlog(56, "%s %s '%s' (%d) ival %d, stone %d.", GET_NAME(ch), d.past,
	       target->short_description, OBJ_VNUM(target), itemvalue(target), stone_vnum);
	crafting_award_experience(ch, plan);
	if (!do_save_silent(ch, 1))
		logit(LOG_DEBUG, "Failed to save %s after %s.", GET_NAME(ch), d.verb);
}
} // namespace

/* `craft` and `forge`: list, info <n>, stat <n> and make <n> [stone]. A recipe
 * is chosen by its list number or its vnum. */
void crafting_handle_command(P_char ch, enum crafting_mode mode, char *argument)
{
	const crafting_discipline &d = mode == CRAFTING_MODE_CRAFT ? craft_discipline :
								     forge_discipline;
	char text[MAX_STRING_LENGTH];

	if (!crafting_mode_enabled(mode))
	{
		send_to_char("That crafting discipline is currently unavailable.\r\n", ch);
		return;
	}
	if (!GET_CHAR_SKILL(ch, d.skill))
	{
		send_to_char(d.not_learned, ch);
		return;
	}

	char sub[MAX_INPUT_LENGTH], number[MAX_INPUT_LENGTH], stone[MAX_INPUT_LENGTH];
	argument = one_argument(argument, sub);
	argument = one_argument(argument, number);
	one_argument(argument, stone);

	int recipe_count = 0;
	int *recipes = crafting_get_player_recipes(ch, &recipe_count);
	if (!recipes || recipe_count == 0)
	{
		snprintf(
			text, sizeof text,
			"You do not know any %s recipes yet. Learn a recipe, then type `%s` to list it.\r\n",
			d.title, d.verb);
		send_to_char(text, ch);
		free(recipes);
		return;
	}
	if (!*sub || is_abbrev(sub, "list"))
	{
		crafting_show_recipes(ch, d, recipes, recipe_count);
		free(recipes);
		return;
	}

	const bool info = is_abbrev(sub, "info"), stat = is_abbrev(sub, "stat"),
		   make = is_abbrev(sub, "make");
	if (!info && !stat && !make)
	{
		snprintf(text, sizeof text,
			 "Unknown %s command. Use `%s` to list recipes and available commands.\r\n",
			 d.title, d.verb);
		send_to_char(text, ch);
		free(recipes);
		return;
	}
	int choice = 0;
	config_parse_int(number, choice);
	const int selected = crafting_select_recipe(recipes, recipe_count, choice);
	free(recipes);
	if (choice <= 0)
	{
		if (make)
			snprintf(text, sizeof text, "What &+Witem&n are you attempting to %s?\r\n",
				 d.verb);
		else
			snprintf(text, sizeof text,
				 "What &+Wrecipe&n would you like &+y%s&n about?\r\n",
				 info ? "information" : "statistics");
		send_to_char(text, ch);
		return;
	}
	if (!selected)
	{
		send_to_char("You dont appear to have that &+Wrecipe&n in your list.&n\r\n", ch);
		return;
	}

	P_obj target = read_object(selected, VIRTUAL);
	if (!target)
	{
		logit(LOG_DEBUG, "%s: '%s' has bad recipe vnum %d.", d.verb, J_NAME(ch), selected);
		send_to_char("That recipe seems to be &+rcorrupted&n. Please tell a &+WGod&n.\r\n",
			     ch);
		return;
	}
	if (make)
	{
		crafting_make(ch, d, target, stone);
		return;
	}
	if (info)
		crafting_show_info(ch, d, target);
	else
	{
		send_to_char(crafting_tome_line, ch);
		spell_identify(GET_LEVEL(ch), ch, 0, 0, 0, target);
	}
	extract_obj(target);
}
