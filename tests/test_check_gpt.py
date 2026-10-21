#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 kaantcp (https://github.com/kaantcp)
#
# Part of z380m-alpine: Alpine Linux on the ASUS ZenPad 8.0 (Z380M, MT8163).
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
# for more details. You should have received a copy of the GNU General
# Public License along with this program (file LICENSE). If not, see
# <https://www.gnu.org/licenses/>.

"""Tests of src/check_gpt.py against the logged printgpt output of the tested tablet (evidence/01) and against deliberately
damaged copies and backup folders.   usage: python3 -I tests/test_check_gpt.py <repo root> <scratch dir>
Nothing is written outside <scratch dir>."""
__author__ = "kaantcp"
__url__ = "https://github.com/kaantcp"
__license__ = "GPL-3.0-only"
CREDIT = "z380m-alpine by kaantcp - https://github.com/kaantcp"
import os
import re
import subprocess
import sys

REPO, T = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
os.makedirs(T, exist_ok=True)
sys.path.insert(0, os.path.join(REPO, "src"))
import check_gpt as c      # noqa: E402

CHECK = os.path.join(REPO, "src", "check_gpt.py")
results = []


def run(args):
    r = subprocess.run([sys.executable, "-I", CHECK] + args, capture_output=True, text=True)
    return r.returncode, r.stdout


def check(name, ok, extra=""):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + (("   " + str(extra)) if (extra and not ok) else ""))


def table_case(name, text, want):
    p = os.path.join(T, re.sub(r"[^A-Za-z0-9]+", "_", name) + ".txt")
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    rc, out = run([p])
    check("table: " + name, rc == want, (rc, out))


src = open(os.path.join(REPO, "evidence", "01_stageA_printgpt_and_boot_write.txt"), encoding="utf-8", newline="").read()
lines = src.split("\n")
table_case("identical to the logged tablet", src, 0)
table_case("system offset moved", src.replace("system:              Offset 0x0000000020ba5000", "system:              Offset 0x0000000020ba6000"), 1)
table_case("total size changed", src.replace("Total disk size:0x00000003ab400000", "Total disk size:0x00000003ab400001"), 1)
table_case("lk missing", "\n".join(l for l in lines if not l.startswith("lk:")), 1)
table_case("extra partition", src.replace("Total disk size", "extra:               Offset 0x0000000000000000, Length 0x0000000000001000, Flags 0x0, UUID x, Type EFI\nTotal disk size", 1), 1)
i = [k for k, l in enumerate(lines) if l.startswith("kb:")][0]
sw = lines[:]
sw[i], sw[i + 1] = sw[i + 1], sw[i]
table_case("two partitions swapped", "\n".join(sw), 1)
table_case("empty file", "", 2)
table_case("CRLF line ends and a colour code", src.replace("\n", "\r\n").replace("proinfo:", "\x1b[32mproinfo:", 1), 0)
table_case("file without a table (evidence/02)", open(os.path.join(REPO, "evidence", "02_stageB_system_write_and_readback.txt"), encoding="utf-8", newline="").read(), 2)


def mk(name, drop=None, size=None, boot1=0x400000):
    d = os.path.join(T, name)
    os.makedirs(d, exist_ok=True)
    for n, _o, l in c.BACKUP_SET:
        if n == drop:
            continue
        with open(os.path.join(d, n + ".bin"), "wb") as f:
            f.truncate(size[1] if size and size[0] == n else l)
    if boot1 is not None:
        with open(os.path.join(d, "preloader_boot1.bin"), "wb") as f:
            f.truncate(boot1)
    return d


def sizes_case(name, d, want):
    rc, out = run(["--sizes", d])
    check("backup folder: " + name, rc == want, (rc, out))


sizes_case("complete", mk("b_ok"), 0)
sizes_case("complete, no preloader file", mk("b_nob1", boot1=None), 0)
sizes_case("nvram truncated", mk("b_trunc", size=("nvram", 1000)), 1)
sizes_case("persist missing", mk("b_miss", drop="persist"), 1)
sizes_case("preloader file wrong size", mk("b_b1", boot1=100), 1)
sizes_case("not a folder", os.path.join(T, "does-not-exist"), 1)
check("the table in check_gpt.py has 26 partitions and 23 of them are in the backup set", len(c.EXPECTED) == 26 and len(c.BACKUP_SET) == 23)

print("\n%d checks, %d failed" % (len(results), results.count(False)))
sys.exit(1 if False in results else 0)
