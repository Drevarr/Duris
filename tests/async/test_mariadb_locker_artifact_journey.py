#!/usr/bin/env python3
"""An artifact stored in a locker keeps its real holder in tracking (issue #1064).

Staff give a mortal a unique artifact. The mortal leaves it in the locker, walks out,
comes back and takes it. Tracking must never name player 0 while the locker holds it,
the soul must stay with the mortal, and after the retrieval and a restart both the
tracking row and `arti unique` must name the mortal again.

Run against disposable MariaDB:
    tests/async/with_disposable_mariadb.sh \\
        python3 tests/async/test_mariadb_locker_artifact_journey.py --server bin/server/dms_new
"""

import argparse
import pathlib
import shutil
import tempfile
import time

import test_mariadb_combat_journey as journey
import test_mariadb_locker_journey as lockers
from test_flight_network_journey import command
from test_mariadb_locker_journey import add_lockers, boot, enter_locker, reenter_locker, stop

GOD, GOD_ACCOUNT = "Lockerwarden", "Lockerstaff"
PLAYER, ACCOUNT = "Lockerkeeper", "Lockerplayer"
RELIC = 3098
ON_PC, ON_GROUND = 3, 4

FIXTURE_RELIC = f"""#{RELIC}
relic unique fixture~
&+Wa fixture relic&N~
&+WA fixture relic lies here.&N~
~
5 6 3 8 7 0 268435456 8193 0 0 0
6 1 6 7 0 0 0 0
2 0 100
"""


def add_relic(run_root: pathlib.Path) -> None:
    objects = run_root / "areas_mini/mini.obj"
    text = objects.read_text()
    journey.require(f"#{RELIC}\n" not in text, "the fixture object number is taken")
    objects.write_text(text.replace("$~", FIXTURE_RELIC + "$~"))


def walk_out(client) -> None:
    """Staff pass the closed locker door; a mortal opens it first."""
    command(client, "open door")
    lockers.walk_out(client)


def run(binary: pathlib.Path) -> None:
    with tempfile.TemporaryDirectory(prefix="duris-locker-artifact-") as run_tmp, \
            journey.mariadb_authority() as (environment, sql):
        run_root = pathlib.Path(run_tmp)
        (run_root / "logs/log").mkdir(parents=True)
        journey.make_fixture(run_root)
        add_lockers(run_root)
        add_relic(run_root)
        journey.generate_certificate(run_root)
        (run_root / "bin/server").mkdir(parents=True)
        for name in ("dms", "dms_new"):
            shutil.copy2(binary, run_root / "bin/server" / name)
        binary = run_root / "bin/server/dms"
        (run_root / "journals/critical").mkdir(parents=True, mode=0o700)
        port, tls_port, websocket_port = journey.available_ports()
        environment.update(CRITICAL_COMMAND_JOURNAL_DIR=str(run_root / "journals/critical"),
                           DURIS_TLS_PORT=str(tls_port), DURIS_WEBSOCKET_PORT=str(websocket_port))

        def tracking():
            fields = sql("SELECT owned,loc_type,location,timer_epoch,bind_owner_pid "
                         f"FROM artifact_domain_state WHERE vnum={RELIC}")
            journey.require(fields != "", "the relic has no tracking row")
            return dict(zip(("owned", "type", "location", "timer", "soul"),
                            map(int, fields.split("\t"))))

        def settle(predicate, label):
            deadline = time.monotonic() + 30
            while not predicate(tracking()):
                journey.require(time.monotonic() < deadline, f"{label}: {tracking()}")
                time.sleep(0.2)
            return tracking()

        def login(name, account):
            client = journey.reconnect_character(port, expected_room=None, account=account,
                                                 character=name)
            client.expect("Welcome to Duris", timeout=60)
            command(client, "toggle paging no")
            return client

        process = boot(binary, run_root, environment, port)
        try:
            for name, account in ((GOD, GOD_ACCOUNT), (PLAYER, ACCOUNT)):
                client = journey.MudClient(port)
                journey.create_character(client, account=account, character=name,
                                         email=name.lower() + "@example.invalid")
                client.send("save")
                client.expect(f"Saving {name}.", timeout=30)
                client.close()
            stop(process)
            journey.make_overlord(sql, GOD)
            # Mortals use lockers only in towns; a racewar-neutral one may use the arena's.
            sql(f"UPDATE player_data SET platinum=100,racewar=4 WHERE name='{PLAYER}'")
            pid = int(sql(f"SELECT pid FROM player_data WHERE name='{PLAYER}'"))

            process = boot(binary, run_root, environment, port)
            god, player = login(GOD, GOD_ACCOUNT), login(PLAYER, ACCOUNT)
            command(god, "goto 22800")
            # Starting gear would leave no room to take the relic back.
            command(player, "remove all")
            command(player, "drop all")
            journey.require("You have created" in command(god, f"load obj {RELIC}"),
                            "staff could not load the relic")
            command(god, f"give relic {PLAYER}")
            journey.require("fixture relic" in command(player, "inventory"),
                            "the mortal did not receive the relic")
            held = settle(lambda row: row["type"] == ON_PC and row["location"] == pid,
                          "the mortal never became the tracked holder")
            journey.require(held["soul"] == pid, f"the relic did not bind to the mortal: {held}")

            enter_locker(player, 0)
            player.send("drop relic")
            player.expect("You drop", timeout=10)
            walk_out(player)
            # The locker's holder has no player identity: tracking keeps the last real
            # location, the soul stays with the mortal, and player 0 is never named.
            time.sleep(2)
            away = tracking()
            journey.require(not (away["type"] == ON_PC and away["location"] <= 0),
                            f"the locker published player 0: {away}")
            journey.require(away["type"] == ON_GROUND and away["soul"] == pid and
                            away["timer"] == held["timer"],
                            f"storing the relic changed its tracking: {away}")

            reenter_locker(player, 1, "")
            taken = command(player, "get relic")
            if "You get" not in taken:
                taken = command(player, "get relic chest")
            journey.require("You get" in taken, "the relic was not in the locker:\n" + taken)
            walk_out(player)
            # The reloaded relic must be the canonical body, or taking it changes nothing.
            back = settle(lambda row: row["type"] == ON_PC and row["location"] == pid,
                          "taking the relic back did not restore the holder")
            journey.require(back["soul"] == pid and back["timer"] == held["timer"],
                            f"the round trip changed the timer or soul: {back}")
            print("locker round trip kept the mortal as holder", flush=True)

            player.send("save")
            player.expect(f"Saving {PLAYER}.", timeout=30)
            god.close()
            player.close()
            stop(process)
            journey.require(tracking() == back, "shutdown changed the relic's tracking")

            process = boot(binary, run_root, environment, port)
            god, player = login(GOD, GOD_ACCOUNT), login(PLAYER, ACCOUNT)
            journey.require("fixture relic" in command(player, "inventory"),
                            "the relic did not survive the restart")
            report = command(god, "arti unique")
            journey.require(PLAYER in report and "Unknown" not in report,
                            "the unique report does not name the mortal:\n" + report)
            journey.require(tracking() == back, "logging in changed the relic's tracking")
            god.close()
            player.close()
            stop(process)
        except Exception:
            print((run_root / "server.out").read_text(errors="replace")[-8000:])
            raise
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", type=pathlib.Path, required=True)
    run(parser.parse_args().server.resolve())
    print("locker artifact journey passed")
