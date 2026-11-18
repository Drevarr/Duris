#!/usr/bin/env python3
"""Real staff epic reset stays inside the player skill array (#1089)."""
from pathlib import Path
import subprocess
import tempfile
from _paths import ROOT, HARNESS_STUBS, extract_function

production = extract_function('epic.c', 'void do_epic_reset(P_char ch, char *arg, int /*cmd*/)')
harness = (ROOT / 'tests/async/epic_reset.cpp').read_text().replace('// PRODUCTION', production)
out = ROOT / 'bin/tests'; out.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='epic-reset-native-', dir=out) as directory:
    cpp, binary = Path(directory) / 'fixture.cpp', Path(directory) / 'fixture'
    cpp.write_text(harness)
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                    '-ffunction-sections', '-fdata-sections',
                    '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                    '-g', '-Isrc', '-I/usr/include/mysql', str(cpp), str(HARNESS_STUBS),
                    '-Wl,--gc-sections', '-o', str(binary)], cwd=ROOT, check=True)
    subprocess.run([str(binary)], check=True, timeout=30)
