#!/usr/bin/env python3
"""Let bots play the full world for a while and fail on any crash or sanitizer report.

    tests/async/with_disposable_mariadb.sh \
        python3 tests/scenarios/soak.py --server bin/server/dms_san --minutes 30 --bots 6

Usually started through `scripts/mudtest soak`. Build the server with scripts/build-san.sh
so memory errors are reported, not just crashes. Each bot is a level-56, high-HP character
that wanders, fights whatever it finds, casts its class's spells (clerics and paladins pray
first; druids and rangers cast from their top two circles), loots, wears gear,
shops where `list` answers, rests and reconnects. Bots go in pairs, one following and grouped
with the other. A staff character runs a copyover halfway through. The run fails if the
server dies, does not shut down cleanly, or its output holds a sanitizer or crash report; it
prints how often each behaviour succeeded, so a run shows it really cast, grouped and shopped.
"""

from __future__ import annotations

import argparse
import pathlib
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/async"))
sys.path.insert(0, str(ROOT / "tests/scenarios"))

import test_mariadb_combat_journey as journey  # noqa: E402
from run_scenarios import CRASH_MARKERS, Actor, define, seed  # noqa: E402

# Book casters (sorcerer and the like) are left out until the bots get spellbooks.
CLASSES = ("WARRIOR", "CLERIC", "DRUID", "RANGER", "PALADIN", "ROGUE", "MONK", "DRUID")
PRAYING = {"CLERIC", "PALADIN"}
# A shop's `list` answers with a table; anywhere else it is refused.
NO_SHOP = ("can't", "cannot", "Huh", "not here", "no one", "nobody")
DIRECTIONS = ("north", "south", "east", "west", "up", "down")
IDLE = ("look", "score", "inventory", "equipment", "who", "affects", "time", "consider all")
SKIP_WORDS = {"the", "a", "an", "is", "are", "here", "standing", "sitting", "resting",
              "sleeping", "of", "and", "with", "in", "on", "its", "his", "her", "their"}


def class_spells() -> dict[str, list[tuple[int, str]]]:
    """(circle, spell name) per class from skills.c. Only SPELL_ADD counts: a SPEC_SPELL_ADD
    spell needs a specialization the bots do not have."""
    spells: dict[str, set[tuple[int, str]]] = {}
    current = None
    # Commented-out declarations are spells the class cannot cast.
    source = (ROOT / "src/classes/skills.c").read_text(errors="replace")
    source = re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", source, flags=re.S))
    for line in source.splitlines():
        if match := re.search(r'SPELL_CREATE\w*\(\s*"([^"]+)"', line):
            current = match[1]
        elif re.search(r"(SKILL|SONG|TAG|POISON)_CREATE", line):
            current = None
        elif current and (match := re.search(r"\bSPELL_ADD\(\s*CLASS_([A-Z_]+)\s*,\s*(\d+)", line)):
            spells.setdefault(match[1], set()).add((int(match[2]), current))
    return {name: sorted(names) for name, names in spells.items()}


SPELLS = class_spells()


def tharnadia_shop_rooms() -> list[int]:
    """Rooms of the shops in Tharnadia, where the bots start (areas/world.shp, wld/tharnadia.wld)."""
    rooms = {int(v) for v in re.findall(r"(?m)^#(\d+)", (ROOT / "areas/wld/tharnadia.wld").read_text(errors="replace"))}
    found = []
    for body in re.split(r"(?m)^#\d+~\n", (ROOT / "areas/world.shp").read_text(errors="replace"))[1:]:
        # After the shop's seven messages come temper, temper, keeper, with_who and its room.
        after_messages = re.split(r"~\n", body, maxsplit=7)[7].split()
        if len(after_messages) > 4 and int(after_messages[4]) in rooms:
            found.append(int(after_messages[4]))
    return found


# Success messages per behaviour, so a run shows its new actions really happened.
OUTCOMES = {
    "cast started": ("You start chanting", "You call forth your prepared spell"),
    "followed": ("You now follow",),
    "joined a group": ("is now a member of", "joins your group"),
    "bought": ("You now have",),
    "sold": ("The shopkeeper gives you",),
    "prayed": ("Your prayers are complete",),
}
tally: dict[str, int] = {}
tally_lock = threading.Lock()


