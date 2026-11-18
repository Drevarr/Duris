#!/usr/bin/env python3
"""Real fire at a covered NPC in the next room explains cover instead of claiming nobody is there."""

import argparse
from pathlib import Path
import signal
import subprocess
import tempfile

import test_starter_arrow_journey as arrows

journey = arrows.journey
ROOT = journey.ROOT
COVERED = "The sentry quarry is under cover; you can't reach it from there."
NOBODY = "I don't believe there is anything that direction."
OLD_FOLLOW_UP = "Could not find target"


def configure(runtime):
    arrows.configure(runtime, "ranger", None)
    # Mob conversion gives every sentinel NPC ranged cover.
    mobile = runtime / "areas_mini/mini.mob"
    sentry = ("#22801\nsentry quarry~\nthe sentry quarry~\nThe sentry quarry waits here.\n~\n~\n"
              "10 0 0 0 0 0 0 0 S\nPH 0 0 -1\n1 0 100 1d1+1 1d1+1\n0.0.0.0 0\n8 8 0\n")
    mobile.write_text(mobile.read_text().replace("$~", sentry + "$~"))
    zone = runtime / "areas_mini/mini.zon"
    resets = "M 0 22801 1 22801 100 0 0 0\n"
    zone.write_text(zone.read_text().replace("\nS\n", "\n" + resets + "S\n"))


def run(binary):
    with tempfile.TemporaryDirectory(prefix="ranged-cover-", dir=ROOT / "bin/tests") as temporary, \
            journey.mariadb_authority() as (env, _):
        runtime = Path(temporary) / "runtime"
        runtime.mkdir()
        configure(runtime)
        journey.generate_certificate(runtime)
        (runtime / "logs/log").mkdir(parents=True)
        (runtime / "journals/critical").mkdir(parents=True, mode=0o700)
        plain, tls, ws = journey.available_ports()
        env.update(CRITICAL_COMMAND_JOURNAL_DIR=str(runtime / "journals/critical"),
                   DURIS_TLS_PORT=str(tls), DURIS_WEBSOCKET_PORT=str(ws))
        log = runtime / "server.out"
        shooter = None
        with log.open("w") as output:
            process = subprocess.Popen([str(binary), "--minimal", "-s", "-d", str(runtime), str(plain)],
                                       cwd=runtime, env=env, stdout=output, stderr=subprocess.STDOUT)
            try:
                shooter = journey.MudClient(plain)
                journey.create_character(shooter, class_name="ranger")
                shooter.expect(arrows.PROMPT)
                arrows.command(shooter, "remove all", ("You stop using ", "You are quite naked"))
                arrows.command(shooter, "wield bow", "You wield ")
                arrows.command(shooter, "put all.arrow quiver", "You put ")
                arrows.command(shooter, "wear quiver", "You strap ")

                covered = arrows.command(shooter, "fire sentry north", COVERED)
                journey.require(NOBODY not in covered and OLD_FOLLOW_UP not in covered,
                                f"cover reply also claimed no target: {covered}")

                nobody = arrows.command(shooter, "fire nobody north", NOBODY)
                journey.require(OLD_FOLLOW_UP not in nobody, f"missing target repeated itself: {nobody}")

                arrows.command(shooter, "north", "The Arrow Landing Room")
                arrows.command(shooter, "fire sentry", ("You fire ", "Your "))
                print("PASS covered NPCs explain cover at range and stay targetable in the room", flush=True)
            except Exception:
                print(log.read_text(errors="replace")[-6000:])
                print(journey.runtime_logs(runtime))
                if shooter:
                    print(shooter.transcript.decode(errors="replace")[-6000:])
                raise
            finally:
                if shooter:
                    shooter.close()
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=40)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", type=Path, required=True)
    (ROOT / "bin/tests").mkdir(parents=True, exist_ok=True)
    run(parser.parse_args().server.resolve())
