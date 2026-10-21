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

"""Decode a /proc/bus/input/devices bitmap (B: EV= / KEY= / ABS=).

usage: decode_bits.py <ev|key|abs> <hexword> [<hexword> ...]
Words are printed by the kernel most-significant first; on this 64-bit kernel each word is 64 bits.
"""
__author__ = "kaantcp"
__url__ = "https://github.com/kaantcp"
__license__ = "GPL-3.0-only"
CREDIT = "z380m-alpine by kaantcp - https://github.com/kaantcp"
import sys

NAMES = {
    "ev": {0: "EV_SYN", 1: "EV_KEY", 2: "EV_REL", 3: "EV_ABS", 4: "EV_MSC", 5: "EV_SW"},
    "key": {
        0x72: "KEY_VOLUMEDOWN", 0x73: "KEY_VOLUMEUP", 0x74: "KEY_POWER",
        0x145: "BTN_TOOL_FINGER", 0x14A: "BTN_TOUCH",
    },
    "abs": {
        0x00: "ABS_X", 0x01: "ABS_Y", 0x18: "ABS_PRESSURE", 0x2F: "ABS_MT_SLOT",
        0x30: "ABS_MT_TOUCH_MAJOR", 0x31: "ABS_MT_TOUCH_MINOR", 0x32: "ABS_MT_WIDTH_MAJOR",
        0x35: "ABS_MT_POSITION_X", 0x36: "ABS_MT_POSITION_Y", 0x39: "ABS_MT_TRACKING_ID",
        0x3A: "ABS_MT_PRESSURE",
    },
}


def set_bits(words):
    ws = [int(w, 16) for w in words][::-1]  # index 0 = least significant word
    return [i * 64 + b for i, w in enumerate(ws) for b in range(64) if (w >> b) & 1]


def main(argv):
    kind, words = argv[1], argv[2:]
    names = NAMES[kind]
    got = set_bits(words)
    print("%s=%s -> %d bits" % (kind.upper(), " ".join(words), len(got)))
    for n in got:
        print("   0x%03x (%3d) %s" % (n, n, names.get(n, "(no name in the small table)")))
    if kind == "key":
        print("   BTN_TOUCH (0x14a) present:", 0x14A in got, "| BTN_TOOL_FINGER (0x145) present:", 0x145 in got)
    if kind == "abs":
        print("   ABS_X present:", 0 in got, "| ABS_Y present:", 1 in got)


main(sys.argv)
