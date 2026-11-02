import os
import sys

AREA_LIST = "AREA"
SUMMARY = {}

def punt(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def build_world(subdir, extension, output_file, label):
    """
    subdir: directory like 'mob' or 'obj'
    extension: file extension like 'mob' or 'obj'
    output_file: output filename like 'tworld.mob'
    label: string for summary output ('mobs' or 'objects')
    """
    try:
        area_list = open(AREA_LIST, "r", encoding="utf-8", errors="ignore")
    except IOError:
        punt("AREA file cannot be opened")

    try:
        out = open(output_file, "w", encoding="utf-8")
    except IOError:
        punt(f"{output_file} cannot be opened")

    area_count = 0
    item_count = -1
    jel_line = 0
    
    for line in area_list:
        line = line.strip()

        if not line or line.startswith('*'):
            continue
        jel_line+=1
        area_name = line.split()[0]

        print(f"Area[{area_count:2d}] : {area_name}")
        area_count += 1

        file_path = os.path.join(subdir, f"{area_name}.{extension}")

        try:
            #print(f"Attemtping to parse: {area_name}.{extension}")
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for buf in f:
                    if buf.startswith('#'):
                        item_count += 1
                    out.write(buf)
        except IOError:
            print(f"\twarning: {file_path} not found")

    area_list.close()
    out.close()

    #print(f"\nSummary: {item_count} {label}\n")
    SUMMARY[label] = item_count

    try:
        os.chmod(output_file, 0o600)
    except Exception:
        pass

    print(f"{output_file} Done\n")

def main():
    # Build both outputs
    build_world("mob", "mob", "tworld.mob", "mobs")
    build_world("obj", "obj", "tworld.obj", "objects")
    build_world("shp", "shp", "tworld.shp", "shops")
    build_world("qst", "qst", "tworld.qst", "quests")
    build_world("wld", "wld", "tworld.wld", "rooms")
    build_world("zon", "zon", "tworld.zon", "zones")

    print("World Statistics:")
    print("=================")
    for item in SUMMARY:
        pad=" "
        item_count = f"{SUMMARY[item]:,d}"
        print(f"\t{item:{pad}<10}{item_count:{pad}>10}")

if __name__ == "__main__":
    main()    