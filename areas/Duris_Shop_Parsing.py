import json


def fread_string(f):
    """Read a ~-terminated string."""
    parts = []
    while True:
        line = f.readline()
        if not line:
            break

        if "~" in line:
            before, _ = line.split("~", 1)
            parts.append(before.rstrip("\n"))
            break

        parts.append(line.rstrip("\n"))

    return "\n".join(parts).strip()


def read_int(f):
    return int(f.readline().strip())


def read_float(f):
    return float(f.readline().strip())


def read_char(f):
    return f.readline().strip()


def read_int_list(f, terminator=0, max_items=100):
    """Generic reader for producing + trade_types."""
    result = []
    for _ in range(max_items):
        val = int(f.readline().strip())
        if val == terminator:
            break
        result.append(val)
    return result


def parse_shop_file(path):
    shops = []

    with open(path, "r", encoding="utf-8") as f:
        while True:
            header = fread_string(f)

            if not header:
                break

            if header.startswith("$"):
                break

            if not header.startswith("#"):
                raise ValueError(f"Unexpected header: {header}")

            shop = {}
            shop["vnum"] = int(header[1:].replace("~", ""))

            # format
            if read_char(f) != "N":
                raise ValueError(f"Unsupported shop format: {shop['vnum']}")

            # producing list
            shop["producing"] = read_int_list(f)

            # buy/sell
            t_buy = read_float(f)
            t_sell = read_float(f)

            buy = min(max(t_buy, 0.05), 0.8)
            sell = min(max(t_sell, 1.0), 10.0)

            if sell <= buy:
                if sell > 7.0:
                    buy = sell - 1.0
                else:
                    sell = buy + 0.25

            shop["buy_percent"] = buy
            shop["sell_percent"] = sell

            # trade types ?
            shop["trade_types"] = read_int_list(f)

            # messages
            shop["messages"] = {
                "no_such_item1": fread_string(f),
                "no_such_item2": fread_string(f),
                "do_not_buy": fread_string(f),
                "missing_cash1": fread_string(f),
                "missing_cash2": fread_string(f),
                "buy": fread_string(f),
                "sell": fread_string(f),
            }

            # core data
            shop["temper1"] = read_int(f)
            shop["temper2"] = read_int(f)
            shop["keeper"] = read_int(f)

            shop["with_who"] = read_int(f)
            shop["in_room"] = read_int(f)

            shop["hours"] = {
                "open1": read_int(f),
                "close1": read_int(f),
                "open2": read_int(f),
                "close2": read_int(f),
            }

            # flags
            shop["flags"] = {
                "roaming": read_char(f) == "Y",
                "magic_allowed": read_char(f) == "Y",
                "killable": read_char(f) == "Y",
            }

            # open/close messages
            shop["open_message"] = fread_string(f)
            shop["close_message"] = fread_string(f)

            shop["shop_hometown"] = read_int(f)
            shop["social_action_types"] = read_int(f)

            shop["racist"] = read_char(f) == "Y"
            shop["shopkeeper_race"] = read_int(f)
            shop["racist_message"] = fread_string(f)

            # end marker
            end_flag = read_char(f)
            if end_flag != "X":
                raise ValueError(f"Shop {shop['vnum']} missing end marker")

            shops.append(shop)

    return shops
	    
def normalize_shop(shop):
    return {
        "vnum": shop["vnum"],
        "producing": shop["producing"],
        "trade_types": shop["trade_types"],
        "economy": {
            "buy_percent": shop["buy_percent"],
            "sell_percent": shop["sell_percent"],
        },
        "messages": shop["messages"],
        "keeper": {
            "vnum": shop["keeper"],
            "race": shop["shopkeeper_race"],
            "racist": shop["racist"],
            "racist_message": shop["racist_message"],
        },
        "location": {
            "room": shop["in_room"],
            "with_who": shop["with_who"],
            "hometown": shop["shop_hometown"],
        },
        "hours": shop["hours"],
        "behavior": {
            "temper1": shop["temper1"],
            "temper2": shop["temper2"],
            "social_action_types": shop["social_action_types"],
            "flags": shop["flags"],
        },
        "dialogue": {
            "open": shop["open_message"],
            "close": shop["close_message"],
        },
    }
    
shops = parse_shop_file("tworld.shp")
normalized = [normalize_shop(s) for s in shops]

with open("shops.json", "w", encoding="utf-8") as f:
    json.dump(normalized, f, indent=2, ensure_ascii=False)
print("Complete.")