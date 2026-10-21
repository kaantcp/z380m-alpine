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

"""Build z380m_touchfix.sh: one text file with the code and, below it, the two files it installs (as comments).

usage: python3 -I build_touchfix.py <touchfix_template.sh> <z380m-touchbridge binary> <z380m-gui script> <output file>

The output is plain ASCII (no TAB, no CR), reproducible (gzip with mtime 0), and prints the sizes and sha256 values.
Each payload is a gzip file in base64, 76 characters per line, every line starting with "#" so a shell never executes it.
"""
__author__ = "kaantcp"
__url__ = "https://github.com/kaantcp"
__license__ = "GPL-3.0-only"
CREDIT = "z380m-alpine by kaantcp - https://github.com/kaantcp"
import base64, gzip, hashlib, io, sys

tmpl, brin, guiin, out = sys.argv[1:5]
VERSION = "1"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def pack(raw):
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, compresslevel=9, mtime=0) as g:
        g.write(raw)
    b64 = base64.encodebytes(buf.getvalue()).decode("ascii")
    return "".join("#" + line + "\n" for line in b64.splitlines())


bridge = open(brin, "rb").read()
gui = open(guiin, "rb").read()
text = open(tmpl).read()
for k, v in (("@VERSION@", VERSION), ("@BRIDGE_SHA@", sha(bridge)), ("@GUI_SHA@", sha(gui))):
    assert k in text, k
    text = text.replace(k, v)
    assert k not in text, "unreplaced placeholder " + k
if not text.endswith("\n"):
    text += "\n"
text += "#@@ BEGIN bridge\n" + pack(bridge) + "#@@ END bridge\n"
text += "#@@ BEGIN gui\n" + pack(gui) + "#@@ END gui\n"
data = text.encode("ascii")           # raises if anything is not ASCII
assert b"\t" not in data and b"\r" not in data
open(out, "wb").write(data)
print("wrote", out, len(data), "bytes")
print("bridge", len(bridge), "bytes sha256", sha(bridge))
print("gui   ", len(gui), "bytes sha256", sha(gui))
print("script sha256", sha(data))
