#!/usr/bin/env python3
"""Source-contract checks for INNATE_ARCANE_RUDIMENTS mechanic."""
from _paths import SRC, extract_function
from pathlib import Path
import sys, re
from contract_text import contains

ROOT = Path(__file__).resolve().parents[2]
def check(name, ok):
	if not ok:
		print(f"FAIL: {name}")
	return bool(ok)

all_ok = True

# 1. structs.h: define exists
structs = (SRC / "structs.h").read_text()
all_ok &= check("INNATE_ARCANE_RUDIMENTS #define",
	contains(structs, "#define INNATE_ARCANE_RUDIMENTS       177"))
all_ok &= check("next innate follows arcane rudiments",
	contains(structs, "#define INNATE_WEB_SPRAY 178"))
last = re.search(r"#define LAST_INNATE (INNATE_\w+)", structs).group(1)
last_number = int(re.search(rf"#define {last} (\d+)", structs).group(1))
all_ok &= check("LAST_INNATE covers arcane rudiments", last_number >= 177)

# 2. innates_data array
innates = (SRC / "innates.c").read_text()
all_ok &= check("\"arcane rudiments\" in innates_data",
	contains(innates, "{\"arcane rudiments\", NULL},"))

# 3. No class assignments yet (0 ADD_CLASS_INNATE for it)
add_class_count = len(re.findall(r'ADD_CLASS_INNATE\(INNATE_ARCANE_RUDIMENTS,', innates))
all_ok &= check("no class assignments (user wants 0 for now)",
	add_class_count == 0)

# 4. Check the book rules that use this innate. The runtime prioritize test
# also exercises the shared check with an unavailable book and the innate.
mem = extract_function("memorize.c", "void do_memorize(P_char ch,")
all_ok &= check("list omits missing-book warning for Arcane Rudiments",
	contains(mem, "!has_innate(ch, INNATE_ARCANE_RUDIMENTS) && !(SpellInSpellBook("))
all_ok &= check("Arcane Rudiments permits queuing without a book",
	contains(mem, "!sbook && book_class(ch) && !has_innate(ch, INNATE_ARCANE_RUDIMENTS)"))
book = extract_function("memorize.c", "static bool has_preparation_book(")
all_ok &= check("Arcane Rudiments satisfies book availability",
	contains(book, "has_innate(ch, INNATE_ARCANE_RUDIMENTS) || SpellInSpellBook("))
for handler, spell in (("void handle_memorize(P_char ch)", "af->modifier"),
                       ("void do_prioritize(", "spell")):
	all_ok &= check(f"{handler} uses the preparation book check",
		contains(extract_function("memorize.c", handler), f"!has_preparation_book(ch, {spell})"))

# 5. No class has this innate inherited accidentally - check class_innates size
# class_innates[LAST_INNATE+2][CLASS_COUNT][5] uses LAST_INNATE
class_innates_line = [l for l in innates.splitlines() if "class_innates" in l and "[" in l]
all_ok &= check("class_innates array sized for LAST_INNATE",
	any("LAST_INNATE" in l for l in class_innates_line))

if all_ok:
	print("All arcane rudiments checks passed.")
	sys.exit(0)
else:
	print("FAILURES DETECTED")
	sys.exit(1)