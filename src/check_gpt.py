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

"""Compare the output of `mtk.py printgpt` with the partition table of the tablet this project was tested on.

usage:  python3 check_gpt.py FILE
        FILE is the text that `mtk.py printgpt` printed. Save it with:
            sudo /usr/bin/python3 -u mtk.py printgpt 2>&1 | tee gpt.txt

The program only reads FILE; it does not talk to the tablet. It prints one line per difference.
Exit status:  0  the table is identical (names, order, offsets, lengths, total size)
              1  it differs: do NOT use the offsets and commands of docs/GUIDE.md on this tablet
              2  no partition table was found in FILE
Partition GUIDs are ignored (they are different on every tablet).

        python3 check_gpt.py --sizes DIR
        Checks a backup folder: DIR/<name>.bin must exist for the 23 partitions proinfo ... APD (everything before
        "cache") and have exactly the length of the partition; DIR/preloader_boot1.bin, if present, must be 4194304
        bytes. It only reads file sizes.
Exit status:  0  all 23 files are there with the right size    1  something is missing or has the wrong size
"""
__author__ = "kaantcp"
__url__ = "https://github.com/kaantcp"
__license__ = "GPL-3.0-only"
CREDIT = "z380m-alpine by kaantcp - https://github.com/kaantcp"
import os
import re
import sys

# name, offset, length - copied from evidence/01_stageA_printgpt_and_boot_write.txt (live printgpt of the tested tablet)
EXPECTED = [
    ("proinfo",   0x0000000000080000, 0x0000000000300000),
    ("nvram",     0x0000000000380000, 0x0000000000500000),
    ("protect1",  0x0000000000880000, 0x0000000000a00000),
    ("protect2",  0x0000000001280000, 0x0000000000a00000),
    ("asus_nvm",  0x0000000001c80000, 0x0000000000100000),
    ("persist",   0x0000000001d80000, 0x0000000002000000),
    ("seccfg",    0x0000000003d80000, 0x0000000000040000),
    ("lk",        0x0000000003dc0000, 0x0000000000080000),
    ("boot",      0x0000000003e40000, 0x0000000000ff7000),
    ("recovery",  0x0000000004e37000, 0x0000000000ff7000),
    ("secro",     0x0000000005e2e000, 0x0000000000ff7000),
    ("para",      0x0000000006e25000, 0x0000000000080000),
    ("logo",      0x0000000006ea5000, 0x0000000000800000),
    ("expdb",     0x00000000076a5000, 0x0000000000a00000),
    ("frp",       0x00000000080a5000, 0x0000000000100000),
    ("tee1",      0x00000000081a5000, 0x0000000000500000),
    ("tee2",      0x00000000086a5000, 0x0000000000500000),
    ("kb",        0x0000000008ba5000, 0x0000000000200000),
    ("dkb",       0x0000000008da5000, 0x0000000000200000),
    ("metadata",  0x0000000008fa5000, 0x0000000002000000),
    ("flashinfo", 0x000000000afa5000, 0x0000000001000000),
    ("ADF",       0x000000000bfa5000, 0x0000000002000000),
    ("APD",       0x000000000dfa5000, 0x0000000006400000),
    ("cache",     0x00000000143a5000, 0x000000000c800000),
    ("system",    0x0000000020ba5000, 0x00000000dfc00000),
    ("userdata",  0x00000001007a5000, 0x00000002aac56e00),
]
TOTAL = 0x3ab400000

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
ROW = re.compile(r"^(\w+):\s+Offset 0x([0-9a-fA-F]+), Length 0x([0-9a-fA-F]+),")
TOT = re.compile(r"Total disk size:\s*0x([0-9a-fA-F]+)")


def parse(text):
    """-> (list of (name, offset, length) in file order, total size or None)"""
    rows, total = [], None
    for line in ANSI.sub("", text).replace("\r", "").split("\n"):
        m = ROW.match(line)
        if m:
            rows.append((m.group(1), int(m.group(2), 16), int(m.group(3), 16)))
            continue
        m = TOT.search(line)
        if m:
            total = int(m.group(1), 16)
    return rows, total


def compare(rows, total):
    """-> list of difference messages (empty = identical)"""
    diffs = []
    got = {r[0]: r for r in rows}
    want = {r[0]: r for r in EXPECTED}
    for n, o, l in EXPECTED:
        if n not in got:
            diffs.append("missing partition %s" % n)
        elif (got[n][1], got[n][2]) != (o, l):
            diffs.append("%s: offset 0x%x length 0x%x, expected offset 0x%x length 0x%x" % (n, got[n][1], got[n][2], o, l))
    for n, o, l in rows:
        if n not in want:
            diffs.append("extra partition %s (offset 0x%x length 0x%x)" % (n, o, l))
    if not diffs and [r[0] for r in rows] != [r[0] for r in EXPECTED]:
        diffs.append("the partitions are in a different order")
    if len(rows) != len(got):
        diffs.append("a partition name appears more than once")
    if total is None:
        diffs.append("no 'Total disk size' line")
    elif total != TOTAL:
        diffs.append("total disk size 0x%x, expected 0x%x" % (total, TOTAL))
    return diffs


BACKUP_SET = EXPECTED[:23]          # proinfo ... APD: the partitions before "cache"
BOOT1_SIZE = 0x400000               # eMMC boot1 area (m_emmc_boot1_size in the logged mtkclient run)


def check_sizes(folder):
    """-> list of problems with a backup folder (empty = fine)"""
    problems = []
    for n, _o, l in BACKUP_SET:
        p = os.path.join(folder, n + ".bin")
        if not os.path.isfile(p):
            problems.append("missing %s.bin" % n)
        elif os.path.getsize(p) != l:
            problems.append("%s.bin is %d bytes, the partition is %d bytes" % (n, os.path.getsize(p), l))
    p = os.path.join(folder, "preloader_boot1.bin")
    if os.path.isfile(p) and os.path.getsize(p) != BOOT1_SIZE:
        problems.append("preloader_boot1.bin is %d bytes, expected %d" % (os.path.getsize(p), BOOT1_SIZE))
    return problems


def main(argv):
    if len(argv) == 3 and argv[1] == "--sizes":
        if not os.path.isdir(argv[2]):
            print("not a folder: %s" % argv[2])
            return 1
        problems = check_sizes(argv[2])
        if problems:
            print("BACKUP INCOMPLETE:")
            for d in problems:
                print("  " + d)
            return 1
        print("OK: all %d partition files in %s have exactly the length of their partition." % (len(BACKUP_SET), argv[2]))
        return 0
    if len(argv) != 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8", errors="replace", newline="") as f:
        rows, total = parse(f.read())
    if not rows:
        print("no partition table found in %s (expected lines like 'boot:  Offset 0x..., Length 0x...,')" % argv[1])
        return 2
    diffs = compare(rows, total)
    if diffs:
        print("DIFFERENT from the tested tablet - stop, do not flash:")
        for d in diffs:
            print("  " + d)
        return 1
    print("OK: %d partitions and the total size 0x%x are identical to the tested tablet." % (len(rows), total))
    return 0


if __name__ == "__main__":
    rc = main(sys.argv)
    print(CREDIT)
    sys.exit(rc)
