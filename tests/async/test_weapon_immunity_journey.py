#!/usr/bin/env python3
"""Real-server weapon immunity message (issue #1124).

A non-magic dagger, swung or thrown at a weapon-immune demon, must say it
passes harmlessly through instead of vanishing or showing an ordinary hit:
on heavy armor that rounds its token damage away, and on light armor where
the damage lands.
Runs an isolated server on disposable MariaDB, like the Assassin journey.
"""

import argparse
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time

import test_mariadb_combat_journey as journey
from test_assassin_combat_journey import spell_id
from test_flight_network_journey import command

ROOT = journey.ROOT
ACTORS = (("Wardkeeper", "Wardstaff"), ("Ironblade", "Ironrogue"))
# Level 45 demons, so weapon immune. The minimal world makes them invisible.
DEMONS = {
    "warrior": ("65544 0 0 138 2048 0 0 0 S\nX 0 1 -1\n45 80 0 5000d1+1 4d8+45\n", 31, -250),
    "cleric": ("65544 0 0 138 2048 0 0 0 S\nX 0 32 -1\n45 80 0 5000d1+1 4d4+30\n", 30, 250),
}
OBJECTS = """#22810
journeydagger dagger~
a journey dagger~
A small journey dagger rests here.~
~
5 11 2 3 7 0 0 8193 0 0 0
2 1 4 11 0 0 0 0
2 100 100
#22812
journeydart dart~
a journey dart~
A small journey dart rests here.~
~
7 11 2 3 7 0 256 8193 0 0 0
0 1 4 6 0 0 0 0
2 100 100
"""


def fixture(runtime):
    journey.make_fixture(runtime)
    journey.generate_certificate(runtime)
    zone = runtime / "areas_mini/mini.zon"
    zone.write_text(re.sub(r"^[MG] .*\n", "", zone.read_text(), flags=re.M))
    # Make each demon visible and give it the armor its case needs.
    mobs = runtime / "areas_mini/mini.mob"
    for text, _, armor in DEMONS.values():
        assert mobs.read_text().count(text) == 1, text
        visible = text.replace(" 138 ", " 0 ").replace("45 80 0 ", f"45 80 {armor} ")
        mobs.write_text(mobs.read_text().replace(text, visible))
    objects = runtime / "areas_mini/mini.obj"
    objects.write_text(objects.read_text().replace("$~", OBJECTS + "$~"))


def seed_actors(sql):
    skills = [spell_id("SKILL_" + name) for name in ("1H_PIERCING", "RANGE_WEAPONS", "DARTS")]
    stats = ",".join(f"base_{stat}=100" for stat in
                     ("str", "dex", "agi", "con", "pow", "int", "wis", "luk"))
    statements = []
    for pid, classes, spec, level in ((1, 1, 0, 62), (2, 1 << 12, 1, 50)):
        statements.append(f"UPDATE player_data SET m_class={classes},spec={spec},level={level},"
                          f"highest_level={level},base_hit=10000,hit_diff=0,{stats},"
                          f"last_room=22800 WHERE pid={pid}")
    statements.append("DELETE FROM player_skills WHERE pid=2")
    statements += [f"INSERT INTO player_skills(pid,skill_id,learned,taught) VALUES(2,{skill},100,100)"
                   for skill in skills]
    sql(";".join(statements))


