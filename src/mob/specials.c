/*
 ***************************************************************************
 *  File: specials.c                                         Part of Duris *
 *  Usage: support functions for special procedures                          *
 *  Copyright  1990, 1991 - see 'license.doc' for complete information.      *
 *  Copyright 1994 - 2008 - Duris Systems Ltd.                             *
 ***************************************************************************
 */

#include "core/prototypes.h"
#include "core/structs.h"
#include "net/comm.h"
#include "world/db.h"
#include "world/events.h"
#include "cmd/interp.h"
#include "core/utils.h"
#include <stdio.h>
#include <strings.h>
#include "combat/damage.h"
#include "world/map.h"
#include "magic/spells.h"

/*
   external variables
 */

extern P_index mob_index;
extern P_index obj_index;
extern P_obj object_list;
extern P_room world;
extern struct message_list fight_messages[MAX_MESSAGES];
extern struct zone_data *zone_table;
extern struct str_app_type str_app[];

P_nevent get_scheduled(P_char ch, event_func func);

/*
   handle EVENT_FIRE_PLANE events.
   called from various places to start things, and from Events to schedule
   the next one.
 */
void event_firesector(P_char ch, P_char /*victim*/, P_obj /*obj*/, void * /*data*/)
{
	struct affected_type *af, *next;

	if (IS_TRUSTED(ch) || ch->in_room == NOWHERE ||
	    ((world[ch->in_room].sector_type != SECT_FIREPLANE) &&
	     (world[ch->in_room].sector_type != SECT_LAVA) &&
	     (world[ch->in_room].sector_type != SECT_UNDRWLD_LIQMITH)))
		return;

	if (ENJOYS_FIRE_DAM(ch))
	{
		if (GET_HIT(ch) < GET_MAX_HIT(ch))
		{
			GET_HIT(ch) += 3;
			add_event(event_firesector, 3, ch, 0, 0, 0, 0, 0);
		}
		return;
	}

	if (IS_AFFECTED(ch, AFF_PROT_FIRE))
	{
		for (af = ch->affected; af; af = next)
		{
			next = af->next;
			if (af->type == SPELL_PROTECT_FROM_FIRE || af->type == SPELL_FIRE_WARD)
			{
				send_to_char(
					"Your feeble spell is no match for elemental fire!\r\n",
					ch);
				affect_remove(ch, af);
			}
		}
		return;
	}

	if (GET_HIT(ch) < -7)
	{
		send_to_char(
			"Failing to bear the &+Reternal heat&n of this place, your body is devoured by &+Yflames&n..\r\n",
			ch);
		act("Failing to bear the &+Reternal heat&n of this place, $n's body is devoured by &+Yflames&n..",
		    FALSE, ch, 0, 0, TO_ROOM);
		die(ch, ch);
		return;
	}
	else
	{
		GET_HIT(ch) -= 3;
		StartRegen(ch, regen_resource::hit);
		// Doesn't matter if PC, if they have a descriptor, show the burn!
		if (ch->desc)
			ch->desc->prompt_mode = TRUE;
	}

	add_event(event_firesector, 3, ch, 0, 0, 0, 0, 0);
}

void firesector(P_char ch)
{
	if (IS_TRUSTED(ch) || GET_RACE(ch) == RACE_F_ELEMENTAL || ch->in_room == NOWHERE ||
	    (IS_NPC(ch) && !IS_PC_PET(ch)) ||
	    ((world[ch->in_room].sector_type != SECT_FIREPLANE) &&
	     (world[ch->in_room].sector_type != SECT_LAVA) &&
	     (world[ch->in_room].sector_type != SECT_UNDRWLD_LIQMITH)))
		return;

	if (!get_scheduled(ch, event_firesector))
		add_event(event_firesector, 3, ch, 0, 0, 0, 0, 0);
}

// Ends holding breath and drowning for a character who has reached air, and tells
// them so if either was happening. Room entry calls it first; the breath event
// covers anything else.
void breathe_air(P_char ch)
{
	if (!IS_AFFECTED2(ch, AFF2_HOLDING_BREATH) && !IS_AFFECTED2(ch, AFF2_IS_DROWNING))
		return;
	REMOVE_BIT(ch->specials.affected_by2, AFF2_HOLDING_BREATH);
	REMOVE_BIT(ch->specials.affected_by2, AFF2_IS_DROWNING);
	send_to_char("&+BYou gasp as fresh air fills your lungs.&n\r\n", ch);
}

