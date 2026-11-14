import re
import html

MUD_COLORS = {
    "&+R":"#FF6666","&+r":"#CC0000",
    "&+W":"#FFFFFF","&+w":"#CCCCCC",
    "&+Y":"#FFFF66","&+y":"#CCCC00",
    "&+B":"#6666FF","&+b":"#0000CC",
    "&+C":"#66FFFF","&+c":"#00CCCC",
    "&+L":"#666666","&+l":"#000000",
    "&+M":"#FF66FF","&+m":"#CC00CC",
    "&+G":"#66FF66","&+g":"#00CC00"
}


COLOR_RE = re.compile(r'(&\+[a-zA-Z]|&n|&N)')

def strip_mud_colors(text):
    # Remove combined bg+fg codes first
    text = re.sub(r"&=[A-Za-z]{2}", "", text)

    # Remove foreground / background codes
    text = re.sub(r"&[+-][A-Za-z]", "", text)

    # Remove reset
    text = text.replace("&n", "")
    text = text.replace("&N", "")
    
    return text

def convert_mud_colors(text: str) -> str:
    if not text:
        return ""

    color = "#00CC00"
    out = []

    parts = COLOR_RE.split(text)

    for part in parts:
        if not part:
            continue

        if part in ("&n", "&N"):
            color = "#00CC00"
            continue

        if part in MUD_COLORS:
            color = MUD_COLORS[part]
            continue

        safe = html.escape(part)
        out.append(f'<span style="color:{color}">{safe}</span>')

    return "".join(out)

def read_tilde_block(lines):
    buf = []
    for line in lines:
        line = line.rstrip("\n")
        if line.endswith("~"):
            buf.append(line[:-1])
            break
        buf.append(line)
    return "\n".join(buf)


def read_ints_line(lines):
    return list(map(int, next(lines).split()))

