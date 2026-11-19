#!/usr/bin/env python3
"""A new character sees each first-find tip once; older characters never do."""
from pathlib import Path
import subprocess
import tempfile

from _paths import ROOT, HARNESS_STUBS

HARNESS = r'''
#include "player/first_find_tips.c"

#include <cassert>
#include <cstring>
#include <regex>

index_data prototypes[64];
P_index obj_index = prototypes;
std::string output;
int dirty_marks = 0;
bool named = false;

void send_to_char(const char *text, P_char) { output += text; }
void mark_player_dirty_components(int, player_component_mask_t) { ++dirty_marks; }
named_set_identity named_set_origin(const obj_data *) { return { named ? 3000 : 0, {} }; }
bool isname(const char *word, const char *list)
{
    return list && std::strstr(list, word);
}

static size_t visible(const std::string &text)
{
    return std::regex_replace(text, std::regex("&[+-][A-Za-z]|&[nN]"), "").size();
}

static obj_data item(int vnum, const char *name = "thing")
{
    static int next = 0;
    obj_data object{};
    prototypes[next].virtual_number = vnum;
    object.R_num = next++;
    object.name = const_cast<char *>(name);
    return object;
}

int main()
{
    for (const auto &tip : tips)
    {
        for (const char *art : tip.art)
            assert(visible(art) == 9);
        for (const char *text : tip.text)
            assert(visible(text) <= 56);
    }

    struct { int vnum; const char *name; int kind; } cases[] = {
        { VOBJ_RANDOM_ARMOR, "random", RANDOM_GEAR },
        { VOBJ_RANDOM_WEAPON, "random", RANDOM_GEAR },
        { LOWEST_MAT_VNUM, "material", SALVAGE_MATERIAL },
        { HIGHEST_MAT_VNUM, "material", SALVAGE_MATERIAL },
        { ENCRUST_VNUM_BEGIN, "stone", ENCRUST_STONE },
        { ENCRUST_VNUM_END, "stone", ENCRUST_STONE },
        { SALVAGE_RECIPE_VNUM, "recipe", RECIPE },
        { MAG_ESSENCE_VNUM, "essence", MAGICAL_ESSENCE },
        { 400238, "essence", ENHANCEMENT_ESSENCE },
        { 400258, "essence", ENHANCEMENT_ESSENCE },
        { VOBJ_SOUL_SHARD, "shard", SOUL_SHARD },
        { VOBJ_DRAGON_SCALE, "scale", DRAGON_SCALE },
        { 400260, "iron ore _ore_", ORE },
        { 194, "old iron ore _ore_", ORE },
        { 504, "topaz _ore_ _gem_", GEM },
        { 293, "bass fish _fishing_", FISH },
        { VOBJ_FORAGE_FIRST, "grub _frg_", FORAGE },
        { VOBJ_FORAGE_FIRST + VOBJ_FORAGE_NUM_TYPES - 1, "bone _frg_", FORAGE },
        { 3, "sword", -1 },
        { 400284, "shard", -1 },
    };
    for (const auto &probe : cases)
    {
        obj_data object = item(probe.vnum, probe.name);
        assert(tip_for(&object) == probe.kind);
    }
    obj_data gear = item(VOBJ_RANDOM_ARMOR, "random");
    named = true;
    assert(tip_for(&gear) == NAMED_GEAR);
    named = false;

    pc_only_data pc{};
    descriptor_data desc{};
    char_data ch{};
    ch.only.pc = &pc;
    ch.desc = &desc;
    STATE(&desc) = CON_PLAYING;
    obj_data shard = item(VOBJ_SOUL_SHARD, "shard");

    // A new character sees the tip once, with its title, and the bit is saved.
    first_find_tip(&ch, &shard);
    assert(output.find("First find: &+WEthereal Soul Shard") != std::string::npos);
    assert(pc.first_find_tips == uint64_t{ 1 } << SOUL_SHARD && dirty_marks == 1);
    const size_t top = output.find(".-"), bottom = output.find("'-");
    assert(visible(output.substr(top, output.find('\r', top) - top)) == 70);
    assert(visible(output.substr(bottom, output.find('\r', bottom) - bottom)) == 70);
    output.clear();
    first_find_tip(&ch, &shard);
    assert(output.empty() && dirty_marks == 1);

    // Other kinds still show; items without a tip change nothing.
    obj_data fish = item(293, "bass _fishing_");
    first_find_tip(&ch, &fish);
    assert(output.find("Fresh Fish") != std::string::npos && dirty_marks == 2);
    output.clear();
    obj_data sword = item(3, "sword");
    first_find_tip(&ch, &sword);
    assert(output.empty() && dirty_marks == 2);

    // Characters from before the tips, NPCs and players not in the game see nothing.
    pc.first_find_tips = FIRST_FIND_TIPS_ALL_SEEN;
    obj_data ore = item(400260, "ore _ore_");
    first_find_tip(&ch, &ore);
    assert(output.empty() && dirty_marks == 2);
    pc.first_find_tips = 0;
    STATE(&desc) = CON_PLAYING + 1;
    first_find_tip(&ch, &ore);
    ch.desc = nullptr;
    first_find_tip(&ch, &ore);
    ch.desc = &desc;
    STATE(&desc) = CON_PLAYING;
    SET_BIT(ch.specials.act, ACT_ISNPC);
    first_find_tip(&ch, &ore);
    assert(output.empty() && pc.first_find_tips == 0 && dirty_marks == 2);
    puts("first-find tips show once per kind to new characters only");
}
'''

if __name__ == '__main__':
    build = ROOT / 'bin/tests'
    build.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='first-find-tips-', dir=build) as temporary:
        source = Path(temporary) / 'harness.cpp'
        source.write_text(HARNESS)
        binary = Path(temporary) / 'harness'
        subprocess.run(['g++', '-std=c++20', '-g', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                        '-I', str(ROOT / 'src'), '-I/usr/include/mysql', '-I/usr/include/libxml2',
                        str(source), str(HARNESS_STUBS), '-lbsd', '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
