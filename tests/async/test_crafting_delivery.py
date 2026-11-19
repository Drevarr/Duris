#!/usr/bin/env python3
"""Craft/Forge command failures preserve exact material, essence, tool and stone UIDs."""
from pathlib import Path
import subprocess
import tempfile
from _paths import ROOT, HARNESS_STUBS, extract_function

HARNESS = r'''
#include "economy/crafting.c"
#include <cassert>
#include <unordered_map>
#include <unordered_set>

static index_data fixture_indices[512]{};
P_index obj_index = fixture_indices;
static obj_data fixture_prototypes[512]{};
static std::unordered_map<int,int> fixture_rnums;
static std::unordered_set<P_obj> live;
static std::unordered_set<uint64_t> removed;
static P_obj active_pouch;
static bool refuse_delivery, refuse_preflight, refuse_ledger;
static int unavailable_vnum, target_vnum, saves, notches, experience;
static uint64_t next_uid, delivered_uid, generated_count;

int GET_CHAR_SKILL_P(P_char,int) { return 100; }
bool is_salvageable(P_obj) { return true; }
int itemvalue(P_obj obj) { return obj->cost; }
int get_matstart(P_obj) { return 400000; }
void logit(const char *,const char *,...) {}
void wizlog(int,const char *,...) {}
static size_t longest_write, listed;
void send_to_char(const char *text,P_char) {
    longest_write=std::max(longest_write,strlen(text));
    for(const char *at=text; (at=strstr(at,"fixture item")); ++at) ++listed;
}
void act(const char *,int,P_char,P_obj,void *,int) {}
bool notch_skill(P_char,int,float) { ++notches; return true; }
int gain_exp(P_char,P_char,int amount,int) { experience+=amount; return amount; }
void set_keywords(P_obj,const char *) {}
void set_short_description(P_obj,const char *) {}
void set_obj_extra_flags(P_obj obj,unsigned flags) { obj->extra_flags=flags; }
bool do_save_silent(P_char,int,player_save_pipeline_result *) { ++saves; return true; }
int fill_word(char *) { return 0; }
bool sql_add_player_recipe(int,int) { std::abort(); }
int real_object(int vnum) { return fixture_rnums.count(vnum) ? fixture_rnums.at(vnum) : -1; }
void page_string(P_desc,char *,int) { std::abort(); }
void spell_identify(int,P_char,char *,int,P_char,P_obj) { std::abort(); }
static int book_size; // Nonzero: a book of that many recipes from 90001 on.
int *sql_get_player_recipes(int,int *count) {
    *count=book_size ? book_size : 1;
    auto *recipes=static_cast<int *>(std::malloc(sizeof(int)*(*count)));
    for(int i=0;i<*count;++i) recipes[i]=book_size ? 90001+i : target_vnum;
    return recipes;
}
bool chaos_material_pouch_available(P_char) { return active_pouch!=nullptr; }
bool chaos_material_pouch_can_record_generated(P_char,const chaos_material_pouch_usage *,size_t) {
    return !refuse_preflight;
}
bool chaos_material_pouch_record_generated(P_char,const chaos_material_pouch_usage *usage,size_t count) {
    if(refuse_ledger) return false;
    for(size_t i=0;i<count;++i) generated_count+=usage[i].count;
    return true;
}
void chaos_material_pouch_report_generated_failure(P_char,const char *) {}
P_obj get_obj_in_list_vis(P_char,const char *name,P_obj list,bool) {
    for(P_obj obj=list; obj; obj=obj->next_content)
        if(strstr(obj->name,name)) return obj;
    return nullptr;
}
static P_obj live_uid(uint64_t uid) {
    for(P_obj obj : live) if(obj->obj_uid==uid) return obj;
    return nullptr;
}
static int fixture_index(int vnum) {
    auto found=fixture_rnums.find(vnum);
    assert(found!=fixture_rnums.end()); return found->second;
}
P_obj read_object(int vnum,int) {
    if(vnum==unavailable_vnum) return nullptr;
    auto *obj=new obj_data(fixture_prototypes[fixture_index(vnum)]);
    obj->obj_uid=next_uid++; obj->loc_p=LOC_NOWHERE; obj->next_content=nullptr;
    live.insert(obj); return obj;
}
void obj_from_char(P_obj obj) {
    assert(OBJ_CARRIED(obj));
    auto *link=&obj->loc.carrying->carrying;
    while(*link!=obj) { assert(*link); link=&(*link)->next_content; }
    *link=obj->next_content; obj->next_content=nullptr; obj->loc_p=LOC_NOWHERE;
}
void extract_obj(P_obj obj,int) {
    assert(obj && live.count(obj));
    if(OBJ_CARRIED(obj)) obj_from_char(obj);
    removed.insert(obj->obj_uid); live.erase(obj); delete obj;
}
bool obj_to_char(P_obj obj,P_char ch) {
    assert(live.count(obj) && OBJ_NOWHERE(obj));
    if(OBJ_VNUM(obj)==target_vnum && obj->obj_uid>=10000) {
        delivered_uid=obj->obj_uid;
        if(refuse_delivery) { extract_obj(obj,0); return false; }
    }
    obj->next_content=ch->carrying; ch->carrying=obj;
    obj->loc_p=LOC_CARRIED; obj->loc.carrying=ch; return true;
}
bool item_creation_grant_submit_to_player(P_char ch,P_obj obj,P_char,P_obj) {
    if(refuse_delivery) return false; // Refused admission leaves the detached object to its caller.
    return obj_to_char(obj,ch);
}
static void prototype(int vnum,bool magical=false) {
    if(fixture_rnums.count(vnum)) return;
    int index=fixture_rnums.size(); fixture_rnums[vnum]=index;
    fixture_indices[index].virtual_number=vnum;
    auto &obj=fixture_prototypes[index]; obj={}; obj.R_num=index; obj.type=ITEM_ARMOR;
    obj.cost=2; obj.wear_flags=ITEM_TAKE|ITEM_WEAR_BODY;
    obj.name=const_cast<char *>("fixture"); obj.short_description=const_cast<char *>("fixture item");
    obj.bitvector5=magical ? 1 : 0;
}
static uint64_t input(P_char ch,int vnum,uint64_t uid) {
    P_obj obj=read_object(vnum,VIRTUAL); obj->obj_uid=uid;
    assert(obj_to_char(obj,ch)); return uid;
}
int main() {
    for(auto mode : {CRAFTING_MODE_CRAFT,CRAFTING_MODE_FORGE}) {
        for(int failure : {1,0,2,3,4,5,6,8}) {
            char_data ch{}; pc_only_data pc{}; ch.only.pc=&pc; pc.pid=42;
            ch.player.level=50; ch.player.name=const_cast<char *>("Artisan");
            fixture_rnums.clear(); removed.clear(); next_uid=10; active_pouch=nullptr;
            target_vnum=failure==6 ? 400000 : 99001;
            prototype(target_vnum,true); prototype(400000); prototype(400004);
            prototype(crafting_essence_vnum(mode)); prototype(crafting_tool_vnum(mode));
            prototype(VOBJ_CHAOS_CRAFT_POUCH);
            input(&ch,400000,101); input(&ch,400004,102);
            input(&ch,crafting_essence_vnum(mode),103); input(&ch,crafting_tool_vnum(mode),104);
            const bool pouch=failure>=2 && failure<=4;
            if(pouch) { input(&ch,VOBJ_CHAOS_CRAFT_POUCH,105); active_pouch=ch.carrying; }
            next_uid=10000; delivered_uid=generated_count=0;
            saves=notches=experience=0;
            refuse_delivery=failure==1; refuse_preflight=failure==2; refuse_ledger=failure==3;
            unavailable_vnum=failure==5 ? target_vnum : failure==8 ? 400004 : 0;
            char make[]="make 1", info[]="info 1";
            char *command=failure==8 ? info : make;
            crafting_handle_command(&ch,mode,command);
            const bool success=failure==0 || failure==4 || failure==6;
            for(uint64_t uid : {101,102,103,104}) {
                const bool consumed=success && (!pouch || uid>=103);
                assert(removed.count(uid)==static_cast<size_t>(consumed));
            }
            if(success) {
                assert(delivered_uid && !removed.count(delivered_uid));
                assert(saves==1 && notches==1 && experience==2000);
                assert(live.size()==static_cast<size_t>(pouch ? 4 : 1));
                assert(generated_count==static_cast<uint64_t>(pouch ? 2 : 0));
            } else {
                assert(saves==0 && notches==0 && experience==0 && generated_count==0);
                assert(live.size()==static_cast<size_t>(pouch ? 5 : 4));
            }
            if(failure==4) assert(!removed.count(105));
            active_pouch=nullptr; refuse_delivery=false; unavailable_vnum=0;
            while(!live.empty()) extract_obj(*live.begin(),0);
        }
    }
    // A named strange stone gives the crafted item its affect bits and is used up
    // with the other inputs; any refusal keeps every input, the stone included.
    struct stone_case { crafting_mode mode; const char *command; bool adds, refuse, success; };
    for(const stone_case &c : {
        stone_case{CRAFTING_MODE_CRAFT,"make 1 strange",true,false,true},
        stone_case{CRAFTING_MODE_CRAFT,"make 1",true,false,true},          // a carried stone is left alone
        stone_case{CRAFTING_MODE_CRAFT,"make 1 strange",false,false,false}, // it would add nothing
        stone_case{CRAFTING_MODE_CRAFT,"make 1 fixture",true,false,false},  // not a stone
        stone_case{CRAFTING_MODE_CRAFT,"make 1 pebble",true,false,false},   // not carried
        stone_case{CRAFTING_MODE_FORGE,"make 1 strange",true,false,false},  // Forge takes no stone
        stone_case{CRAFTING_MODE_CRAFT,"make 1 strange",true,true,false},   // delivery refused
    }) {
        char_data ch{}; pc_only_data pc{}; ch.only.pc=&pc; pc.pid=42;
        ch.player.level=50; ch.player.name=const_cast<char *>("Artisan");
        fixture_rnums.clear(); removed.clear(); next_uid=10; active_pouch=nullptr;
        target_vnum=99001; unavailable_vnum=0;
        prototype(target_vnum,true); prototype(400000); prototype(400004);
        prototype(crafting_essence_vnum(c.mode)); prototype(crafting_tool_vnum(c.mode));
        prototype(ENCRUST_VNUM_BEGIN);
        auto &stone=fixture_prototypes[fixture_index(ENCRUST_VNUM_BEGIN)];
        stone.name=const_cast<char *>("strange stone");
        stone.bitvector2=c.adds ? AFF2_PROT_ACID : 0;
        stone.bitvector5=1; // the target already has this bit
        input(&ch,400000,101); input(&ch,400004,102);
        input(&ch,crafting_essence_vnum(c.mode),103); input(&ch,crafting_tool_vnum(c.mode),104);
        input(&ch,ENCRUST_VNUM_BEGIN,106);
        next_uid=10000; delivered_uid=generated_count=0; saves=notches=experience=0;
        refuse_delivery=c.refuse;
        std::string command=c.command;
        crafting_handle_command(&ch,c.mode,command.data());
        const bool named=strstr(c.command,"strange")!=nullptr;
        for(uint64_t uid : {101,102,103,104})
            assert(removed.count(uid)==static_cast<size_t>(c.success));
        assert(removed.count(106)==static_cast<size_t>(c.success && named));
        if(c.success) {
            P_obj made=live_uid(delivered_uid);
            assert(made && saves==1 && experience==2000);
            assert(((made->bitvector2&AFF2_PROT_ACID)!=0)==named);
        } else {
            assert(saves==0 && notches==0 && experience==0 && live.size()==5);
        }
        refuse_delivery=false;
        while(!live.empty()) extract_obj(*live.begin(),0);
    }
    // A large recipe book lists every recipe without any single write reaching the
    // output limit, which would drop the whole list.
    {
        char_data ch{}; pc_only_data pc{}; ch.only.pc=&pc; pc.pid=42; ch.player.level=50;
        fixture_rnums.clear(); prototype(400000); prototype(400004);
        book_size=400;
        for(int i=0;i<book_size;++i) prototype(90001+i,true);
        longest_write=listed=0;
        char list[]="list";
        crafting_handle_command(&ch,CRAFTING_MODE_CRAFT,list);
        assert(listed==static_cast<size_t>(book_size) && longest_write<MAX_STRING_LENGTH/16);
        book_size=0;
        while(!live.empty()) extract_obj(*live.begin(),0);
    }
    puts("Craft/Forge: exact input UIDs, failed delivery/ledger, output identity, stones and one checkpoint pass");
}
'''

(ROOT / 'bin/tests').mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='crafting-delivery-', dir=ROOT / 'bin/tests') as temporary:
    cpp = Path(temporary) / 'crafting.cpp'
    binary = Path(temporary) / 'crafting'
    parsing = '\n'.join(extract_function('interp.c', signature) for signature in (
        'char *one_argument(', 'bool is_abbrev(', 'void half_chop(',
    ))
    cpp.write_text(HARNESS + parsing)
    subprocess.run([
        'g++', '-std=c++20', '-g', '-O1', '-ffunction-sections', '-fdata-sections',
        '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-pie', '-no-pie',
        '-Isrc', '-I/usr/include/mysql', str(cpp), str(HARNESS_STUBS),
        'src/core/safe_format.c', 'src/item/item_value.c', '-Wl,--gc-sections', '-lbsd', '-lcrypto', '-o', str(binary),
    ], cwd=ROOT, check=True)
    subprocess.run([str(binary)], cwd=ROOT, check=True, timeout=30)
