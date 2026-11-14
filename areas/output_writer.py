def build_rows(qst_data, mob_data):
    rows = []

    for mob in qst_data:
        try:
            vnum = int(mob["vnum"])
        except (KeyError, ValueError):
            continue

        mob_info = mob_data.get(vnum)

        if mob_info:
            mob_name_html = mob_info.get(
                "s_desc_html",
                f"<span class='unknown'>Mob {vnum}</span>"
            )
        else:
            mob_name_html = f"<span class='unknown'>Mob {vnum}</span>"

        # Optional: append vnum label
        mob_display = f"{mob_name_html} <span class='vnum'>[{vnum}]</span>"

        for qid, quest in mob.get("Quests", {}).items():
            rows.append({
                "vnum": vnum,
                "mob_name": mob_display,
                "quest_id": qid,
                "R": quest.get("R", []),
                "G": quest.get("G", [])
            })

    return rows

    
def split_currency(total):
    p = total // 1000
    remainder = total % 1000

    g = remainder // 100
    remainder %= 100

    s = remainder // 10
    c = remainder % 10

    return {
        "p": p,
        "g": g,
        "s": s,
        "c": c
    }
    
def format_currency_html(total):
    cur = split_currency(total)

    parts = []
    if cur["p"]:
        parts.append(f"<span class='coin p'>{cur['p']}p</span>")
    if cur["g"]:
        parts.append(f"<span class='coin g'>{cur['g']}g</span>")
    if cur["s"]:
        parts.append(f"<span class='coin s'>{cur['s']}s</span>")
    if cur["c"]:
        parts.append(f"<span class='coin c'>{cur['c']}c</span>")

    return " ".join(parts) if parts else "<span class='coin c'>0c</span>"
    
def format_items(items):
    output = []

    for item in items:
        if item["type"] == "item":
            output.append(item["name_html"])

        elif item["type"] == "coins":
            output.append(format_currency_html(item["amount"]))

        elif item["type"] == "exp":
            output.append(f"<span class='exp'>{item['amount']} XP</span>")

        elif item["type"] == "type_item":
            output.append(f"<span class='itemtype'>Any item of type: {item['amount']}</span>")
            
        else:
            # fallback for T, etc.
            output.append(f"<span class='other'>{item['label']}</span>")

    return "<br>".join(output)


def build_html_table(rows):
    html_output = []
    html_output.append("<table border='1' cellspacing='0' cellpadding='5'>")
    html_output.append("<tr><th>Quest Mob</th><th>Rewards (R)</th><th>Requirements (G)</th></tr>")

    for row in rows:
        r_html = format_items(row["R"])
        g_html = format_items(row["G"])

        html_output.append(f"""
        <tr>
            <td>{row['mob_name']}</td>
            <td>{r_html}</td>
            <td>{g_html}</td>
        </tr>
        """)

    html_output.append("</table>")
    return "\n".join(html_output)