def room_targets(text: str) -> list[str]:
    """Keyword guesses for whatever stands in the room, from the lines of a `look`."""
    words = []
    for line in text.splitlines():
        if "Soak" in line:  # the other bots and staff: fight the world, not each other
            continue
        if re.search(r"\b(is|are|stands?|sits?|rests?|floats?|lies|hovers?)\b.*here", line):
            words += [w for w in re.findall(r"[a-z]{3,}", line.lower()) if w not in SKIP_WORDS]
    return words


class Bot(threading.Thread):
    def __init__(self, actor: Actor, port: int, deadline: float, pause: threading.Event,
                 errors: list[str], class_name: str, leader: str | None, keep: pathlib.Path | None):
        super().__init__(daemon=True)
        self.actor, self.port, self.deadline, self.pause, self.errors = actor, port, deadline, pause, errors
        self.class_name, self.leader, self.keep = class_name, leader, keep
        circles = SPELLS.get(class_name, [])
        self.spells = [name for _, name in circles]
        # Slot casters cast from their two highest circles.
        top = max((circle for circle, _ in circles), default=0)
        self.top_spells = [name for circle, name in circles if circle >= top - 1] or self.spells
        self.target = None
        self.commands = 0
        self.random = random.Random(actor.name)

    def connect(self):
        client = journey.reconnect_character(self.port, expected_room=None,
                                             account=self.actor.account, character=self.actor.name)
        client.expect_any(("Pos: ", "<>"), timeout=60)
        client.send("toggle paging no")
        if self.leader:
            # The leader's `group all` needs the follower's consent first.
            client.send("follow " + self.leader)
            client.send("consent " + self.leader)
        else:
            self.maybe_shop(client)  # leaders start in a shop
        return client

    def act(self, client, command: str) -> str:
        start = len(client.transcript)
        client.send(command)
        self.commands += 1
        end = time.monotonic() + 0.4
        while time.monotonic() < end:
            client._receive()
        text = bytes(client.transcript[start:]).decode(errors="replace")
        with tally_lock:
            tally[command.split()[0]] = tally.get(command.split()[0], 0) + 1
        for prompt in ("PRESS RETURN", "Press return", "[Hit Return]"):
            if prompt in text:
                client.send("")
        return text

    def close(self, client):
        """Count each outcome over the whole connection: some answers arrive late (a purchase
        is confirmed after it is saved) or between commands."""
        try:
            client._receive()
        except AssertionError:  # the server already closed it; count what arrived
            pass
        text = bytes(client.transcript).decode(errors="replace")
        if self.keep:
            with (self.keep / f"{self.actor.name}.txt").open("a") as saved:
                saved.write(text)
        with tally_lock:
            for outcome, markers in OUTCOMES.items():
                tally[outcome] = tally.get(outcome, 0) + sum(text.count(m) for m in markers)
        client.close()

    def cast(self, client, target: str, spell: str | None = None):
        if spell is None:
            pool = self.spells if self.class_name in PRAYING else self.top_spells
            spell = self.random.choice(pool)
        self.act(client, f"cast '{spell}' {target}")

    def prepare(self, client):
        """A praying class prays for one spell while resting, then casts it."""
        if self.class_name not in PRAYING:
            return
        spell = self.random.choice(self.spells)
        self.act(client, "rest")
        start = len(client.transcript)
        self.act(client, "pray " + spell)
        deadline = time.monotonic() + 30
        while (b"Your prayers are complete" not in client.transcript[start:]
               and time.monotonic() < deadline):
            client._receive()
        self.act(client, "stand")
        self.cast(client, self.target or "me", spell)

    def maybe_shop(self, client):
        listed = self.act(client, "list")
        if any(word in listed for word in NO_SHOP):
            return
        with tally_lock:
            tally["shop found"] = tally.get("shop found", 0) + 1
        carried = [line for line in self.act(client, "inventory").splitlines() if "carrying" not in line]
        inventory = [w for w in re.findall(r"[a-z]{3,}", "\n".join(carried).lower()) if w not in SKIP_WORDS]
        if inventory:
            item = self.random.choice(inventory)
            self.act(client, "value " + item)
            self.act(client, "sell " + item)
        choice = "buy " + self.random.choice(("1", "2", "3"))
        # Looting fills the bots' packs; make room rather than be refused every time.
        if "can't carry" in self.act(client, choice):
            self.act(client, "drop all")
            self.act(client, choice)

    def run(self):
        client = None
        try:
            client = self.connect()
            while time.monotonic() < self.deadline:
                if self.pause.is_set():
                    self.close(client)
                    client = None
                    while self.pause.is_set():
                        time.sleep(1)
                    client = self.connect()
                # A leader regroups now and then: its follower may have just (re)joined.
                if not self.leader and self.commands % 40 == 0:
                    self.act(client, "group all")
                roll = self.random.random()
                if roll < 0.30:
                    # Followers mostly move with their leader.
                    if not self.leader or self.random.random() < 0.2:
                        self.act(client, self.random.choice(DIRECTIONS))
                        if self.random.random() < 0.15:
                            self.maybe_shop(client)
                elif roll < 0.55:
                    looked = self.act(client, "look")
                    targets = room_targets(looked)
                    if targets:
                        self.target = self.random.choice(targets)
                        self.act(client, "kill " + self.target)
                        for _ in range(self.random.randint(2, 6)):
                            if self.spells and self.class_name not in PRAYING and self.random.random() < 0.5:
                                self.cast(client, self.target)
                            else:
                                self.act(client, self.random.choice(("kick", "bash", "score", "look")))
                elif roll < 0.65 and self.spells:
                    # Praying classes cast what they just prayed for; slot casters cast directly.
                    if self.class_name in PRAYING:
                        self.prepare(client)
                    else:
                        self.cast(client, "me")
                elif roll < 0.67:
                    self.act(client, self.random.choice(("group all", "group", "follow " + (self.leader or "self"))))
                elif roll < 0.70:
                    self.act(client, "get all")
                    self.act(client, "get all corpse")
                    self.act(client, "wear all")
                elif roll < 0.78:
                    self.act(client, self.random.choice(("rest", "sit", "stand", "sleep", "wake", "stand")))
                elif roll < 0.80:
                    self.act(client, "save")
                elif roll < 0.81:
                    client.send("quit")
                    time.sleep(2)
                    self.close(client)
                    client = self.connect()
                else:
                    self.act(client, self.random.choice(IDLE))
        except Exception as error:  # a dead server shows up here first
            self.errors.append(f"{self.actor.name}: {error!r}")
        finally:
            if client is not None:
                self.close(client)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server", type=pathlib.Path, required=True)
    parser.add_argument("--minutes", type=float, default=20)
    parser.add_argument("--bots", type=int, default=6)
    parser.add_argument("--keep", type=pathlib.Path,
                        help="copy the server output, logs and each bot's transcript here")
    args = parser.parse_args()
    binary = args.server.resolve()
    (ROOT / "bin/tests").mkdir(parents=True, exist_ok=True)

    actors = {"Soakstaff": Actor("Soakstaff", level=62)}
    for n in range(args.bots):
        name = "Soakbot" + "abcdefghijklmnopqrstuvwxyz"[n]
        actors[name] = Actor(name, classes=define("CLASS_" + CLASSES[n % len(CLASSES)]), level=56)

    with tempfile.TemporaryDirectory(prefix="soak-", dir=ROOT / "bin/tests") as temporary, \
            journey.mariadb_authority() as (authority, sql):
        runtime = pathlib.Path(temporary)
        for directory in ("areas", "areas_mini", "docs", "help"):
            (runtime / directory).symlink_to(ROOT / directory, target_is_directory=True)
        shutil.copytree(ROOT / "lib", runtime / "lib")
        journey.generate_certificate(runtime)
        # Copyover promotes a staged bin/server/dms_new over the running bin/server/dms.
        (runtime / "bin/server").mkdir(parents=True)
        shutil.copy2(binary, runtime / "bin/server/dms_new")
        binary = shutil.copy2(binary, runtime / "bin/server/dms")
        (runtime / "logs/log").mkdir(parents=True)
        critical = runtime / "journals/critical"
        critical.mkdir(parents=True, mode=0o700)
        (runtime / "journals/players").mkdir(mode=0o700)
        plain, tls, websocket = journey.available_ports()
        environment = dict(authority, CRITICAL_COMMAND_JOURNAL_DIR=str(critical),
                           DURIS_TLS_PORT=str(tls), DURIS_WEBSOCKET_PORT=str(websocket),
                           ASAN_OPTIONS="detect_leaks=0:abort_on_error=0",
                           UBSAN_OPTIONS="print_stacktrace=1")
        output_path = runtime / "server.out"
        output = output_path.open("a")
        process = None
        failures: list[str] = []

        def boot():
            nonlocal process
            offset = output_path.stat().st_size
            process = subprocess.Popen([str(binary), "-d", str(runtime), str(plain)], cwd=runtime,
                                       env=environment, stdout=output, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 900
            while "Entering game loop." not in output_path.read_text(errors="replace")[offset:]:
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("full-world server did not boot")
                time.sleep(1)

        def stop():
            if process is not None and process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=300)
                except subprocess.TimeoutExpired:
                    # Never release the schema or runtime directory under a live server.
                    process.kill()
                    process.wait()
                    failures.append("server ignored SIGTERM for 300s and was killed")
                    return
                if process.returncode != 0:
                    failures.append(f"server exited {process.returncode} on shutdown")

        try:
            boot()
            print("full world booted; creating characters", flush=True)
            for actor in actors.values():
                client = journey.MudClient(plain)
                # Tharnadia, not the sealed Beginner Introduction the helper prefers.
                journey.create_character(client, expected_room=None, account=actor.account,
                                         character=actor.name, email=actor.name.lower() + "@example.invalid",
                                         hometown="T", expected_hometown="Tharnadia")
                client.send("save")
                client.expect("Saving " + actor.name + ".", timeout=60)
                client.close()
            stop()
            seed(sql, actors)
            # High HP keeps them alive; coins let them buy where `list` finds a shop.
            sql("UPDATE player_data SET base_hit=10000,hit_diff=0,platinum=1000 WHERE name LIKE 'Soakbot%'")
            # Each pair starts in a shop, so the follower can follow and the leader can buy.
            shops = tharnadia_shop_rooms()
            names = [name for name in actors if name != "Soakstaff"]
            for n, name in enumerate(names):
                if shops:
                    sql(f"UPDATE player_data SET last_room={shops[n // 2 % len(shops)]} WHERE name='{name}'")
            boot()
            print(f"soaking {args.bots} bots for {args.minutes} minutes", flush=True)
            deadline = time.monotonic() + args.minutes * 60
            pause, errors = threading.Event(), []
            # Pairs: every second bot follows the one before it, which groups it.
            if args.keep:
                args.keep.mkdir(parents=True, exist_ok=True)
            bots = [Bot(actors[name], plain, deadline, pause, errors, CLASSES[n % len(CLASSES)],
                        names[n - 1] if n % 2 else None, args.keep)
                    for n, name in enumerate(names)]
            for bot in bots:
                bot.start()
            time.sleep(args.minutes * 30)
            if process.poll() is None:
                pause.set()
                time.sleep(3)
                staff = journey.reconnect_character(plain, expected_room=None,
                                                    account=actors["Soakstaff"].account, character="Soakstaff")
                staff.expect_any(("Pos: ", "<>"), timeout=60)
                offset = output_path.stat().st_size
                staff.send("copyover")
                rebooted = time.monotonic() + 900
                while "Entering game loop." not in output_path.read_text(errors="replace")[offset:]:
                    if process.poll() is not None or time.monotonic() > rebooted:
                        raise RuntimeError("server did not come back from copyover")
                    time.sleep(1)
                staff.close()
                print("copyover done; bots resume", flush=True)
                pause.clear()
            for bot in bots:
                bot.join()
            if process.poll() is not None:
                failures.append(f"server died during the soak (exit {process.returncode})")
            failures += errors
            print(f"bots sent {sum(bot.commands for bot in bots)} commands", flush=True)
            print("outcomes: " + ", ".join(f"{name} {tally.get(name, 0)}" for name in OUTCOMES) +
                  f" (cast sent {tally.get('cast', 0)}, kill sent {tally.get('kill', 0)}, "
                  f"list sent {tally.get('list', 0)}, shop found {tally.get('shop found', 0)})", flush=True)
        except Exception as error:
            failures.append(f"soak aborted: {error!r}")
        finally:
            stop()  # here, so Ctrl-C also stops the server before the fixtures go
            output.close()
            logs = output_path.read_text(errors="replace") + journey.runtime_logs(runtime)
            found = [marker for marker in CRASH_MARKERS if marker in logs]
            if found:
                reports = sorted({line.strip() for line in logs.splitlines()
                                  if any(marker in line for marker in found)})
                failures.append(f"server output reports {', '.join(found)}:\n  " + "\n  ".join(reports[:10]))
            if args.keep:
                args.keep.mkdir(parents=True, exist_ok=True)
                shutil.copy2(output_path, args.keep / "server.out")
                shutil.copytree(runtime / "logs", args.keep / "logs", dirs_exist_ok=True)
        for failure in failures:
            print("FAIL", failure, flush=True)
        print("soak passed" if not failures else f"soak failed ({len(failures)} problem(s))")
        return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
