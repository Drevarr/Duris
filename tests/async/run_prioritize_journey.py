#!/usr/bin/env python3
"""Prioritize through Telnet, normal preparation and a disposable MariaDB restart."""
import argparse
from contextlib import closing, contextmanager
from pathlib import Path
import re

import test_mariadb_combat_journey as journey
from run_battleprep_journey import preparation, subscribe_preparation, support_preparation
from test_account_recovery_journey import IsolatedServer
from test_creation_prompt_journey import reboot
from test_flight_network_journey import command
from test_gmcp_control_journey import telnet_packets
from test_minor_creation_instrument_journey import spell_id


CLERIC, SHAMAN = "Eldara", "Silwen"


@contextmanager
def login(server, name):
    with closing(journey.reconnect_character(server.plain_port, expected_room=None,
                                             account=name, character=name)) as client:
        prompt, _ = client.expect_any(("PRESS RETURN", "Pos: standing >"))
        if prompt == "PRESS RETURN":
            client.send("")
            client.expect("Pos: standing >")
        yield client


def save_and_quit(client, name):
    client.send("save")
    client.expect(f"Saving {name}.")
    client.send("quit")
    client.expect("ACCOUNT MENU", timeout=30)


def queue(client, verb, expected):
    text = command(client, verb)
    queued = re.findall(r"seconds:\s+\(\s*\d+\w+\) ([\w ]+?)[ \t]*[\r\n]", text)
    assert queued == expected, (queued, text)
    return text


def run(binary):
    def prepare(root):
        properties = root / "lib/duris.properties"
        properties.write_text(properties.read_text().replace("camp.timer=9.000", "camp.timer=1.000"))
        journey.import_help(root, env)

    with journey.mariadb_authority() as (env, sql), IsolatedServer(binary, env, prepare) as server:
        for name in (CLERIC, SHAMAN):
            print(f"Creating {name}", flush=True)
            with closing(journey.MudClient(server.plain_port)) as client:
                journey.create_character(client, expected_room=None, account=name, character=name,
                                         email=f"{name.lower()}@example.invalid")
                client.send("save")
                client.expect(f"Saving {name}.")

        server.shutdown()
        # Minimal-world room 14 permits casting and camping. Players queue every spell.
        for name, cls in ((CLERIC, 1 << 5), (SHAMAN, 1 << 8)):
            sql(f"UPDATE player_data SET m_class={cls}, secondary_class=0, spec=0, level=21, "
                f"highest_level=21, base_wis=60, played_time=200000, last_room=14 WHERE name='{name}'")
        reboot(server)

        print("Checking memorization", flush=True)
        with login(server, SHAMAN) as client:
            rest = command(client, "rest")
            assert "You sit down and relax" in rest, rest
            for spell in ("flameburst", "spirit armor"):
                text = command(client, "memorize " + spell)
                assert "You are memorizing " + spell in text, text
            text = command(client, "prioritize spirit armor")
            assert "1 pending copy of spirit armor" in text, text
            queue(client, "memorize", ["spirit armor", "flameburst"])
            command(client, "stand")

        print("Checking prayer", flush=True)
        with login(server, CLERIC) as client:
            command(client, "toggle page off")
            text = command(client, "help prioritize")
            assert "Move every pending copy" in text and "prio full heal" in text, text
            support_preparation(client)
            subscribe_preparation(client)
            preparation(client, 0, "complete")
            rest = command(client, "rest")
            assert "You sit down and relax" in rest, rest
            for spell in ("cure serious", "bless", "bless"):
                text = command(client, "pray " + spell)
                assert "You are praying for " + spell in text, text
            before_switch = len(telnet_packets(client))
            text = command(client, "prio BlEsS")
            assert "2 pending copies of bless" in text and "restarts your preparation time" in text, text
            assert preparation(client, before_switch, "active")["estimatedSeconds"] > 0
            queue(client, "pray", ["bless", "bless", "cure serious"])

            # The game must actually finish the promoted spell before the original head.
            matched, _ = client.expect_any(("finished praying for bless", "finished praying for cure serious"),
                                           timeout=120)
            assert matched.endswith("bless"), matched
            before_pause = len(telnet_packets(client))
            command(client, "stand")
            assert preparation(client, before_pause, "paused")["estimatedSeconds"] > 0
            text = command(client, "prio cure serious")
            assert "1 pending copy of cure serious" in text, text
            text = queue(client, "pray", ["cure serious", "bless"])
            assert re.search(r"\)\s+1 - bless\b", text), text
            save_and_quit(client, CLERIC)

        server.shutdown()
        def saved_slots():
            return sql(f"SELECT modifier,(flags & 16)<>0 FROM player_affects JOIN player_data USING(pid) "
                       f"WHERE name='{CLERIC}' AND type={spell_id('TAG_MEMORIZE')} ORDER BY player_affects.id")
        bless, cure = spell_id("SPELL_BLESS"), spell_id("SPELL_CURE_SERIOUS")
        assert saved_slots().splitlines() == [f"{bless}\t1", f"{cure}\t0", f"{bless}\t0"]

        reboot(server)
        print("Checking restart, casting and resume", flush=True)
        with login(server, CLERIC) as client:
            text = queue(client, "pray", ["cure serious", "bless"])
            assert re.search(r"\)\s+1 - bless\b", text), text
            text = command(client, "prio bless")
            assert "1 pending copy of bless" in text, text
            room = command(client, "look")
            assert "Unnamed" in room, room
            client.send("cast 'bless' self")
            client.expect("suddenly feel blessed", timeout=30)
            queue(client, "pray", ["bless", "cure serious", "bless"])
            command(client, "rest")
            text = queue(client, "pray", ["bless", "cure serious", "bless"])
            assert "You continue your praying" in text, text
            command(client, "stand")
            save_and_quit(client, CLERIC)
        server.shutdown()
        assert saved_slots().splitlines() == [f"{bless}\t0", f"{cure}\t0", f"{bless}\t0"]
    print("PASS memorize/pray order, GMCP, completion, restart and cast-to-tail")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", type=Path, required=True)
    run(parser.parse_args().server.resolve())
