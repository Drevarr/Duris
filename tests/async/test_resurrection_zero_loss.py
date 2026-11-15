#!/usr/bin/env python3
"""Execute resurrection's XP refund and carried-item transfer blocks."""
from pathlib import Path
import subprocess
import tempfile

from _paths import source

function = source('magic.c').read_text().split('bool resurrect_corpse(', 1)[1]
start = function.index('\t/*\n\t * restore lost exp from death')
block = function[start:function.index('\n\tGET_HIT(t_ch)', start)]
prelude = r'''
#include <algorithm>
#include <cassert>
struct Character { bool pc = true, trusted = false, evil = false; int level = 29; long xp = 12345; };
struct Object { long value[8]{}; };
#define IS_PC(ch) ((ch)->pc)
#define IS_TRUSTED(ch) ((ch)->trusted)
#define EVIL_RACE(ch) ((ch)->evil)
#define GET_LEVEL(ch) ((ch)->level)
#define GET_NAME(ch) "ResurrectionFixture"
#define GET_EXP(ch) ((ch)->xp)
constexpr int LOG_EXP = 0, EXP_RESURRECT = 1, EXPMOD_RES_EVIL = 0, EXPMOD_RES_NORMAL = 1;
double exp_mods[] = {.7, .8};
int calls = 0, alerts = 0;
long restored = -1;
void logit(int, const char*, ...) {}
void debug(const char*, ...) {}
void wizlog(int, const char*, ...) { ++alerts; }
void gain_exp(Character *ch, void*, long amount, int type) {
    assert(type == EXP_RESURRECT);
    ++calls; restored = amount;
    // The real dispatcher floors this gain at one; the caller must avoid it
    // when a death lost nothing rather than inventing refundable XP.
    ch->xp += std::max(1L, amount);
}
void refund(Character *t_ch, Character *ch, Object *obj) {
    long resu_exp;
'''
cases = r'''
}
int main() {
    for (int level : {1, 29, 30, 56})
        for (bool evil : {false, true})
            for (bool trusted_caster : {false, true}) {
                Character player, caster;
                Object corpse;
                player.level = level; player.evil = evil; caster.trusted = trusted_caster;
                calls = alerts = 0;
                refund(&player, &caster, &corpse);
                assert(player.xp == 12345 && calls == 0 && alerts == 0);
                corpse.value[4] = 100;
                refund(&player, &caster, &corpse);
                const long expected = trusted_caster ? 100 : level >= 56 ? 50 : evil ? 70 : 80;
                assert(calls == 1 && restored == expected && player.xp == 12345 + expected);
                assert(alerts == 0);
            }
    // Preserve the existing nonzero-corpse rounding/minimum-XP behavior.
    Character player, caster;
    Object corpse; corpse.value[4] = 1;
    calls = 0; refund(&player, &caster, &corpse);
    assert(calls == 1 && restored == 0 && player.xp == 12346);
}
'''
inventory_start = function.index('\t\tfor (t_obj = t_ch->carrying;')
inventory_block = function[inventory_start:function.index('\n\t\t/*', inventory_start)]
inventory = r'''
#include <cassert>
#include <cstddef>
#include <initializer_list>
struct Object { int extra_flags = 0; Object *next_content = nullptr; bool destroyed = false, dropped = false; };
struct Character { Object *carrying; int in_room = 1; };
constexpr int ITEM_TRANSIENT = 1, TRUE = 1;
#define IS_SET(flags, bit) ((flags) & (bit))
void extract_obj(Object *obj, int) { obj->destroyed = true; }
void obj_from_char(Object *) {}
void obj_to_room(Object *obj, int) { obj->dropped = true; }
void transfer(Character *t_ch, [[maybe_unused]] Object *obj) {
    Object *t_obj, *next_obj;
''' + inventory_block + r'''
}
int main() {
    for (int corpse_flags : {0, ITEM_TRANSIENT}) {
        Object ordinary, transient, corpse;
        transient.extra_flags = ITEM_TRANSIENT; ordinary.next_content = &transient;
        corpse.extra_flags = corpse_flags;
        Character owner{&ordinary};
        transfer(&owner, &corpse);
        assert(ordinary.dropped && !ordinary.destroyed);
        assert(transient.destroyed && !transient.dropped);
    }
}
'''
coin_start = source('magic.c').read_text().index('static void resurrect_coin_pile(')
coin_text = source('magic.c').read_text()[coin_start:]
coin_block = coin_text[:coin_text.index('\n}\n') + 3]
coins = r'''
#include <cassert>
#include <climits>
struct Object { int value[8]{}; bool destroyed = false, carried = false; };
struct Character { long long wallet = 0; };
using P_char = Character *;
using P_obj = Object *;
void ADD_MONEY(Character *ch, int amount) { assert(amount >= 0); ch->wallet += amount; }
void extract_obj(Object *obj) { obj->destroyed = true; }
void obj_to_char(Object *obj, Character *) { obj->carried = true; }
''' + coin_block + r'''
int main() {
    Character player;
    Object small; small.value[0] = 5; small.value[3] = 7;
    resurrect_coin_pile(&player, &small);
    assert(player.wallet == 7005 && small.destroyed && !small.carried);
    // 3,000,000 platinum is past INT_MAX copper: the pile must survive, not vanish.
    Object large; large.value[3] = 3000000;
    resurrect_coin_pile(&player, &large);
    assert(player.wallet == 7005 && large.carried && !large.destroyed);
}
'''
with tempfile.TemporaryDirectory(prefix='duris-resurrection-zero-') as temporary:
    root = Path(temporary)
    for name, code in [('refund', prelude + block + cases), ('inventory', inventory), ('coins', coins)]:
        source, binary = root / f'{name}.cpp', root / name
        source.write_text(code)
        subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie',
                        str(source), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
print('resurrection refunds remain correct; only transient carried items are destroyed; '
      'corpse coins are credited or kept, never lost')
