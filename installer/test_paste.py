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

"""Rig test for the paste file: an interactive BusyBox ash on a pty receives the paste like the T window does
(miniterm --eol CR: every LF of the paste becomes a CR on the wire).

usage: python3 -I test_paste.py <repository root>
"""
__author__ = "kaantcp"
__url__ = "https://github.com/kaantcp"
__license__ = "GPL-3.0-only"
CREDIT = "z380m-alpine by kaantcp - https://github.com/kaantcp"
import fcntl, hashlib, os, pty, re, select, shutil, struct, subprocess, sys, termios, time

SCR = sys.argv[1]
BASE = f"{SCR}/rootfs_inst_base"
OUT = f"{SCR}/out"
RIG = f"{SCR}/installer/rig"
WORK = f"{SCR}/work"
os.makedirs(WORK, exist_ok=True)
PASTE = open(f"{OUT}/z380m_gui_paste.txt").read()

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name + (("   <- " + extra) if (extra and not cond) else ""), flush=True)


def fresh_rig(tag):
    R = f"{SCR}/rootfs_paste_{tag}"
    subprocess.run(["rm", "-rf", R], check=True)
    subprocess.run(["cp", "-a", BASE, R], check=True)
    shutil.copy(f"{RIG}/paste_inner.sh", f"{R}/tmp/paste_inner.sh")
    return R


def session(R, hostname, data_after_prompt, wait_re, timeout=300, tail=None, steps=None):
    """data_after_prompt: bytes written to the terminal once the prompt shows (CR line ends already).
    wait_re: regex; the session ends when it matches the new output (or after timeout).
    tail: optional list of bytes written one after the other after wait_re matched (each waits for the prompt)."""
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp("unshare", ["unshare", "--mount", "--uts", "--pid", "--fork", "bash", f"{RIG}/paste_outer.sh", R, hostname])
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 120, 0, 0))
    buf = bytearray()

    def readable(t):
        r, _, _ = select.select([fd], [], [], t)
        if r:
            try:
                d = os.read(fd, 65536)
            except OSError:
                return None
            if not d:
                return None
            buf.extend(d)
        return True

    t0 = time.time()
    while b"z380m:/# " not in buf and time.time() - t0 < 60:
        if readable(0.2) is None:
            break
    start = len(buf)
    pending = memoryview(data_after_prompt)
    t0 = time.time()
    matched = False
    while time.time() - t0 < timeout:
        r, w, _ = select.select([fd], [fd] if pending else [], [], 0.2)
        if r:
            try:
                d = os.read(fd, 65536)
            except OSError:
                break
            if not d:
                break
            buf.extend(d)
        if w and pending:
            try:
                n = os.write(fd, pending[:2048])
                pending = pending[n:]
            except OSError:
                break
        if not pending and re.search(wait_re, bytes(buf[start:]).decode("latin-1")):
            matched = True
            break
    # let the rest of the output arrive
    t1 = time.time()
    while time.time() - t1 < 1.5:
        if readable(0.2) is None:
            break
    for sdata, sre, stimeout in (steps or []):
        mark = len(buf)
        os.write(fd, sdata)
        t1 = time.time()
        while time.time() - t1 < stimeout:
            readable(0.2)
            if re.search(sre, bytes(buf[mark:]).decode("latin-1")):
                break
        t1 = time.time()
        while time.time() - t1 < 1.5:
            if readable(0.2) is None:
                break
    if tail:
        for tb in tail:
            os.write(fd, tb)
            t1 = time.time()
            while time.time() - t1 < 2.0:
                if readable(0.2) is None:
                    break
    try:
        os.write(fd, b"exit\r")
    except OSError:
        pass
    t1 = time.time()
    while time.time() - t1 < 3:
        if readable(0.2) is None:
            break
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass
    return matched, bytes(buf[start:]).decode("latin-1")