void event_underwatersector(P_char ch, P_char /*victim*/, P_obj /*obj*/, void * /*data*/)
{
	if (IS_AFFECTED(ch, AFF_WATERBREATH) || (ch->in_room == -1) || !IS_UNDERWATER(ch))
	{
		if (ch->in_room != -1 && !IS_UNDERWATER(ch))
			breathe_air(ch);
		REMOVE_BIT(ch->specials.affected_by2, AFF2_HOLDING_BREATH);
		REMOVE_BIT(ch->specials.affected_by2, AFF2_IS_DROWNING);
		return;
	}

	if (IS_AFFECTED2(ch, AFF2_IS_DROWNING))
	{
		if (GET_HIT(ch) < 0)
		{
			send_to_char(
				"Failing to hold your breath any second longer, you draw an airless breath..\r\n",
				ch);
			act("Failing to hold $s breath any second longer, $n draws an airless breath..",
			    FALSE, ch, 0, 0, TO_ROOM);
			die(ch, ch);
			return;
		}
		else
		{
			GET_HIT(ch) -= 3;
			StartRegen(ch, regen_resource::hit);
		}

		if (ch->desc)
			ch->desc->prompt_mode = TRUE;
	}
	else if (IS_AFFECTED2(ch, AFF2_HOLDING_BREATH))
	{
		send_to_char("&+BYour lungs begin to burn!&n\r\n", ch);
		REMOVE_BIT(ch->specials.affected_by2, AFF2_HOLDING_BREATH);
		SET_BIT(ch->specials.affected_by2, AFF2_IS_DROWNING);
	}
	else
	{
		SET_BIT(ch->specials.affected_by2, AFF2_HOLDING_BREATH);
		send_to_char("&+BYou begin to hold your breath...&n\r\n", ch);
		add_event(event_underwatersector, 3 * GET_C_CON(ch), ch, 0, 0, 0, 0, 0);
		return;
	}

	add_event(event_underwatersector, 3, ch, 0, 0, 0, 0, 0);
}

void underwatersector(P_char ch)
{
	if ((IS_NPC(ch) && !IS_PC_PET(ch)) || !IS_UNDERWATER(ch) || IS_TRUSTED(ch) ||
	    IS_AFFECTED(ch, AFF_WATERBREATH))
		return;

	if (!get_scheduled(ch, event_underwatersector))
		add_event(event_underwatersector, 3, ch, 0, 0, 0, 0, 0);
}

void swimming_char(P_char ch)
{
	if (!ch)
	{
		logit(LOG_DEBUG, "NULL ch in call to swimming_char");
		return;
	}

	return;
	if (IS_TRUSTED(ch) || IS_NPC(ch) || ch->specials.z_cord > 0 ||
	    IS_AFFECTED(ch, AFF_LEVITATE) || IS_AFFECTED(ch, AFF_FLY) ||
	    !IS_MAP_ROOM(ch->in_room) || (ch->in_room == NOWHERE) || !IS_WATER_ROOM(ch->in_room))
	{
		REMOVE_BIT(ch->specials.affected_by3, AFF3_SWIMMING);
		REMOVE_BIT(ch->specials.affected_by2, AFF2_IS_DROWNING);
		REMOVE_BIT(ch->specials.affected_by2, AFF2_HOLDING_BREATH);

		return;
	}

	if (GET_STAT(ch) == STAT_DEAD)
	{
		logit(LOG_EXIT, "assert: dead char in call to swimming_char");
		return;
	}

	/*  if (current_event && (current_event->type == EVENT_SWIMMING)) {
	      if (GET_VITALITY(ch) < 1) {
	    if (IS_WATER_ROOM(ch->in_room)) {
	          ch->specials.z_cord = -1;
	          underwatersector(ch);
	          REMOVE_BIT(ch->specials.affected_by3, AFF3_SWIMMING);
	        }
	      } else {
	    GET_VITALITY(ch) -= (4 - (BOUNDED(0, (GET_CHAR_SKILL(ch, SKILL_SWIM) / 25), 4)));
	      }
	      if( ch->desc )
	    ch->desc->prompt_mode = TRUE;

	      StartRegen(ch, regen_resource::vitality);
	  } else {
	    FIND_EVENT_TYPE(e1, EVENT_SWIMMING)
	    if (ch == (P_char) e1->actor.a_ch)
	      return;
	  }

	    if (!IS_AFFECTED3(ch, AFF3_SWIMMING) && !IS_AFFECTED2(ch, AFF2_HOLDING_BREATH)
	    && !IS_AFFECTED2(ch, AFF2_IS_DROWNING)) {
	      SET_BIT(ch->specials.affected_by3, AFF3_SWIMMING);
	      send_to_char("&+BYou begin to swim...&n\r\n", ch);
	    }

	  if (ch->in_room == NOWHERE || !IS_WATER_ROOM(ch->in_room)) {
	    if (IS_AFFECTED2(ch, AFF2_HOLDING_BREATH))
	      REMOVE_BIT(ch->specials.affected_by2, AFF2_HOLDING_BREATH);
	    if (IS_AFFECTED2(ch, AFF2_IS_DROWNING))
	      REMOVE_BIT(ch->specials.affected_by2, AFF2_IS_DROWNING);
	    if (IS_AFFECTED3(ch, AFF3_SWIMMING))
	      REMOVE_BIT(ch->specials.affected_by3, AFF3_SWIMMING);
	    return;

	  }

	  swim_timer = GET_C_CON(ch) / 5;
	  AddEvent(EVENT_SWIMMING, swim_timer, TRUE, ch, 0);*/
}

