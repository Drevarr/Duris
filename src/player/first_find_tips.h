/****************************************************************************
 *
 *  File: first_find_tips.h                                     Part of Duris
 *  Usage: the one-time tip a new character sees on first finding each kind
 *         of random drop or crafting item
 *
 *  Additions since 2025 by the Duris maintainers and since 2026 by
 *    LuminariMUD maintainers are public domain (Unlicense, see LICENSE)
 *
 ****************************************************************************/

#ifndef FIRST_FIND_TIPS_H
#define FIRST_FIND_TIPS_H

#include <cstdint>

struct char_data;
struct obj_data;

// Characters that existed before the tips have every bit set, so they never see them.
constexpr uint64_t FIRST_FIND_TIPS_ALL_SEEN = ~uint64_t{ 0 };

// Show ch the tip for this item's kind, once per character.
void first_find_tip(char_data *ch, const obj_data *object);

#endif
