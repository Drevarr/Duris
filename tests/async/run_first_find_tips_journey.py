#!/usr/bin/env python3
"""Show first-find tips through a real server on disposable MariaDB.

A new character sees each tip once, the choice survives a restart, and a
character from before the tips sees none. Never reads .env or connects to an
existing game.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile
import time

import test_mariadb_combat_journey as journey
from test_flight_network_journey import authority, command

ROOT = journey.ROOT
STAFF, NEWBIE, VETERAN = "Tipwarden", "Tipnewbie", "Tipveteran"
ANSI = re.compile(r"\x1b\[[0-9;]*m")
FISH, SCALE = "Fresh Fish", "Dragon Scale"


def plain(text):
    return ANSI.sub("", text)


def run(binary):
    with tempfile.TemporaryDirectory(prefix="first-find-tips-", dir=ROOT / "bin/tests") as temporary:
        runtime = Path(temporary)
        journey.make_fixture(runtime)
        journey.generate_certificate(runtime)
        (runtime / "help").symlink_to(ROOT / "help", target_is_directory=True)
        (runtime / "logs/log").mkdir(parents=True)
        (runtime / "journals/critical").mkdir(parents=True, mode=0o700)
        plain_port, tls, websocket = journey.available_ports()
        clients, process = [], None
        output_path = runtime / "server.out"
        with authority("mariadb", runtime) as (env, sql), output_path.open("w") as output:
            env.update(CRITICAL_COMMAND_JOURNAL_DIR=str(runtime / "journals/critical"),
                       DURIS_TLS_PORT=str(tls), DURIS_WEBSOCKET_PORT=str(websocket),
                       MAINTENANCE_STATE_FILE=str(runtime / "maintenance.state"))

            def boot():
                offset = output_path.stat().st_size
                proc = subprocess.Popen([str(binary), "--minimal", "-d", str(runtime), str(plain_port)],
                                        cwd=runtime, env=env, stdout=output, stderr=subprocess.STDOUT)
                deadline = time.monotonic() + 90
                while b"Entering game loop." not in output_path.read_bytes()[offset:]:
                    assert proc.poll() is None and time.monotonic() < deadline, output_path.read_text()[-6000:]
                    time.sleep(.1)
                return proc

            def stop():
                for client in clients:
                    client.close()
                clients.clear()
                if process and process.poll() is None:
                    process.terminate()
                    process.wait(timeout=60)
                    assert process.returncode == 0

            def login(name):
                client = journey.reconnect_character(plain_port, expected_room=None, account=name, character=name)
                clients.append(client)
                client.expect_any(("Pos: standing >", "<>"), timeout=30)
                command(client, "toggle paging off")
                return client

            def handed(staff, receiver, name, vnum, keyword):
                command(staff, f"goto {name}")
                assert "You have created" in plain(command(staff, f"load obj {vnum}"))
                start = len(receiver.transcript)
                given = plain(command(staff, f"give {keyword} {name}"))
                assert "Ok." in given, given
                command(receiver, "look")
                return plain(bytes(receiver.transcript[start:]).decode(errors="replace"))

            def tips(name):
                return int(sql(f"SELECT first_find_tips FROM player_data WHERE name='{name}'"))

            try:
                process = boot()
                for name in (STAFF, NEWBIE, VETERAN):
                    client = journey.MudClient(plain_port)
                    clients.append(client)
                    journey.create_character(client, expected_room=None, account=name, character=name,
                                             email=name.lower() + "@example.invalid")
                    command(client, "save")
                    client.send("quit")
                    client.expect("ACCOUNT MENU", timeout=30)
                    client.close()
                    clients.remove(client)
                stop()
                assert tips(NEWBIE) == 0
                journey.make_overlord(sql, STAFF)
                # Stand in for a character saved before the tips existed.
                sql(f"UPDATE player_data SET first_find_tips=18446744073709551615 WHERE name='{VETERAN}'")

                process = boot()
                staff, newbie, veteran = (login(name) for name in (STAFF, NEWBIE, VETERAN))
                text = handed(staff, newbie, NEWBIE, 293, "bass")
                assert "First find: " + FISH in text and "this tip shows once" in text, text
                assert "><(((o>" in text and "See: help fishing" in text, text
                text = handed(staff, newbie, NEWBIE, 392, "scale")
                assert "First find: " + SCALE in text, text
                text = handed(staff, newbie, NEWBIE, 293, "bass")
                assert "First find" not in text, text
                command(newbie, "drop bass")
                text = plain(command(newbie, "get bass"))
                assert "First find" not in text, text
                print("PASS: a new character sees each tip once", flush=True)

                text = handed(staff, veteran, VETERAN, 293, "bass")
                assert "First find" not in text, text
                print("PASS: a character from before the tips sees none", flush=True)

                command(newbie, "save")
                stop()
                assert tips(NEWBIE) == (1 << 11) | (1 << 8), tips(NEWBIE)
                process = boot()
                staff, newbie = login(STAFF), login(NEWBIE)
                for vnum, keyword in ((293, "bass"), (392, "scale")):
                    text = handed(staff, newbie, NEWBIE, vnum, keyword)
                    assert "First find" not in text, text
                text = handed(staff, newbie, NEWBIE, 800, "grub")
                assert "First find: Foraged Goods" in text, text
                print("PASS: seen tips survive a restart; unseen ones still show", flush=True)
                stop()
            except BaseException:
                for client in clients:
                    print(bytes(client.transcript).decode(errors="replace")[-6000:])
                print(output_path.read_text(errors="replace")[-6000:])
                raise
            finally:
                stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", type=Path, required=True)
    run(parser.parse_args().server.resolve())
