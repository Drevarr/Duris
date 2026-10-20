import json
import os
import re
from pathlib import Path


LANDMARKS = {
    528827: "Fenaline Docks",
    519298: "Darkmore Forest & Quintaragon Castle",
    524894: "Darkmore Forest & Quintaragon Castle",
    526528: "Shaledrieth (Sunwell)",
    530034: "Totem Pass",
    532036: "Totem Pass",
    536039: "Worm Pass",
    538438: "Worm Pass",
    539288: "Broken Blade Inn",
    545285: "Elven Pass",
    547289: "Elven Pass",
    545343: "Canderthal Harbor",
    544843: "Mystic",
    572471: "Jenna's Waystation",
    568439: "Tharnadian Ruins",
    584825: "Lareth (Sunwell)",
    590430: "Farseer Outpost",
    578863: "Gnomish Observatory",
    578100: "Spider Pass",
    576102: "Spider Pass",
    579311: "Pit Lions",
    627270: "Bear Pass",
    635261: "Dalvik",
    612059: "The Basin Waste",
    630996: "Deep and Dark Hole",
    629815: "Moria Shaft",
    623811: "Troll Mercenary",
    622612: "Troll Mercenary",
    623031: "Arlik's Inn",
    610280: "Goat Path",
    609883: "Goat Path",
    599922: "Warg Ravine",
    598723: "Warg Ravine",
    593125: "Orc Trade Path",
    591925: "Orc Trade Path",
    597062: "Ogre Camp",
    597058: "Ogre Camp",
    597444: "Contraband Pirate",
    619036: "Worm Crater",
    590199: "Lava Tubes",
    589401: "Lava Tubes",
    583796: "Cyric's Tunnels",
    577782: "Cursed Bridge",
    577784: "Cursed Bridge",
    573429: "Magma Path",
    573831: "Magma Path",
    567018: "Collapsed Tower",
    568230: "Ruined Outpost",
    543910: "Ice Forest",
    543119: "Ice Forest",
    542730: "Fishing Village",
    541147: "Greyy Fang",
    537871: "Altar of Ice",
    523899: "General Store",
    518665: "Cave of the Roc",
    516667: "Cave of the Roc",
    517880: "Tzultaire Ruins",
    517891: "Boulder Lion Pass",
    516291: "Boulder Lion Pass",
    513880: "Bone Fort Inn",
    512667: "Chesynn the Hunter",
    513384: "Shadow Pass",
    511781: "Shadow Pass",
    510179: "The Great Shaboath",
    556018: "The Transparent Tower",
    562071: "Savannah of Broken Trusts" #Placeholder to get around zone exit and entrance being on the marker
}

DIRECTIONS = {
    "D0": "North",
    "D1": "East",
    "D2": "South",
    "D3": "West",
    "D4": "Up",
    "D5": "Down",
    "D6": "NorthWest",
    "D7": "SouthWest",
    "D8": "NorthEast",
    "D9": "SouthEast",
}

Direction_Offsets = {
    "North": (0,1),
    "East": (1,0),
    "South": (0,-1),
    "West": (-1,0),
    "Up": (0,0,1),
    "Down": (0,0,-1),
    "NorthWest": (-1,1),
    "SouthWest": (-1,-1),
    "NorthEast": (1,1),
    "SouthEast": (1,-1)
}

Reverse_Offsets = {
    "North": 400,
    "East": -1,
    "South": -400,
    "West": 1,
    "Up": 0,
    "Down": 0,
    "NorthWest": 401,
    "SouthWest": -399,
    "NorthEast": 399,
    "SouthEast": -401
}

TARGET_MIN = 500000 #Starting VNUM for Surface Map
TARGET_MAX = 659999 #Ending VNUM for Surface Map
Square_Size = 4     #Each room is Square_Size in pixes
Map_Width = 400     #400 x 400 produces a  1600x1600 png
Map_Length = 400
zone_marker_points = set()

def update_landmarks():
    for vnum in LANDMARKS:
        zone_marker_data.setdefault(vnum, {})['zone'] = LANDMARKS[vnum]
        
