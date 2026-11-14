import json
import os
import sys
from typing import Mapping
from bit_flags import *
from output_writer import *
from spells_skills import *
from tid_writer import *
from type_flags import *
from utilities import *


AREA_LIST = "AREA"
LOADED_AREAS = []
WORLD_OBJECTS = "tworld.obj"

#list of tid files to output
tid_list = []

def process_item_values(item_values, item_type):
    Item_Type_Notes={}
    
    match item_type:
        case "ITEM_WAND" | "ITEM_STAFF":
            spell_level = item_values[0] 
            max_charges = item_values[1]
            charges_left = item_values[2]
            spell_1 = spell_lookup.get(item_values[3], "")
            Item_Type_Notes = {
            "Spell": spell_1,
            "Level": spell_level,
            "Max Charges": max_charges,
            "Reamining Charges": charges_left
            }
            
        case "ITEM_SCROLL" | "ITEM_POTION":
            spell_level = item_values[0] 
            spell_1 = spell_lookup.get(item_values[1], "")
            spell_2 = spell_lookup.get(item_values[2], "")
            spell_3 = spell_lookup.get(item_values[3], "")
            Item_Type_Notes = {
            "Spell Level": spell_level,
            "Spells": f"{spell_1} {spell_2} {spell_3}"
            }

        case "ITEM_WEAPON":
            weapon_type = weapon_type_lookup.get(item_values[0], "")
            num_dice = item_values[1]
            size_dice = item_values[2]
            proc = item_values[5]
            proc_level = item_values[6]
            proc_pct = f"1/{item_values[7]}" if item_values[7] else None
            Item_Type_Notes = {
                "Type": weapon_type,
                "Damage": f"{num_dice}D{size_dice}",
                "Proc": proc,
                "Proc Level": proc_level,
                "Proc Chance": proc_pct
            }

        case "ITEM_MISSILE":
            to_hit_mod = item_values[0]
            num_dice = item_values[1]            
            size_dice = item_values[2]
            missile_type = missile_type_lookup.get(item_values[3], "")
            Item_Type_Notes = {
            "Missile Type": missile_type,
            "To Hit Mod": f"+{to_hit_mod}",
            "Damage": f"{num_dice}D{size_dice}"            
            }

        case "ITEM_ARMOR":
            armor_class = item_values[0]
            warmth = item_values[1]
            prestige = item_values[2]
            matl_type = material_type_lookup.get(item_values[3], "")
            Item_Type_Notes = {
            "Armor Class": armor_class,
            "Prestige": prestige,
            "Warmth": warmth,
            "Material Type": matl_type
            }

        case "ITEM_WORN":
            matl_type = material_type_lookup.get(item_values[3], "")
            Item_Type_Notes = {
            "Material Type": matl_type
            }
            
        case "ITEM_SHIELD":
            shield_type = shield_type_lookup.get(item_values[0], "")
            shield_shape = shield_shape_lookup.get(item_values[1], "")
            shield_size = shield_size_lookup.get(item_values[2], "")
            armor_class = item_values[3]
            shield_thick = item_values[4]
            misc_flag = "Spiked" if item_values[5] else "None"
            Item_Type_Notes = {
            "Armor Class": armor_class,
            "Misc Flag": misc_flag,
            "Shield Type": shield_type,
            "Shield Shape": shield_shape,
            "Shield Size": shield_size,
            "Shield Thickness": shield_thick
            }
            
        case "ITEM_CONTAINER" | "ITEM_STORAGE":
            holds = item_values[0]
            locktype = item_values[1] 
            key = item_values[2]
            size_hold = item_values[3]
            Item_Type_Notes = {
            "Max Hold Weight": holds,
            "Hold Size": size_hold,
            "Lock Type": locktype,
            "Key Vnum": key
            }

        case "ITEM_KEY":
            break_pct = item_values[1]
            Item_Type_Notes = {
            "Break Pct": break_pct
            }
            
        case "ITEM_FOOD":
            time = item_values[0]
            hit_reg = item_values[1]*15 or 15
            move_reg = item_values[2]
            poi = "YES" if item_values[3] else "NO"
            str_con = item_values[4]
            agi_dex = item_values[5]
            int_wis = item_values[6]
            hit_dam = item_values[7]
            Item_Type_Notes = {
            "Duration": time,
            "Hit Regen": hit_reg,
            "Move Regen": move_reg,
            "Str/Con": str_con,
            "Agi/Dex": agi_dex,
            "Int/Wis": int_wis,
            "Hit/Dam": hit_dam,
            "Poison": poi
            }
            
        case "ITEM_MONEY":
            copper = item_values[0]
            silver = item_values[1]
            gold = item_values[2]
            platinum = item_values[3]
            Item_Type_Notes = {
            "Copper": copper,
            "Silver": silver,
            "Gold": gold,
            "Platinum": platinum
            }
            
        case "ITEM_TELEPORT":
            to_room = item_values[0]
            command = item_values[1]
            charges = item_values[2]
            if charges == -1:
                charges = "Infinite"
            zone_to = item_values[3]
            Item_Type_Notes = {
                "To Room": to_room,
                "Command": command,
                "Charges": charges,
                "To Zone": zone_to
            }

        case "ITEM_PICK":
            pick_bonus = item_values[0]
            break_pct = item_values[1]
            Item_Type_Notes = {
                "Pick Bonus": pick_bonus,
                "Break Pct": break_pct
            }

        case "ITEM_INSTRUMENT":
            type = item_values[0]
            level = item_values[1]
            break_pct = item_values[2]
            min_level = item_values[4]
            Item_Type_Notes = {
                "Type": type,
                "Level": level,
                "Break Chance": break_pct,
                "Min Level": min_level
            }

        case "ITEM_SPELLBOOK":
            prof = item_values[0]
            tongue = item_values[1]
            total_pages = item_values[2]
            used_pages = item_values[3]
            Item_Type_Notes = {
                "Class": prof,
                "Tongue": tongue,
                "Total Pages": total_pages,
                "Used Pages": used_pages,
            }

        case "ITEM_SWITCH":
            cmd = item_values[0]
            room = item_values[1]
            direction = item_values[2]
            switch_move = "SWITCH" if item_values[3] else "WALL"
            Item_Type_Notes = {
                "Command": cmd,
                "Room": room,
                "Direction": direction,
                "What Move": switch_move
            }

        case "ITEM_QUIVER":
            max_hold = item_values[0]
            flags = item_values[1]
            missile_type = item_values[2]
            cur_hold = item_values[3]
            Item_Type_Notes = {
                "Max Hold": max_hold,
                "Current Held": cur_hold,
                "Flags": flags,
                "Missile Type": missile_type
            }
                
        case "ITEM_TOTEM":
            spheres = ', '.join(decode_flags(item_values[0], TOTEM_SPHERE_FLAGS))
            Item_Type_Notes = {
                "Spheres": spheres
            }
    
        case "ITEM_BANDAGE":
            maxheal = item_values[0]
            Item_Type_Notes = {
                "Max Heal": maxheal
            }
    
        case "ITEM_HERB":
            level = item_values[0]
            herb_1 = herb_type_lookup.get(item_values[1], "")
            herb_2 = herb_type_lookup.get(item_values[2], "")
            herb_3 = herb_type_lookup.get(item_values[3], "")
            duration = item_values[7]
            spell_2_level = level // 2 if herb_2 else None
            spell_3_level = level // 3 if herb_3 else None
            stoned_duration = item_values[6]
            Item_Type_Notes = {
                "Level": level,
                "Duration": duration,
                "Spell_1": herb_1,
                "Spell_1 Level:": level,
                "Spell_2": herb_2,
                "Spell_2 Level": spell_2_level,
                "Spell_3": herb_3,
                "Spell_3 Duration": spell_3_level,
                "Stoned Duration": stoned_duration
            }
                

        case "ITEM_PIPE":
            pipe_type = item_values[0]
            pipe_hp = item_values[1]
            break_pct = item_values[2]     #if( number(1, 100) < pipe->value[2] )
            Item_Type_Notes = {
                "Pipe Type": pipe_type,
                "Pipe HP": pipe_hp,
                "Break Pct": break_pct
            }

        case _:
            return {"Unknown Type": item_type, "Raw Values": item_values}

    return Item_Type_Notes