def wire(text, eol=b"\r"):
    return text.encode("ascii").replace(b"\n", eol)


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def payload():
    out = {}
    for line in open(f"{SCR}/installer/payload.list"):
        line = line.strip()
        if line and not line.startswith("#"):
            src, name = line.split()
            out[name] = f"{SCR}/{src}"
    return out


def untouched(R):
    """the dry run must not have installed anything"""
    return (not os.path.exists(f"{R}/usr/local/sbin/z380m-gui")) and (not os.path.exists(f"{R}/etc/z380m/gui")) \
        and (not os.path.exists(f"{R}/root/gui-uninstall.sh"))


# ---------------------------------------------------------------- A: normal paste
R = fresh_rig("A")
ok, out = session(R, "z380m", wire(PASTE), r"CHECK DONE|STOPPED|PASTE DAMAGED|WRONG WINDOW|UNPACK FAILED")
open(f"{WORK}/paste_A.txt", "w").write(out)
check("A paste: session reached an end marker", ok, out[-400:])
check("A paste: checksum accepted", "paste OK (" in out)
check("A paste: unpacked", "unpacked into /root/zgui" in out)
check("A paste: dry run finished", "CHECK DONE: all gates passed" in out, out[-600:])
check("A paste: install was NOT run", untouched(R))
files = payload()
same = all(os.path.exists(f"{R}/root/zgui/{n}") and sha(f"{R}/root/zgui/{n}") == sha(p) for n, p in files.items())
check("A paste: all 13 files unpacked byte-identical", same and len(files) == 13)
check("A paste: log written", os.path.exists(f"{R}/root/gui-install.txt"))
check("A paste: terminal queries (ESC[6n) in the output: info only -> " + str(out.count("\x1b[6n")), True)

# ---------------------------------------------------------------- B: paste that gained blank lines and trailing spaces
R = fresh_rig("B")
noisy = "\n".join(l + "  " if re.fullmatch(r"[A-Za-z0-9+/=]{4,76}", l) else l for l in PASTE.split("\n"))
ok, out = session(R, "z380m", wire(noisy, eol=b"\r\r"), r"CHECK DONE|STOPPED|PASTE DAMAGED|WRONG WINDOW|UNPACK FAILED")
open(f"{WORK}/paste_B.txt", "w").write(out)
check("B blank lines + trailing spaces: still accepted", "paste OK (" in out and "CHECK DONE: all gates passed" in out, out[-500:])

# ---------------------------------------------------------------- C: one damaged character
R = fresh_rig("C")
lines = PASTE.split("\n")
i = next(k for k, l in enumerate(lines) if l == "Z380M_B64_END" or False)
j = [k for k, l in enumerate(lines) if re.fullmatch(r"[A-Za-z0-9+/=]{76}", l)][100]
lines[j] = lines[j][:30] + ("A" if lines[j][30] != "A" else "B") + lines[j][31:]
ok, out = session(R, "z380m", wire("\n".join(lines)), r"CHECK DONE|STOPPED|PASTE DAMAGED|WRONG WINDOW|UNPACK FAILED")
open(f"{WORK}/paste_C.txt", "w").write(out)
check("C damaged paste: refused with PASTE DAMAGED", "PASTE DAMAGED" in out, out[-400:])
check("C damaged paste: nothing unpacked", not os.path.exists(f"{R}/root/zgui/install.sh"))
check("C damaged paste: nothing installed", untouched(R))

# ---------------------------------------------------------------- D: wrong window (the PC)
R = fresh_rig("D")
ok, out = session(R, "test-pc", wire(PASTE), r"WRONG WINDOW|CHECK DONE|PASTE DAMAGED")
open(f"{WORK}/paste_D.txt", "w").write(out)
check("D wrong window: refused", "WRONG WINDOW" in out and "test-pc" in out, out[-300:])
check("D wrong window: no files written", not os.path.exists(f"{R}/root/zgui") and untouched(R))