def find_marker_adjacent(vnum):
    for offset in Reverse_Offsets.values():
        if (vnum + offset) in zone_marker_points:
            return True
    return False

def parse_zone_markers(filepath, target_zone, zone_marker_points):
    """
    Parses a .wld file and adds vnums to zone_marker_points
    when a room contains a line: `<target_zone> 0 0 0`
    """
    current_vnum = None

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        lines = iter(f)

        for raw_line in lines:
            line = raw_line.strip()

            # Start of a new room
            if line.startswith('#'):
                try:
                    current_vnum = int(line[1:])
                except ValueError:
                    current_vnum = None
                continue

            # Skip until we have a valid room
            if current_vnum is None:
                continue

            # Skip name line (ends with ~)
            if line.endswith('~'):
                continue

            # Skip description block
            if line == '~':
                continue

            # Check for zone marker line
            parts = line.split()
            if len(parts) == 4:
                try:
                    zone = int(parts[0])
                    if zone == target_zone and parts[2:] == ['0', '0']:
                        zone_marker_points.add(current_vnum)
                except ValueError:
                    pass

def strip_mud_colors(text):
    # Remove combined bg+fg codes first
    text = re.sub(r"&=[A-Za-z]{2}", "", text)

    # Remove foreground / background codes
    text = re.sub(r"&[+-][A-Za-z]", "", text)

    # Remove reset
    text = text.replace("&n", "")
    text = text.replace("&N", "")
    
    return text

def find_zone_marker(direction, to_room):
    marker_vnum = to_room + Reverse_Offsets[direction]

    return marker_vnum

def get_zone_name(file_start):
    zone_name = zone_data[file_start]['name']
    return zone_name

def parse_zon_file(directory, loaded_areas):
    """
    Parses a .zon file and returns a dict with zone metadata.
    Only the first 3 non-comment lines are used.
    """
    zones = {}
    for filename in os.listdir(directory):
        meaningful = []
        file_start, file_extension = os.path.splitext(filename)
        #print("Loading: ",filename)            
        filepath = os.path.join(directory, filename)

        if filename.endswith(".zon") and file_start in loaded_areas:
            #print("Attempting to parse: ",filename)
           
            #all_results.extend(parse_wld_file(filepath))  
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
        
                    # Skip empty lines and comments
                    if not line or line.startswith('*'):
                        continue
        
                    meaningful.append(line)
        
                    if len(meaningful) == 3:
                        break
        
            if len(meaningful) < 3:
                raise ValueError("Invalid .zon file: not enough data lines")
        
            #  Line 1: zone vnum
            if not meaningful[0].startswith('#'):
                raise ValueError("Invalid zone vnum line")
        
            vnum = int(meaningful[0][1:])
        
            # Line 2: zone name
            name_line = meaningful[1]
            if not name_line.endswith('~'):
                raise ValueError("Zone name not terminated with ~")
        
            zone_name = name_line[:-1]
        
            # Line 3: zone stats
            parts = meaningful[2].split()
            if len(parts) != 6:
                raise ValueError("Invalid zone stat line")
        
            max_vnum   = int(parts[0])
            reset_mode = int(parts[1])
            zone_flags = int(parts[2])
            min_time   = int(parts[3])
            max_time   = int(parts[4])
            zone_diff  = int(parts[5])
        
            if file_start not in zones:
                zones[file_start] ={
                    'vnum': vnum,
                    'name': strip_mud_colors(zone_name),
                    'max_vnum': max_vnum,
                    'min_time': min_time,
                    'max_time': max_time,
                    'reset_mode': reset_mode,
                    'zone_flags': zone_flags,
                    'zone_diff': zone_diff,            
                }
        
    return zones
    
def parse_area(file_loc):
    pattern = re.compile(r'([a-z_\d]+)\s+\*')  # use + instead of * (important)

    areas = []

    with open("AREA", "r", encoding="utf-8") as f:
        for line in f:
            match = pattern.search(line)
    
            if match and match.group(1) !="end" and "surf" not in match.group(1):
                areas.append(match.group(1))
    
    return areas
    
