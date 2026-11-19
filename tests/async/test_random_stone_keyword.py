#!/usr/bin/env python3
"""Random drop stones answer to 'random' like every other random drop (issue #1124)."""
import re

from _paths import ROOT

objects = (ROOT / "areas/obj/tradeskills.obj").read_text()
for vnum in range(400291, 400300):
    keywords = re.search(rf"^#{vnum}\n(.*)~$", objects, re.MULTILINE)
    assert keywords and keywords[1].split()[0] == "random", (vnum, keywords)
print("random drop stones keep the random keyword")
