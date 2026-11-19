#!/usr/bin/env python3
"""Run the real output phase, dirty-room flush and room-entry GMCP over moves.

Descriptors, rooms and the text queue are fixtures; run_output_phase(), the
dirty-room functions and char_to_room()'s room-entry GMCP lines are production
code. Moves happen in the command phase and in the events phase on both pulse
parities. Every descriptor that is told about a move must get its Room.Info in
the same output phase, after that text and prompt: never a pulse earlier
(issue #823) and never a pulse later. That also holds for the mover, for a
player in a switched NPC body, and when a zone reset dirties hundreds of other
rooms first.
"""

from pathlib import Path
import os
import subprocess
import tempfile

from _paths import ROOT, extract_function, source


gmcp = source("gmcp.c").read_text(encoding="utf-8")
flush = extract_function("gmcp.c", "void gmcp_flush_dirty_rooms(")
dirty_start = gmcp.rindex("\n/*", 0, gmcp.index("void gmcp_mark_room_dirty("))
dirty_rooms = gmcp[dirty_start:gmcp.index(flush) + len(flush)]

entry = extract_function("handler.c", "bool char_to_room(")
entry = entry[entry.index("\tif (dir != -2)\n\t\tdo_look(ch, 0, -4);"):
              entry.index("\t/* Send GMCP Room.Map")]

PRELUDE = r'''
#include <sys/select.h>
#include <cstdint>
#include <cstdio>
#include <string>
#include <unordered_set>
#include <vector>

struct output_queue { const void *head = nullptr; };
struct descriptor_data {
    descriptor_data *next = nullptr;
    int descriptor = 0, connected = 0, ws_state = 0, write_failed = 0;
    bool websocket = false, gmcp_enabled = true;
    size_t telnet_output_len = 0, ws_output_offset = 0, ws_output_len = 0,
           ws_control_output_len = 0;
    const char *ws_close_cause = nullptr;
    output_queue output;
    std::vector<std::string> queued, wire;
};
using P_desc = descriptor_data *;
struct char_data {
    int in_room = -1;
    bool npc = false;
    char_data *next_in_room = nullptr;
    descriptor_data *desc = nullptr;
};
using P_char = char_data *;
struct room_data { char_data *people = nullptr; };
struct game_loop_pulse_context { uint64_t loop_tick = 0, prompts_us = 0; };
enum { CON_PLAYING, CON_FLUSH, CON_SSLNEGO };
enum { WS_STATE_CLOSING = 3 };
#define PROFILE_START(name)
#define PROFILE_END(name)
#define IS_NPC(ch) ((ch)->npc)
#define GMCP_ENABLED(ch) ((ch) && (ch)->desc && (ch)->desc->gmcp_enabled)

static room_data rooms[700];
static room_data *world = rooms;
static int pulse = 0, failures = 0;
static bool in_output = false;
static fd_set output_set;
static P_desc descriptor_list = nullptr;

static void check(bool ok, const std::string &what)
{
    if (!ok) {
        ++failures;
        std::fprintf(stderr, "FAIL: %s\n", what.c_str());
    }
}
static void discord_bridge_flush() {}
static uint64_t loop_monotonic_us() { return 0; }
static uint64_t latency_trace_elapsed_us(uint64_t begin, uint64_t end) { return end - begin; }
static void latency_trace_record(const char *, uint64_t, uint64_t) {}
static int telnet_flush_output(P_desc) { return 0; }
static int websocket_flush_output(P_desc) { return 0; }
static void close_socket(P_desc) { check(false, "no descriptor closes"); }
static void say(P_char ch, const std::string &text)
{
    if (ch->desc) {
        ch->desc->queued.push_back(text);
        ch->desc->output.head = ch->desc;
    }
}
static int process_output(P_desc d)
{
    for (const auto &text : d->queued)
        d->wire.push_back(text);
    if (!d->queued.empty())
        d->wire.push_back("prompt");
    d->queued.clear();
    d->output.head = nullptr;
    return 0;
}
// Room.Info goes straight to the socket, so it must only be written while text drains.
void gmcp_room_info(P_char ch)
{
    check(in_output, "Room.Info written outside the output phase, ahead of queued text");
    ch->desc->wire.push_back("Room.Info " + std::to_string(ch->in_room));
}
static void gmcp_room_map(P_char) {}
static void do_look(P_char ch, char *, int) { say(ch, "look " + std::to_string(ch->in_room)); }
'''

