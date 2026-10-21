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

"""Check that the two installer files in dist/ are made of exactly the sources in this repository: every file inside
them equals the repository file byte for byte, and the checksums are the ones listed in dist/SHA256SUMS.
usage: python3 -I tests/verify_dist.py <repo root>
Reads files only. Exit status 0 = all checks passed."""
__author__ = "kaantcp"
__url__ = "https://github.com/kaantcp"
__license__ = "GPL-3.0-only"
CREDIT = "z380m-alpine by kaantcp - https://github.com/kaantcp"
import base64
import gzip
import hashlib
import io
import os
import re
import sys
import tarfile

R = os.path.abspath(sys.argv[1])
results = []


def check(name, ok, extra=""):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + (("   " + str(extra)) if (extra and not ok) else ""))


def rd(rel, mode="r"):
    with open(os.path.join(R, rel), mode, **({} if "b" in mode else {"encoding": "utf-8", "newline": ""})) as f:
        return f.read()


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ---- dist/SHA256SUMS
sums = {}
for line in rd("dist/SHA256SUMS").splitlines():
    h, name = line.split(None, 1)
    sums[name.strip()] = h
for name in ("z380m_gui_paste.txt", "z380m_touchfix.sh"):
    check("dist/SHA256SUMS lists %s correctly" % name, sums.get(name) == sha(rd("dist/" + name, "rb")))

# ---- plain text only: ASCII, no TAB, no CR (the tablet's shell line editor eats TABs)
paste = rd("dist/z380m_gui_paste.txt")
tfx = rd("dist/z380m_touchfix.sh")
for label, text in (("paste file", paste), ("touch fix", tfx)):
    check("%s: ASCII only, no TAB, no CR" % label, text.isascii() and "\t" not in text and "\r" not in text)

# ---- the paste file: a tar.gz of the files named in installer/payload.list
m = re.search(r"<<'Z380M_B64_END'\n(.*?)\nZ380M_B64_END\n", paste, re.S)
check("paste file: base64 block found", m is not None)
b64 = "".join(m.group(1).split())
g = re.search(r'if \[ "\$GOT" = "([0-9a-f]{64})" \]; then', paste)
check("paste file: the checksum in its guard is the checksum of the base64 text", g is not None and g.group(1) == sha(b64.encode("ascii")))
tf = tarfile.open(fileobj=io.BytesIO(base64.b64decode(b64)), mode="r:gz")
inside = {ti.name: tf.extractfile(ti).read() for ti in tf.getmembers() if ti.isfile()}
src = {}
for line in rd("installer/payload.list").splitlines():
    if line.strip() and not line.startswith("#"):
        rel, name = line.split()
        src[name] = rel
check("paste file: holds the %d files named in installer/payload.list" % len(src), sorted(inside) == sorted(src), sorted(set(inside) ^ set(src)))
for name in sorted(inside):
    if name in src:
        check("paste file: %s == %s" % (name, src[name]), inside[name] == rd(src[name], "rb"))
check("paste file: carries the credit line", CREDIT in paste)

# ---- the touch-fix file: code + two gzip/base64 payloads


def payload(name):
    mm = re.search(r"#@@ BEGIN %s\n(.*?)#@@ END %s\n" % (name, name), tfx, re.S)
    return gzip.decompress(base64.b64decode("".join(l[1:] for l in mm.group(1).splitlines())))


bridge, gui = payload("bridge"), payload("gui")
check("touch fix: the bridge program == installer/touchfix/z380m-touchbridge.arm64", bridge == rd("installer/touchfix/z380m-touchbridge.arm64", "rb"))
check("touch fix: z380m-gui (version 2) == scripts/gui/z380m-gui", gui == rd("scripts/gui/z380m-gui", "rb"))
code = tfx.split("#@@ BEGIN bridge")[0]
tm = rd("installer/touchfix/touchfix_template.sh").replace("@VERSION@", "1")
tm = tm.replace("@BRIDGE_SHA@", sha(bridge)).replace("@GUI_SHA@", sha(gui))
if not tm.endswith("\n"):
    tm += "\n"
check("touch fix: the code == installer/touchfix/touchfix_template.sh (placeholders filled)", code == tm)
check("touch fix: carries the credit line", CREDIT in code)
check("the bridge program carries the credit line", b"z380m-touchbridge 1 by kaantcp - https://github.com/kaantcp" in bridge)

print("\n%d checks, %d failed" % (len(results), results.count(False)))
sys.exit(1 if False in results else 0)