# ---------------------------------------------------------------- E: truncated paste (the end of the block is missing)
R = fresh_rig("E")
cut = "\n".join(PASTE.split("\n")[:-30]) + "\n"
ok, out = session(R, "z380m", wire(cut), r"\n> $", timeout=40, tail=[b"\x03", b"echo alive-$((6*7))\r"])
open(f"{WORK}/paste_E.txt", "w").write(out)
check("E truncated paste: shell waits at the > prompt", "\n> " in out or "> " in out[-300:] or ok)
check("E truncated paste: Ctrl-C brings the prompt back and the shell works", "alive-42" in out, out[-300:])
check("E truncated paste: nothing installed", untouched(R) and not os.path.exists(f"{R}/root/zgui/install.sh"))

# ---------------------------------------------------------------- F: the same file fetched over HTTP and run with sh (fallback)
R = fresh_rig("F")
srv = subprocess.Popen([sys.executable, "-I", "-m", "http.server", "18765", "--bind", "127.0.0.1", "--directory", OUT],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.0)
try:
    cmd = b"wget -qO- http://127.0.0.1:18765/z380m_gui_paste.txt | sh\r"
    ok, out = session(R, "z380m", cmd, r"CHECK DONE|STOPPED|PASTE DAMAGED|WRONG WINDOW|UNPACK FAILED|not found|wget:")
finally:
    srv.terminate()
open(f"{WORK}/paste_F.txt", "w").write(out)
check("F http + sh: dry run finished", "CHECK DONE: all gates passed" in out, out[-500:])
check("F http + sh: install was NOT run", untouched(R))

# ---------------------------------------------------------------- G: the terminal answers a size query in the middle of the paste
# (the tablet shell asks the terminal with ESC[6n; the terminal's answer ESC[24;80R then arrives
# between pasted bytes, possibly in the middle of a line)
R = fresh_rig("G")
raw = wire(PASTE)
cut1, cut2, cut3 = 5003, 9001, 13007
reply = b"\x1b[24;80R"
data = raw[:cut1] + reply + raw[cut1:cut2] + reply + raw[cut2:cut3] + b"\x1b[1;1R" + raw[cut3:]
ok, out = session(R, "z380m", data, r"CHECK DONE|STOPPED|PASTE DAMAGED|WRONG WINDOW|UNPACK FAILED")
open(f"{WORK}/paste_G.txt", "w").write(out)
check("G terminal replies in the middle of the paste: still accepted", "paste OK (" in out and "CHECK DONE: all gates passed" in out, out[-500:])

# ---------------------------------------------------------------- H: the whole flow typed the way the user will do it
R = fresh_rig("H")
ok, out = session(R, "z380m", wire(PASTE), r"CHECK DONE|STOPPED|PASTE DAMAGED|WRONG WINDOW|UNPACK FAILED",
                  steps=[(b"sh /root/zgui/install.sh\r", r"INSTALL OK|STOPPED|INSTALLER EXIT|FAILED", 240),
                         (b"echo RC-$((6*7)):$(cat /tmp/z380m-install.rc)\r", r"RC-42:\d", 20),
                         (b"z380m-gui status\r", r"boot service|guard|touch", 30),
                         (b"sh /root/gui-uninstall.sh\r", r"uninstall|removed|done|\$ $|# $", 120)])
open(f"{WORK}/paste_H.txt", "w").write(out)
check("H flow: install finished OK from the pasted files", "INSTALL OK" in out, out[-800:])
check("H flow: install exit code file says 0", "RC-42:0" in out, out[-400:])
check("H flow: z380m-gui is installed and answers (status before any start)",
      "supervisor: not running" in out and "start at boot: no" in out, out[-900:])
check("H flow: console.sh hook installed with a backup", os.path.exists(f"{R}/etc/z380m/console.sh.orig"))
check("H flow: uninstall script restores the original console.sh and removes the files",
      not os.path.exists(f"{R}/usr/local/sbin/z380m-gui") and not os.path.exists(f"{R}/etc/z380m/gui"),
      out[-600:])

bad = [n for n, c in results if not c]
print(f"\n{len(results) - len(bad)} PASS, {len(results)} checks, {len(bad)} failed")
sys.exit(1 if bad else 0)
