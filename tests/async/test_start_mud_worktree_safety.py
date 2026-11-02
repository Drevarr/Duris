#!/usr/bin/env python3
"""Start this checkout's background launcher without consulting systemd."""

import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="duris-start-") as directory:
    temporary = Path(directory)
    checkout = temporary / "checkout"
    (checkout / "scripts").mkdir(parents=True)
    (checkout / "logs").mkdir()
    sibling = temporary / "sibling"
    sibling.mkdir()
    shutil.copy2(ROOT / "scripts/start_mud.sh", checkout / "scripts/start_mud.sh")
    launcher = checkout / "scripts/cycle_mud.sh"
    launcher.write_text('#!/bin/bash\nprintf "%s\\n" "$PWD" "$@" > "$START_MUD_TEST_CAPTURE"\n')
    launcher.chmod(0o755)

    commands = temporary / "commands"
    commands.mkdir()
    systemctl = commands / "systemctl"
    systemctl.write_text('#!/bin/bash\ntouch "$START_MUD_TEST_SYSTEMCTL"\nexit 0\n')
    systemctl.chmod(0o755)
    service_called = temporary / "service-called"

    for index, arguments in enumerate(([], ["--dev"], ["--minimal"])):
        capture = temporary / f"launch-{index}"
        environment = dict(os.environ, PATH=f"{commands}:{os.environ['PATH']}",
                           START_MUD_TEST_CAPTURE=str(capture),
                           START_MUD_TEST_SYSTEMCTL=str(service_called))
        subprocess.run([str(checkout / "scripts/start_mud.sh"), *arguments],
                       cwd=sibling, env=environment, check=True, capture_output=True)
        deadline = time.monotonic() + 5
        expected = [str(checkout), *arguments]
        while time.monotonic() < deadline:
            if capture.exists() and capture.read_text().splitlines() == expected:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("background launcher did not report the expected checkout and arguments")
        assert not service_called.exists(), "local startup consulted systemd"
        assert (checkout / "logs/duris-console.log").exists()

    launcher.write_text('#!/bin/bash\nprintf "%s" "$$" > "$START_MUD_TEST_CAPTURE"\nexec sleep 30\n')
    capture = temporary / "detached-launch"
    environment["START_MUD_TEST_CAPTURE"] = str(capture)
    process = subprocess.Popen([str(checkout / "scripts/start_mud.sh")], cwd=sibling,
                               env=environment, start_new_session=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process.communicate(timeout=5)
    assert process.returncode == 0
    child = None
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if capture.exists() and capture.read_text().isdigit():
                child = int(capture.read_text())
                break
            time.sleep(0.01)
        assert child, "background launcher did not report its PID"
        assert os.getsid(child) != process.pid, "launcher retained the caller's session"
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        os.kill(child, 0)
    finally:
        if child:
            try:
                os.kill(child, signal.SIGTERM)
            except ProcessLookupError:
                pass

print("background game launcher: checkout, arguments, and systemd independence passed")