def punt(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)

def get_loaded_areas():
    
    with open(AREA_LIST, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('*'):
                continue            
            line_parts = line.split()
            zone_file = line_parts[0]

            LOADED_AREAS.append(zone_file)

def parse_zon_file(filename):
    """
    Parses a .zon file and returns a dict of zones keyed by vnum.
    """
    zones = {}

    with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
        lines = iter(f)

        for raw in lines:
            line = raw.strip()

            # Skip comments / empty
            if not line or line.startswith('*'):
                continue

            # Start of a new zone
            if line.startswith('#'):
                vnum = int(line[1:])

                # --- Line 2: name ---
                while True:
                    name_line = next(lines).strip()
                    if name_line and not name_line.startswith('*'):
                        break

                if not name_line.endswith('~'):
                    raise ValueError(f"Zone {vnum}: name not terminated with ~")

                zone_name = name_line[:-1]

                # --- Line 3: stats ---
                while True:
                    stats_line = next(lines).strip()
                    if stats_line and not stats_line.startswith('*'):
                        break

                parts = stats_line.split()
                if len(parts) != 6:
                    raise ValueError(f"Zone {vnum}: invalid stat line")

                max_vnum   = int(parts[0])
                reset_mode = int(parts[1])
                zone_flags = int(parts[2])
                min_time   = int(parts[3])
                max_time   = int(parts[4])
                zone_diff  = int(parts[5])

                # --- Skip commands until 'S' ---
                for cmd_line in lines:
                    cmd_line = cmd_line.strip()
                    if cmd_line == 'S':
                        break

                # Store zone
                #zones[vnum] = {
                zones = {
                    'vnum': vnum,
                    'name': zone_name,
                    'name_html': convert_mud_colors(zone_name),
                    'max_vnum': max_vnum,
                    'min_time': min_time,
                    'max_time': max_time,
                    'reset_mode': zone_repop_lookup.get(reset_mode, "UNKNOWN"),
                    'zone_flags': decode_flags(zone_flags, ZONE_FLAGS),
                    'zone_diff': zone_diff,
                }

    return zones

def parse_mob_file(filepath):
    mob_data = {}

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        lines = iter(f)

        for raw in lines:
            line = raw.strip()

            if line.startswith("#"):
                try:
                    vnum = int(line[1:])
                except ValueError:
                    continue

                try:
                    next(lines)  # skip keywords

                    short_desc_line = next(lines).strip()
                    short_desc = short_desc_line.rstrip("~")

                except StopIteration:
                    break

                # ✅ Use YOUR converter here
                short_desc_html = convert_mud_colors(short_desc)

                mob_data[vnum] = {
                    "s_desc": short_desc,
                    "s_desc_html": short_desc_html
                }

    return mob_data


def parse_command(line, object_data):
    parts = line.split()

    if len(parts) < 3:
        return {"type": "unknown", "raw": line}

    cmd = parts[0]          # R or G
    subtype = parts[1]      # I, C, E, T, etc.
    value = int(parts[2])

    # --- ITEM ---
    if subtype == "I":
        obj = object_data.get(value)
        return {
            "type": "item",
            "vnum": value,
            "name": obj["short_description"] if obj else f"[Unknown Item {value}]",
            "name_html": obj["short_description_html"] if obj else f"[Unknown Item {value}]",
            "keywords": obj["name_list"].split() if obj else []
        }

    
    if subtype == "C": # COINS
        return {
            "type": "coins",
            "amount": value
        }

    if subtype == "E":  # Currency
        return {
            "type": "exp",
            "amount": value
        }

    if subtype == "T":  # ITEM_TYPE
        return {
            "type": "type_item",
            "amount": item_type_lookup[value]  #Do Item Type Look up here
        }
        
    # --- GENERIC FALLBACK (NEW) ---
    return {
        "type": "other",
        "subtype": subtype,
        "value": value,
        "label": f"{subtype} {value}",  # display-friendly
        "raw": line
    }


def parse_qst_file(filepath, object_data):
    results = []

    current_vnum = None
    keywords = []

    quests = {}
    current_q = None
    q_counter = 0

    in_q_text = False

    def flush_mob():
        nonlocal keywords, quests

        if not quests:
            return

        # Flatten keywords into single string
        keyword_str = " ".join(keywords)

        results.append({
            "vnum": current_vnum,
            "keywords": keyword_str,
            "Quests": quests.copy()
        })

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        lines = iter(f)

        for raw in lines:
            line = raw.strip()

            # --- New mob ---
            if line.startswith("#"):
                if current_vnum is not None:
                    flush_mob()

                current_vnum = line[1:]
                keywords = []
                quests = {}
                current_q = None
                q_counter = 0
                continue

            # --- M block ---
            if line in ("M", "MA"):
                try:
                    kw_line = next(lines).strip().rstrip("~")

                    # Skip qc_action entries
                    if "qc_action" not in kw_line:
                        keywords.append(kw_line)

                except StopIteration:
                    pass
                continue

            # --- Start Q block ---
            if line in ("Q", "QA"):
                q_counter += 1
                key = f"R{q_counter}"

                current_q = {
                    "R": [],
                    "G": []
                }
                
                quests[key] = current_q

                quests[key] = current_q
                in_q_text = True
                continue

            # --- End Q text ---
            if in_q_text and line == "~":
                in_q_text = False
                continue

            if in_q_text:
                continue

            # --- Commands ---
            if current_q:
                if line.startswith("R "):
                    # append to the correct R key
                    for k in current_q:
                        if k.startswith("R"):
                            current_q[k].append(parse_command(line, object_data))
                    continue

                if line.startswith("G "):
                    current_q["G"].append(parse_command(line, object_data))
                    continue

            # --- End mob ---
            if line == "S":
                if current_vnum is not None:
                    flush_mob()

                current_vnum = None
                keywords = []
                quests = {}
                current_q = None
                continue

        # EOF flush
        if current_vnum is not None:
            flush_mob()

    return results

def parse_obj_file(path):
    objects = {}

    pending_line = None

    with open(path, "r", encoding="latin-1") as f:
        lines = iter(f)

        while True:
            if pending_line is not None:
                raw = pending_line
                pending_line = None
            else:
                raw = next(lines, None)

            if raw is None:
                break

            line = raw.strip()

            if not line.startswith("#"):
                continue

            if line.startswith("$"):
                break

            # object header
            vnum = int(line[1:])

            namelist   = read_tilde_block(lines)
            short_desc = read_tilde_block(lines)
            long_desc  = read_tilde_block(lines)
            _ = read_tilde_block(lines)  # full desc / unused

            # stats line 1
            stats1 = read_ints_line(lines)

            defaults = [0, 0, 0, 0, 7, 0, 0, 0, 0, 0, 0]
            stats1 = (stats1 + defaults)[:11]

            (
                item_type, matl_type, size, space,
                craftsmanship, dmg_resist,
                extra1_flags, wear_flags,
                extra2_flags, anti1_flags, anti2_flags
            ) = stats1

            # stats line 2
            stats2 = read_ints_line(lines)
            stats2 = (stats2 + [0] * 8)[:8]
            item_vals = stats2
            item_type_str = item_type_lookup.get(item_type, "UNKNOWN")
            item_vals_notes = process_item_values(item_vals, item_type_str)

            # stats line 3
            stats3 = read_ints_line(lines)
            stats3 = (stats3 + [0] * 8)[:8]

            weight, worth, condition, aff1, aff2, aff3, aff4, aff5 = stats3

            # optional E / A sections
            extra_desc = []
            affects = []

            while True:
                #peek = next(lines).strip()
                try:
                    peek = next(lines).strip()
                except StopIteration:
                    break                

                if peek == "E":
                    keyword = read_tilde_block(lines)
                    if "_id_name_" in keyword:
                        continue
                    desc = read_tilde_block(lines)
                    extra_desc.append((keyword, desc))

                elif peek == "A":
                    loc, mod = read_ints_line(lines)
                    loc = modifiers_lookup[loc]
                    affects.append((loc, mod))

                else:
                    # push back one line for the outer loop
                    pending_line = peek + "\n"
                    break

            # ---- store object ----
            objects[vnum] = {
                "vnum": vnum,
                "name_list": namelist,
                "short_description": short_desc,
                "short_description_html": convert_mud_colors(short_desc),
                #"long_description": long_desc,
                "item_type": item_type_lookup.get(item_type, "UNKNOWN"),
                "material": material_type_lookup.get(matl_type, "UNKNOWN"),
                #"size": item_size_lookup[size],
                #"space": space,
                "craftsmanship": craftmanship_lookup.get(craftsmanship, "UNKNOWN"),
                #"damage_resist": dmg_resist,
                "wear_flags": decode_flags(wear_flags, ITEM_WEAR_FLAGS),
                "extra1_flags": decode_flags(extra1_flags, ITEM_EXTRA1_FLAGS),
                "extra2_flags": decode_flags(extra2_flags, ITEM_EXTRA2_FLAGS),
                "anti1_flags": decode_flags(anti1_flags, ITEM_CLASS_ANTI_FLAGS),
                "anti2_flags": decode_flags(anti2_flags, ITEM_ANTI2_FLAGS),
                "item_values": item_vals,
                "item_value_notes": item_vals_notes,
                "weight": weight,
                "worth": worth,
                #"condition": condition,
                "aff1": decode_flags(aff1, ITEM_AFF1_FLAGS),
                "aff2": decode_flags(aff2, ITEM_AFF2_FLAGS),
                "aff3": decode_flags(aff3, ITEM_AFF3_FLAGS),
                "aff4": decode_flags(aff4, ITEM_AFF4_FLAGS),
                "aff5": decode_flags(aff5, ITEM_AFF5_FLAGS),
                "affects": affects,
                #"extra_descriptions": extra_desc,
            }

    return objects


if __name__ == "__main__":
    get_loaded_areas()
    object_data = parse_obj_file(WORLD_OBJECTS)
    zon_path = "./zon/"
    mob_path = "./mob/"
    qst_path = "./qst/"


    for zone_file in LOADED_AREAS:
        print(zone_file)
        qst_file = qst_path + zone_file + ".qst"

        # Skip this zone if no QST file
        if not os.path.exists(qst_file):
            print(f"[SKIP] No QST file for {zone_file}")
            continue
        zone_data = parse_zon_file(zon_path+zone_file+".zon")
        mob_data = parse_mob_file(mob_path+zone_file+".mob")
        qst_file = qst_path + zone_file + ".qst"

        if os.path.exists(qst_file):
            quest_data = parse_qst_file(qst_file, object_data)
        else:
            quest_data = []  # ✅ safe fallback        
        quest_data = parse_qst_file(qst_path+zone_file+".qst", object_data)

        rows = build_rows(quest_data, mob_data)
        html_output = build_html_table(rows)


        #with open(zone_file+"_quests.html", "w", encoding="utf-8") as f:
            #f.write(html_output)
                
        title = strip_mud_colors(zone_data["name"]) + " Quests"
        caption = convert_mud_colors(zone_data["name"]) + " Quests"
        text = html_output
        tags = "Quest"
        append_tid_for_output(
            create_new_tid_from_template(title, caption, text, tags, creator="Drevarr"),
            tid_list
        )
    #loaded_zone_list = list(zone_data.values())

    #with open("zones.json", "w") as f:
        #json.dump(loaded_zone_list, f, indent=4) #, indent=2 

    write_tid_list_to_json(tid_list, "Duris_Quest_tids.json")

    print("complete")        