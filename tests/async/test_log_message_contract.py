#!/usr/bin/env python3
"""Staff channels skip detached sessions and preserve complete messages."""
from pathlib import Path
import subprocess
import tempfile

from _paths import HARNESS_STUBS, ROOT, extract_function

HARNESS = r'''
#include "core/prototypes.h"
#include "core/utils.h"
#include "core/utility.h"
#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

P_desc descriptor_list;
static P_char recipient;
static int delivered, logged;
static std::string received, recorded;
void send_to_char(const char *text, P_char ch) {
    assert(ch == recipient);
    ++delivered;
    received = text;
}
void logit(const char *, const char *format, ...) {
    char buffer[32768];
    va_list args;
    va_start(args, format);
    vsnprintf(buffer, sizeof buffer, format, args);
    va_end(args);
    ++logged;
    recorded = buffer;
}
std::string strip_ansi(const char *text) { return text; }

// PRODUCTION

int main(int argc, char **argv) {
    assert(argc == 2);
    using logger = void (*)(int, const char *, ...);
    const logger channels[] = {ereglog, wizlog, loginlog, statuslog, epiclog, banlog};
    const int selected = atoi(argv[1]);
    assert(selected >= 0 && selected < 6);
    char_data staff{}, muted{}, mortal{}, junior{};
    staff.player.level = muted.player.level = 62;
    mortal.player.level = 30;
    junior.player.level = 55;
    staff.specials.act = PLR_SNOTIFY | PLR_WIZLOG | PLR_PLRLOG | PLR_STATUS | PLR_BAN;
    staff.specials.act3 = PLR3_EPICWATCH;
    mortal.specials.act = junior.specials.act = staff.specials.act;
    mortal.specials.act3 = junior.specials.act3 = staff.specials.act3;
    descriptor_data links[6]{};
    P_char characters[] = {nullptr, &staff, &muted, &mortal, &junior, &staff};
    for (int i = 0; i < 6; ++i) {
        links[i].connected = i == 5 ? CON_FLUSH : CON_PLAYING;
        links[i].character = characters[i];
        links[i].next = i < 5 ? &links[i + 1] : nullptr;
    }
    // Reconnection clears the old character before close_socket logs the close.
    descriptor_list = links;
    recipient = &staff;
    const std::string payload = std::string(8192, 'x') + " complete-tail 42";
    channels[selected](60, "%s %d", (std::string(8192, 'x') + " complete-tail").c_str(), 42);
    assert(delivered == 1 && received.find(payload) != std::string::npos);
    const bool writes_file = selected == 3 || selected == 4;
    assert(logged == (writes_file ? 1 : 0));
    if (writes_file) {
        assert(recorded.ends_with(payload));
        assert(recorded.find('\n') == std::string::npos);
    }
    // File logging still works when there are no eligible session recipients.
    descriptor_list = nullptr;
    channels[selected](60, "without recipients");
    assert(delivered == 1 && logged == (writes_file ? 2 : 0));
    puts("staff channel accepts a detached playing session and preserves recipients");
}
'''

functions = ["static char *format_variadic_message("] + [
    "void " + name + "(" for name in
    ("ereglog", "wizlog", "loginlog", "statuslog", "epiclog", "banlog")]
production = "\n".join(extract_function("utility.c", signature) for signature in functions)
(ROOT / "bin/tests").mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="staff-logging-", dir=ROOT / "bin/tests") as directory:
    source = Path(directory) / "harness.cpp"
    binary = Path(directory) / "harness"
    source.write_text(HARNESS.replace("// PRODUCTION", production))
    subprocess.run(["g++", "-std=c++20", "-g", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                    "-fno-omit-frame-pointer", "-Isrc", str(source), str(HARNESS_STUBS),
                    "-o", str(binary)], cwd=ROOT, check=True, timeout=120)
    failures = []
    for selected, name in enumerate(("ereglog", "wizlog", "loginlog", "statuslog", "epiclog", "banlog")):
        result = subprocess.run([str(binary), str(selected)], capture_output=True, text=True, timeout=30)
        if result.returncode:
            failures.append(name)
            print(name + ": " + result.stderr, flush=True)
        else:
            print("PASS " + name, flush=True)
    assert not failures, failures
print("staff logging runtime regression passed")
