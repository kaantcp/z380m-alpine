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

"""Pack the GUI installer into one text file that is pasted into the tablet's shell (the T window).

usage: python3 -I mkpaste.py <repository root> <output dir>

Writes in <output dir>:
  z380m_gui_paste.txt   comment header + one shell block: [wrong-window guard] [write pkg.b64 with a heredoc]
                        [sha256 check] [unpack] [run install.sh check]
  z380m_gui_src.zip     the same files, readable, plus SHA256SUMS
  paste_info.txt        sizes and hashes

The package is a tar.gz with fixed metadata (sorted names, mtime 0, uid/gid 0), so the result is reproducible.
The sha256 is taken over the base64 text with all white space removed: a paste that gained or lost blank
lines, CRs or trailing spaces is still accepted; a changed or missing character is not.
Everything written is plain ASCII (no TAB, no non-ASCII characters): the tablet's shell line editor eats TABs.
"""
__author__ = "kaantcp"
__url__ = "https://github.com/kaantcp"
__license__ = "GPL-3.0-only"
CREDIT = "z380m-alpine by kaantcp - https://github.com/kaantcp"
import base64, gzip, hashlib, io, os, sys, tarfile, zipfile

scr = sys.argv[1]
out = sys.argv[2]
os.makedirs(out, exist_ok=True)

files = []
with open(os.path.join(scr, "installer", "payload.list")) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        src, name = line.split()
        with open(os.path.join(scr, src), "rb") as g:
            data = g.read()
        files.append((name, data))
files.sort()

# ---- tar.gz, reproducible
tb = io.BytesIO()
with tarfile.open(fileobj=tb, mode="w", format=tarfile.GNU_FORMAT) as tf:
    for name, data in files:
        ti = tarfile.TarInfo(name)
        ti.size = len(data)
        ti.mtime = 0
        ti.mode = 0o644
        ti.uid = ti.gid = 0
        ti.uname = ti.gname = ""
        tf.addfile(ti, io.BytesIO(data))
gb = io.BytesIO()
with gzip.GzipFile(filename="", mode="wb", fileobj=gb, mtime=0, compresslevel=9) as gz:
    gz.write(tb.getvalue())
pkg = gb.getvalue()

b64 = base64.encodebytes(pkg).decode("ascii")          # 76 characters per line, one LF each
assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\n" for c in b64)
sha = hashlib.sha256("".join(b64.split()).encode("ascii")).hexdigest()
nlines = b64.count("\n")
DELIM = "Z380M_B64_END"
assert DELIM not in b64

header = f"""# {CREDIT}
# Z380M GUI installer, step 1 of 3.  Paste ALL of this file into the T window
# (the tablet shell, prompt  z380m:/# ).  It unpacks its files into /root/zgui and runs a dry run
# (survey, package list, size check).
# Package: {len(pkg)} bytes, {nlines} lines of text, sha256 {sha[:16]}...
"""

body = f"""if [ "$(hostname)" = z380m ] && [ "$(id -u)" = 0 ]; then
echo "{CREDIT}"
mkdir -p /root/zgui && cd /root/zgui || echo "cannot use /root/zgui"
rm -f pkg.b64
cat > pkg.b64 <<'{DELIM}'
{b64}{DELIM}
GOT=$(tr -d ' \\t\\r\\n' < pkg.b64 | sha256sum | cut -d' ' -f1)
if [ "$GOT" = "{sha}" ]; then
echo "paste OK ({nlines} lines, checksum matches)"
if tr -d ' \\t\\r\\n' < pkg.b64 | base64 -d | tar xzf -; then
echo "unpacked into /root/zgui"
sh /root/zgui/install.sh check < /dev/null
else
echo "UNPACK FAILED (disk full?). Nothing was installed."
fi
else
echo "PASTE DAMAGED: got $(wc -l < pkg.b64) lines, expected {nlines}."
echo "checksum got $GOT"
echo "checksum need {sha}"
echo "Nothing was unpacked or installed. Paste again, or use the PC-server way."
fi
else
echo "WRONG WINDOW: this shell is '$(hostname)', not the tablet (z380m)."
echo "Paste it in the T window, the one whose prompt is z380m:/#   Nothing was done."
fi
"""
text = header + body
assert text.isascii() and "\t" not in text
with open(os.path.join(out, "z380m_gui_paste.txt"), "w", newline="\n") as f:
    f.write(text)

# ---- readable copy
sums = "".join(f"{hashlib.sha256(d).hexdigest()}  {n}\n" for n, d in files)
with zipfile.ZipFile(os.path.join(out, "z380m_gui_src.zip"), "w", zipfile.ZIP_DEFLATED) as zf:
    for name, data in files:
        zi = zipfile.ZipInfo("z380m_gui/" + name, date_time=(2026, 10, 17, 0, 0, 0))
        zi.external_attr = 0o644 << 16
        zf.writestr(zi, data)
    zi = zipfile.ZipInfo("z380m_gui/SHA256SUMS", date_time=(2026, 10, 17, 0, 0, 0))
    zi.external_attr = 0o644 << 16
    zf.writestr(zi, sums)

with open(os.path.join(out, "paste_info.txt"), "w") as f:
    f.write(f"files={len(files)} raw={sum(len(d) for _, d in files)} tar={len(tb.getvalue())} gz={len(pkg)} "
            f"b64_lines={nlines} paste_bytes={len(text)} sha={sha}\n")
    f.write(sums)
print(open(os.path.join(out, "paste_info.txt")).read())