def read_until_tilde(lines):
    """Consume lines until one ends with ~"""
    for line in lines:
        if line.rstrip().endswith("~"):
            return
    raise StopIteration

def parse_wld_file(directory, loaded_areas):
    results = {}

    for filename in os.listdir(directory):
        file_start, file_extension = os.path.splitext(filename)
        if filename.endswith(".wld") and file_start in loaded_areas:
            #print("Attempting to parse",filename)
            filepath = os.path.join(directory, filename)
            #results[file_start]={}
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                lines = iter(f.readlines())  # ← FIX
        
                current_room = None
            
                for raw in lines:
                    line = raw.strip()
            
                    if line.startswith("#"):
                        try:
                            current_room = int(line[1:])
                        except ValueError:
                            current_room = None
                        continue
            
                    if line == "S":
                        current_room = None
                        continue
            
                    if line == "E":
                        try:
                            read_until_tilde(lines)
                            read_until_tilde(lines)
                        except StopIteration:
                            break
                        continue
            
                    if line in DIRECTIONS and current_room is not None:
                        direction = DIRECTIONS[line]
            
                        try:
                            read_until_tilde(lines)
                            read_until_tilde(lines)
            
                            exit_line = next(lines).strip()
                            parts = exit_line.split()
            
                            if len(parts) >= 3:
                                to_room = int(parts[-1])
            
                                if TARGET_MIN <= to_room <= TARGET_MAX:
                                    zone_marker = find_zone_marker(direction, to_room)
                                    if zone_marker in zone_marker_points:
                                        zone_name = get_zone_name(file_start)
                                        results[zone_marker]={
                                            "zone": zone_name,
                                            "from_room": current_room,
                                            "direction": direction,
                                            "to_room": to_room                                    
                                        }
            
                        except StopIteration:
                            break

    return results

def parse_directory(directory, loaded_areas):
    all_results = []

    for filename in os.listdir(directory):
        if filename.endswith(".wld") and filename in loaded_areas:
            #print("Attempting to parse",filename)
            filepath = os.path.join(directory, filename)
            all_results.extend(parse_wld_file(filepath))

    return all_results

if __name__ == "__main__":

    # File Locations
    script_directory = Path(__file__).resolve().parent
    template_path = script_directory / "leaflet_template.html"
    target_zone = 5000  # Zone Number of Surface_map
    surface_map = script_directory / "wld" / "surface.wld"
    area_loc = script_directory
    zon_directory = script_directory / "zon"
    wld_directory = script_directory / "wld"

    # Parse Map file for zone markers
    parse_zone_markers(str(surface_map), target_zone, zone_marker_points)

    # Read AREA file for loaded zones
    loaded_areas = parse_area(str(area_loc))

    # Read ZON files for zone name and details
    zone_data = parse_zon_file(str(zon_directory), loaded_areas)

    # Read WLD files and find exits to Map vnums
    zone_marker_data = parse_wld_file(str(wld_directory), loaded_areas)

    # Inject Sniktiorg landmark names
    update_landmarks()

    # Sort Markers based on name from zon file
    sorted_zone_marker_data = dict(
        sorted(zone_marker_data.items(), key=lambda item: item[1]['zone'])
    )

    # Print markers for leaflet
    for marker in sorted_zone_marker_data:
        print(f'  {{ vnum: {marker}, name: "{zone_marker_data[marker]["zone"]}" }},')

    # Convert the sorted dictionary into JSON
    zones_json = json.dumps(
        [
            {"vnum": marker, "name": data["zone"]}
            for marker, data in sorted_zone_marker_data.items()
        ],
        ensure_ascii=False
    )

    template = template_path.read_text(encoding="utf-8")
    html = template.replace("{{ZONES_DATA}}", zones_json)
    output_path = Path(__file__).resolve().parent / "duris_surface_map.html"
    output_path.write_text(html, encoding="utf-8")
    print("duris_surface_map.html has been created")