DRIVER = r'''
static void room_entry_gmcp(P_char ch, int dir)
{
''' + entry + r'''
}

static void unlink(char_data &ch)
{
    for (P_char *link = &world[ch.in_room].people; *link; link = &(*link)->next_in_room)
        if (*link == &ch) {
            *link = ch.next_in_room;
            break;
        }
    ch.next_in_room = nullptr;
}
static void place(char_data &ch, int room)
{
    ch.in_room = room;
    ch.next_in_room = world[room].people;
    world[room].people = &ch;
}
// char_from_room()/char_to_room() around the production room-entry lines.
static void move(char_data &ch, int to)
{
    const int from = ch.in_room;
    for (P_char other = world[from].people; other; other = other->next_in_room)
        if (other != &ch)
            say(other, "leaves");
    gmcp_mark_room_dirty(from);
    unlink(ch);
    place(ch, to);
    for (P_char other = world[to].people; other; other = other->next_in_room)
        if (other != &ch)
            say(other, "arrives");
    room_entry_gmcp(&ch, 0);
}

static descriptor_data descriptors[4];
static char_data mover, watcher, leaver, switched;
static size_t seen[4];

static void output_phase(int tick)
{
    pulse = tick;
    in_output = true;
    game_loop_pulse_context context{static_cast<uint64_t>(tick)};
    run_output_phase(context);
    in_output = false;
    for (int i = 0; i < 4; ++i) {
        descriptor_data &d = descriptors[i];
        std::vector<std::string> chunk(d.wire.begin() + seen[i], d.wire.end());
        seen[i] = d.wire.size();
        if (chunk.empty())
            continue;
        int room = -1;
        for (char_data *ch : {&mover, &watcher, &leaver, &switched})
            if (ch->desc == &d)
                room = ch->in_room;
        const std::string where = "tick " + std::to_string(tick) + " descriptor " +
                                  std::to_string(i) + ": ";
        check(chunk.size() >= 3 && chunk[chunk.size() - 2] == "prompt" &&
                  chunk.back() == "Room.Info " + std::to_string(room),
              where + "text was not followed by its Room.Info in the same output phase");
        for (size_t j = 0; j + 1 < chunk.size(); ++j)
            check(chunk[j].rfind("Room.Info", 0) != 0, where + "Room.Info before text");
    }
}

int main()
{
    FD_ZERO(&output_set);
    char_data *characters[] = {&mover, &watcher, &leaver, &switched};
    for (int i = 0; i < 4; ++i) {
        descriptors[i].descriptor = 3 + i;
        descriptors[i].next = i < 3 ? &descriptors[i + 1] : nullptr;
        FD_SET(descriptors[i].descriptor, &output_set);
        characters[i]->desc = &descriptors[i];
    }
    descriptor_list = &descriptors[0];
    switched.npc = true; // A player switched into a mob still has a room panel.
    place(mover, 1);
    place(leaver, 1);
    place(watcher, 2);
    place(switched, 2);

    // Ticks 0-1: command-phase moves; ticks 2-3: event-phase moves; tick 4: an
    // event-phase move after a zone reset dirtied 600 empty rooms.
    for (int tick = 0; tick < 7; ++tick) {
        if (tick < 2)
            move(mover, mover.in_room == 1 ? 2 : 1);
        output_phase(tick);
        if (tick == 4)
            for (int room = 10; room < 610; ++room)
                gmcp_mark_room_dirty(room);
        if (tick >= 2 && tick <= 4)
            move(mover, mover.in_room == 1 ? 2 : 1);
    }
    for (int i = 0; i < 4; ++i)
        check(descriptors[i].queued.empty(), "text left undrained");
    check(watcher.desc->wire.size() == 15, "watcher saw every move");
    if (failures)
        return 1;
    std::puts("Room.Info follows its move text in the same output phase: command and "
              "event moves on both parities, mover, observers, switched body, 600 dirty rooms");
}
'''

parts = [PRELUDE, dirty_rooms, extract_function("comm.c", "static void run_output_phase("),
         DRIVER]

build_root = Path(os.environ.get("BIN_ROOT", ROOT / "bin")) / "tests"
build_root.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="room-info-order-", dir=build_root) as directory:
    harness = Path(directory) / "harness.cpp"
    binary = Path(directory) / "harness"
    harness.write_text("\n".join(parts), encoding="utf-8")
    subprocess.run([
        "g++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
        "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie",
        str(harness), "-o", str(binary),
    ], cwd=ROOT, check=True)
    subprocess.run([str(binary)], cwd=ROOT, check=True)