long pow10(long x)
{
	int y = 1;

	while (x-- > 0)
		y *= 10;

	return y;
}

void npc_steal(P_char ch, P_char vict)
{
	if (!IS_ALIVE(ch) || !IS_ALIVE(vict) || IS_NPC(vict) || IS_PC_PET(ch))
	{
		return;
	}

	if (ch->in_room == NOWHERE || ch->in_room != vict->in_room)
	{
		return;
	}

	// Teachers don't steal.
	if (IS_SET(ch->specials.act, ACT_TEACHER) || IS_SET(ch->specials.act, ACT_SPEC_TEACHER))
	{
		return;
	}

	if (IS_TRUSTED(vict) || IS_ROOM(ch->in_room, ROOM_SAFE) || CHAR_IN_SAFE_ROOM(ch))
	{
		return;
	}

	if (IS_FIGHTING(ch) || IS_FIGHTING(vict) ||
	    (IS_ROOM(ch->in_room, ROOM_SINGLE_FILE) && !AdjacentInRoom(ch, vict)))
	{
		return;
	}

	// NPC theft is disabled; treat thief procs as harmless flavor emotes.
	if (!number(0, 1))
	{
		act("&+WHey! $n just tried to steal something from you!&n", FALSE, ch, 0, vict,
		    TO_VICT);
		act("$n just tried to steal something from $N!", TRUE, ch, 0, vict, TO_NOTVICT);
	}
	else
	{
		act("You discover that $n has $s hands in your wallet.", FALSE, ch, 0, vict,
		    TO_VICT);
		act("$n tries to steal gold from $N.", TRUE, ch, 0, vict, TO_NOTVICT);
	}
}

/* Pi's room proc */

P_obj find_key(P_char ch, int key)
{
	P_obj o, tar_obj = NULL;

	if (!has_key(ch, key))
		return (0);

	for (o = ch->carrying; o; o = o->next_content)
		if (obj_index[o->R_num].virtual_number == key)
			tar_obj = o;
	if (ch->equipment[HOLD])
		if (obj_index[ch->equipment[HOLD]->R_num].virtual_number == key)
			tar_obj = ch->equipment[HOLD];
	return (tar_obj);
}

/**
 * For negative plane events, similar to event_firesector. -Keja
 */
void event_negsector(P_char ch, P_char /*victim*/, P_obj /*obj*/, void * /*data*/)
{
	struct affected_type *af, *next;

	if (IS_TRUSTED(ch) || GET_RACE(ch) == RACE_UNDEAD || ch->in_room == NOWHERE ||
	    ((world[ch->in_room].sector_type != SECT_NEG_PLANE)))
		return;

	if (IS_AFFECTED5(ch, AFF5_PROT_UNDEAD))
	{
		for (af = ch->affected; af; af = next)
		{
			next = af->next;
			if (af->type == SPELL_PROT_FROM_UNDEAD)
			{
				send_to_char(
					"Your feeble spell is no match for the negative energy!\r\n",
					ch);
				affect_remove(ch, af);
			}
		}
		return;
	}

	if (GET_HIT(ch) < 0)
	{
		send_to_char("&+LYou gasp as you realize your lifeforce has run out!&n.\r\n", ch);
		act("$n&+L collapses in a crumpled heap, as their body shrivels into nothing.\r\n",
		    FALSE, ch, 0, 0, TO_ROOM);
		die(ch, ch);
		return;
	}
	else
	{
		GET_HIT(ch) -= 3;
		StartRegen(ch, regen_resource::hit);
		if (ch->desc)
			ch->desc->prompt_mode = TRUE;
	}

	add_event(event_negsector, 3, ch, 0, 0, 0, 0, 0);
}

void negsector(P_char ch)
{
	if (IS_TRUSTED(ch) || GET_RACE(ch) == RACE_UNDEAD || ch->in_room == NOWHERE ||
	    (IS_NPC(ch) && !IS_PC_PET(ch)) || ((world[ch->in_room].sector_type != SECT_NEG_PLANE)))
		return;

	if (!get_scheduled(ch, event_negsector))
		add_event(event_negsector, 3, ch, 0, 0, 0, 0, 0);
}