def run(binary):
    with tempfile.TemporaryDirectory(prefix="weapon-immunity-", dir=ROOT / "bin/tests") as temporary, \
            journey.mariadb_authority() as (authority, sql):
        runtime = Path(temporary)
        fixture(runtime)
        (runtime / "logs/log").mkdir(parents=True)
        critical = runtime / "journals/critical"
        critical.mkdir(parents=True, mode=0o700)
        (runtime / "journals/players").mkdir(mode=0o700)
        plain, tls, websocket = journey.available_ports()
        environment = dict(authority, CRITICAL_COMMAND_JOURNAL_DIR=str(critical),
                           DURIS_TLS_PORT=str(tls), DURIS_WEBSOCKET_PORT=str(websocket))
        process = None
        clients = []
        output_path = runtime / "server.out"
        with output_path.open("w") as output:
            def boot():
                nonlocal process
                offset = output_path.stat().st_size
                process = subprocess.Popen([str(binary), "--minimal", "-s", "-d", str(runtime), str(plain)],
                                           cwd=runtime, env=environment, stdout=output, stderr=subprocess.STDOUT)
                deadline = time.monotonic() + 120
                while "Entering game loop." not in output_path.read_text(errors="replace")[offset:]:
                    assert process.poll() is None and time.monotonic() < deadline, "isolated boot failed"
                    time.sleep(.1)

            def stop():
                for client in clients:
                    client.close()
                clients.clear()
                if process is not None and process.poll() is None:
                    process.send_signal(signal.SIGTERM)
                    process.wait(timeout=30)
                    assert process.returncode == 0, "isolated server shutdown failed"

            def login(name, account):
                client = journey.reconnect_character(plain, expected_room=None, account=account, character=name)
                clients.append(client)
                client.expect("Welcome to Duris", timeout=30)
                client.expect_any(("Pos: standing >", "<>"), timeout=20)
                command(client, "toggle paging no")
                return client

            def attack(staff, fighter, text, target):
                """Repeat one attack until a blow lands; return the fighter's new text."""
                for _ in range(48):
                    command(fighter, "wake")
                    command(fighter, "stand")
                    staff_before, fighter_before = len(staff.transcript), len(fighter.transcript)
                    command(fighter, text)
                    time.sleep(1)
                    assert "monotone" in command(staff, "tranquilize Ironblade")
                    command(staff, "tranquilize " + target)
                    seen = bytes(fighter.transcript[fighter_before:]).decode(errors="replace")
                    watched = bytes(staff.transcript[staff_before:]).decode(errors="replace")
                    if "seems to pass harmlessly through" in seen:
                        assert "seems to pass harmlessly through" in watched, watched
                        assert "You hit" not in seen, seen
                        return seen
                raise AssertionError(text + " never landed a blow")

            try:
                boot()
                for name, account in ACTORS:
                    client = journey.MudClient(plain)
                    clients.append(client)
                    journey.create_character(client, account=account, character=name,
                                             email=name.lower() + "@example.invalid")
                    client.send("save")
                    client.expect("Saving " + name + ".")
                stop()
                seed_actors(sql)
                boot()
                staff, fighter = (login(*actor) for actor in ACTORS)
                command(staff, "trans Ironblade")
                for vnum, keyword in ((22810, "journeydagger"), (22812, "journeydart")):
                    assert "created" in command(staff, f"load obj {vnum}")
                    assert "Ok." in command(staff, f"give {keyword} Ironblade")
                command(fighter, "remove all")
                assert "You wield" in command(fighter, "wield journeydagger")
                for target, (_, vnum, armor) in DEMONS.items():
                    assert "demon" in command(staff, f"load mob {vnum}").lower()
                    swing = attack(staff, fighter, "hit " + target, target)
                    # raw_damage() frames a landed blow; on heavy armor hit() sends the line itself.
                    landed = "-=[Your journey dagger seems" in swing
                    assert "Your journey dagger seems" in swing and landed == (armor > 0), swing
                    if "journeydart" not in command(fighter, "inventory"):
                        command(fighter, "get journeydart")
                    assert "Your journey dart seems" in attack(
                        staff, fighter, "throw journeydart " + target, target)
                    command(staff, "purge " + target)
                    print(f"Melee and thrown blows pass harmlessly through the {target}"
                          f" at armor {armor}", flush=True)
                # Terse mode hides the line that stands in for a blow armor rounds away, as it
                # hides hit messages; the staff observer, not terse, still sees the blow.
                assert "demon" in command(staff, f"load mob {DEMONS['warrior'][1]}").lower()
                command(fighter, "toggle terse")
                for _ in range(48):
                    command(fighter, "wake")
                    command(fighter, "stand")
                    staff_before, fighter_before = len(staff.transcript), len(fighter.transcript)
                    command(fighter, "hit warrior")
                    time.sleep(1)
                    command(staff, "tranquilize Ironblade")
                    command(staff, "tranquilize warrior")
                    watched = bytes(staff.transcript[staff_before:]).decode(errors="replace")
                    if "seems to pass harmlessly through" in watched:
                        seen = bytes(fighter.transcript[fighter_before:]).decode(errors="replace")
                        assert "seems to pass harmlessly through" not in seen, seen
                        break
                else:
                    raise AssertionError("the terse fighter's blow never landed")
                print("Terse mode hides the harmless blow from the terse fighter", flush=True)
                stop()
            except Exception:
                print(output_path.read_text(errors="replace")[-5000:])
                print(journey.runtime_logs(runtime)[-8000:])
                for client in clients:
                    print(client.transcript.decode(errors="replace")[-5000:])
                raise
            finally:
                stop()


def main():
    (ROOT / "bin/tests").mkdir(parents=True, exist_ok=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", type=Path, required=True)
    run(parser.parse_args().server.resolve())


if __name__ == "__main__":
    main()
