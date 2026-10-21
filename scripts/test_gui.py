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

"""Test rig for z380m-gui: runs the REAL z380m-gui, console.sh, session.sh and Alpine's BusyBox in an x86 chroot,
with stand-ins for z380term and Xorg and a pty for the serial line (/dev/ttyGS0). Plays the user at the T window.

usage: python3 -I test_gui.py <repository root>
"""
__author__ = "kaantcp"
__url__ = "https://github.com/kaantcp"
__license__ = "GPL-3.0-only"
CREDIT = "z380m-alpine by kaantcp - https://github.com/kaantcp"
import os
import pty
import select
import shutil
import signal
import subprocess
import sys
import time

SCR = sys.argv[1]
R = os.path.join(SCR, "rootfs_x86")
OUTER = os.path.join(SCR, "scripts", "gui_outer.sh")
STUBLOG = os.path.join(R, "tmp", "stub.log")
GUILOG = os.path.join(R, "var", "log", "z380m-gui.log")
CONLOG = os.path.join(R, "var", "log", "z380m-console.log")
FLAG = os.path.join(R, "run", "z380m-gui")
GUARD = os.path.join(R, "etc", "z380m", "gui", "boot-guard")
TOUCH = os.path.join(R, "dev", "input", "z380m-touch")
PRELOAD = os.path.join(R, "etc", "z380m", "gui", "preload")
SVC = os.path.join(R, "etc", "init.d", "z380m-gui")

results = []


def check(name, ok, extra=""):
    results.append((name, bool(ok)))
    print(("PASS  " if ok else "FAIL  ") + name + (("   " + extra) if extra and not ok else ""))


def sync_rig():
    """copy the CURRENT sources into the rig, so the test can never run against a stale copy"""
    def put(src, dst, mode):
        d = os.path.join(R, dst.lstrip("/"))
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copyfile(os.path.join(SCR, src), d + ".tmp")
        os.chmod(d + ".tmp", mode)
        os.replace(d + ".tmp", d)
    put("scripts/gui_inner.sh", "/tmp/gui_inner.sh", 0o755)     # plays BusyBox init (started by gui_outer.sh)
    put("scripts/gui/z380m-gui", "/usr/local/sbin/z380m-gui", 0o755)
    for n in ("z380m-kbd", "z380m-bright", "z380m-colortest"):
        put("scripts/gui/" + n, "/usr/local/bin/" + n, 0o755)
    put("scripts/gui/session.sh", "/etc/z380m/gui/session.sh", 0o755)
    for n in ("xorg.conf", "jwmrc", "Xresources"):
        put("scripts/gui/" + n, "/etc/z380m/gui/" + n, 0o644)
    # console.sh = the tablet's original with the installer's two hook blocks (the same patch tool the installer uses)
    out = os.path.join(R, "etc", "z380m", "console.sh")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    subprocess.run(["sh", os.path.join(SCR, "scripts/gui/patch_console.sh"), os.path.join(SCR, "scripts/gui/console.sh.orig"),
                    out + ".tmp", os.path.join(SCR, "scripts/gui/console_block_a.txt"), os.path.join(SCR, "scripts/gui/console_block_b.txt")], check=True)
    os.chmod(out + ".tmp", 0o755)
    os.replace(out + ".tmp", out)
    # a stand-in xterm (logs its arguments) so that the colour test window and notify() are visible in stub.log
    x = os.path.join(R, "usr", "local", "bin", "xterm")
    with open(x, "w") as f:
        f.write('#!/bin/sh\necho "xterm $*" >> /tmp/stub.log\n')
    os.chmod(x, 0o755)


sync_rig()


def rd(path):
    try:
        with open(path, "r", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


master, slave = pty.openpty()
slave_path = os.ttyname(slave)
for p in (STUBLOG, GUILOG, CONLOG, FLAG, GUARD, TOUCH, SVC, PRELOAD,
          *[os.path.join(R, "dev", "tty%d" % i) for i in range(8)], os.path.join(R, "tmp", "xorg-fail"),
          os.path.join(R, "run", "z380m-serial-shell.pid"),
          # state that earlier runs of this very test leave behind (section 12 makes the library file, section 14 the first-run flag);
          # a stale library file made section 12 behave as if the colour fix were installed
          os.path.join(R, "usr", "local", "lib", "z380m-fbfix.so"), os.path.join(R, "etc", "z380m", "gui", "first-run"),
          os.path.join(R, "run", "z380m-gui-keep"), os.path.join(R, "run", "z380m-gui-stop"), os.path.join(R, "run", "z380m-gui-restart")):
    try:
        os.remove(p)
    except OSError:
        pass
os.makedirs(os.path.join(R, "var", "log"), exist_ok=True)
os.makedirs(os.path.join(R, "etc", "init.d"), exist_ok=True)
os.makedirs(os.path.join(R, "dev", "input"), exist_ok=True)

proc = subprocess.Popen(["unshare", "--mount", "--uts", "--pid", "--fork", "bash", OUTER, R, slave_path],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
buf = b""


def pump(timeout=0.2):
    global buf
    r, _, _ = select.select([master], [], [], timeout)
    if r:
        try:
            d = os.read(master, 4096)
        except OSError:
            d = b""
        buf += d


def mark():
    global buf
    buf = b""


def send(s):
    os.write(master, s.encode())


def expect(token, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if token.encode() in buf:
            return True
        pump(0.2)
    return token.encode() in buf


def wait_file(path, needle, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        if needle in rd(path):
            return True
        pump(0.1)
    return needle in rd(path)


def wait_count(path, needle, n, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        if rd(path).count(needle) >= n:
            return True
        pump(0.1)
    return rd(path).count(needle) >= n


def wait_exists(path, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        if os.path.exists(path):
            return True
        pump(0.1)
    return os.path.exists(path)


def wait_gone(path, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        if not os.path.exists(path):
            return True
        pump(0.1)
    return not os.path.exists(path)


def count(path, needle):
    return rd(path).count(needle)


def cmd(line, token, timeout=10):
    """type a command whose output contains the token (the echo of the typed line must not)"""
    mark()
    send(line + "\r")
    return expect(token, timeout)


try:
    # --- 0. the text console is up (the stand-in z380term runs a shell on the serial line)
    check("0 text console starts", wait_file(STUBLOG, "z380term stub: start", 20))
    time.sleep(1.0)
    check("0 shell on the serial line answers", cmd("echo T0-$((6*7))", "T0-42", 10))

    # --- 1. test run with a short watchdog, nobody confirms.
    #        (z380term is only ~2 s old here on purpose: the "fails fast" fallback of console.sh must not kick in)
    mark()
    send("z380m-gui start 20\r")
    check("1 start prints its message", expect("starting the desktop", 6))
    check("1 plain shell is announced", wait_file(GUILOG, "plain shell on /dev/ttyGS0", 25))
    check("1 Xorg is up", wait_file(GUILOG, "Xorg is up", 20))
    check("1 session started", wait_file(GUILOG, "session started", 10))
    time.sleep(1.0)
    check("1 the serial line has a working plain shell", cmd("echo T1-$((6*7))", "T1-42", 10))
    st = rd(STUBLOG)
    check("1 Xorg got the config, no TCP, verbose log", "-config /etc/z380m/gui/xorg.conf" in st and "-nolisten tcp" in st
          and "-logverbose 6" in st and "-logfile /var/log/Xorg.0.log" in st, st[-300:])
    check("1 no /dev/tty0 but /dev/tty1: Xorg is told vt1", "vt1" in st.split("Xorg stub: start")[1].split("\n")[0], st[-300:])
    check("1 touch screen found by name, fixed symlink made", os.path.islink(TOUCH) and os.readlink(TOUCH) == "/dev/input/event7"
          and "touch panel: /dev/input/event7" in rd(GUILOG), rd(GUILOG)[-300:])
    check("1 session ran its X commands", all(w in st for w in ("xsetroot ", "xset ", "setxkbmap ", "xrdb -merge /etc/z380m/gui/Xresources",
                                                             "jwm start -f /etc/z380m/gui/jwmrc")), st[-400:])
    check("1 z380term is not running during the desktop", count(STUBLOG, "z380term stub: start") == 1 and "z380term stub: SIGTERM" in st, st[-300:])
    check("1 lease file names a supervisor", os.path.exists(FLAG) and rd(FLAG).strip().isdigit())
    mark()
    send("z380m-gui status\r")
    check("1 status says running", expect("supervisor: running", 6))
    check("1 watchdog gives the console back", wait_gone(FLAG, 40))
    check("1 Xorg was stopped", wait_file(STUBLOG, "Xorg stub: SIGTERM", 10))
    check("1 z380term restarted by init", wait_count(STUBLOG, "z380term stub: start", 2, 15))
    time.sleep(1.5)
    check("1 serial shell works again", cmd("echo T1b-$((6*7))", "T1b-42", 10))
    check("1 logs tell the story", "watchdog: no 'keep'" in rd(GUILOG) and "GUI mode over" in rd(CONLOG), rd(GUILOG)[-400:])

    # --- 2. keep, then stop (z380term is older than 5 s this time)
    time.sleep(6)
    mark()
    send("z380m-gui start 15\r")
    check("2 plain shell again", wait_count(GUILOG, "plain shell on /dev/ttyGS0", 2, 25))
    check("2 Xorg up again", wait_count(GUILOG, "Xorg is up", 2, 20))
    time.sleep(1.0)
    check("2 keep is accepted", cmd("z380m-gui keep", "the desktop stays", 10))
    time.sleep(17)
    check("2 desktop survives the watchdog time after keep", os.path.exists(FLAG) and count(STUBLOG, "Xorg stub: SIGTERM") == 1)
    check("2 status says confirmed", cmd("z380m-gui status", "confirmed with keep: yes", 8))
    mark()
    send("z380m-gui stop\r")
    check("2 stop is accepted", expect("stopping", 8))
    check("2 stop gives the console back", wait_gone(FLAG, 25))
    check("2 z380term restarted a third time", wait_count(STUBLOG, "z380term stub: start", 3, 15))
    time.sleep(1.5)
    check("2 serial shell works again", cmd("echo T2-$((6*7))", "T2-42", 10))

    # --- 3. Xorg cannot start
    open(os.path.join(R, "tmp", "xorg-fail"), "w").close()
    mark()
    send("z380m-gui start 60\r")
    check("3 failure is noticed and logged", wait_file(GUILOG, "Xorg did not come up", 40))
    check("3 console comes back by itself", wait_gone(FLAG, 15) and wait_count(STUBLOG, "z380term stub: start", 4, 15))
    os.remove(os.path.join(R, "tmp", "xorg-fail"))
    time.sleep(1.5)
    check("3 serial shell works again", cmd("echo T3-$((6*7))", "T3-42", 10))

    # --- 4. the supervisor is killed hard: console.sh must take the screen back
    mark()
    send("z380m-gui start 120\r")
    check("4 desktop up", wait_count(GUILOG, "session started", 3, 40))
    time.sleep(1.0)
    mark()
    send("kill -9 $(cat /run/z380m-gui)\r")
    check("4 text console is reclaimed", wait_gone(FLAG, 15) and wait_count(STUBLOG, "z380term stub: start", 5, 15))
    time.sleep(1.5)
    check("4 serial shell works again", cmd("echo T4-$((6*7))", "T4-42", 10))
    check("4 orphan Xorg was killed", count(STUBLOG, "Xorg stub: SIGTERM") >= 3, rd(STUBLOG)[-400:])
    # --- 5. boot mode, as the OpenRC service starts it: guard file, no watchdog, guard cleared after 60 s of stability
    time.sleep(6)
    n_sess = count(GUILOG, "session started")
    n_z = count(STUBLOG, "z380term stub: start")
    mark()
    send("z380m-gui boot\r")
    check("5 boot start creates the guard", wait_exists(GUARD, 10))
    check("5 desktop up in boot mode", wait_count(GUILOG, "session started", n_sess + 1, 40))
    check("5 boot mode is in the log", "boot start" in rd(GUILOG))
    time.sleep(16)
    check("5 no watchdog in boot mode: desktop still up after 16 s", os.path.exists(FLAG) and rd(FLAG).strip().isdigit())
    check("5 guard is still there during the first minute", os.path.exists(GUARD))
    check("5 guard is cleared once the desktop was stable for 60 s", wait_file(GUILOG, "guard cleared", 60) and not os.path.exists(GUARD))
    time.sleep(2.0)
    check("5 serial shell works next to the desktop", cmd("echo T5-$((6*7))", "T5-42", 10))
    mark()
    send("z380m-gui stop\r")
    check("5 stop in boot mode gives the console back", wait_gone(FLAG, 25) and wait_count(STUBLOG, "z380term stub: start", n_z + 1, 15))
    time.sleep(1.5)
    check("5 serial shell works again", cmd("echo T5b-$((6*7))", "T5b-42", 10))

    # --- 6. a boot guard left behind: the boot start must be skipped
    open(GUARD, "w").close()
    n_sess = count(GUILOG, "session started")
    mark()
    send("z380m-gui boot\r")
    check("6 boot start is skipped while the guard exists", wait_file(GUILOG, "staying on the text console", 10))
    time.sleep(2)
    check("6 nothing was started", not os.path.exists(FLAG) and count(GUILOG, "session started") == n_sess)
    check("6 status shows the guard", cmd("z380m-gui status", "boot guard: PRESENT", 8))
    check("6 boot-reset clears it", cmd("z380m-gui boot-reset", "boot guard cleared", 8) and not os.path.exists(GUARD))

    # --- 7. boot-enable / boot-disable (OpenRC service file)
    check("7 boot-enable says so", cmd("z380m-gui boot-enable", "will start at every boot", 10))
    check("7 service file exists, is executable and OpenRC-style", os.path.exists(SVC) and os.access(SVC, os.X_OK)
          and rd(SVC).startswith("#!/sbin/openrc-run") and "z380m-gui boot" in rd(SVC))
    check("7 rc-update add was called", "rc-update add z380m-gui default" in rd(STUBLOG))
    check("7 service file parses as shell", cmd("sh -n /etc/init.d/z380m-gui && echo SVC-$((6*7))", "SVC-42", 8))
    check("7 status mentions the service", cmd("z380m-gui status", "start at boot: set up", 8))
    check("7 boot-disable removes it", cmd("z380m-gui boot-disable", "will not start at boot any more", 10) and not os.path.exists(SVC))
    check("7 rc-update del was called", "rc-update del z380m-gui default" in rd(STUBLOG))

    # --- 8. with a /dev/tty0 present, Xorg is NOT given a vt argument
    check("8 fake /dev/tty0 made", cmd("touch /dev/tty0 && mount --bind /dev/null /dev/tty0 && test -c /dev/tty0 && echo TTY0-$((6*7))", "TTY0-42", 8))
    n_x = count(STUBLOG, "Xorg stub: start")
    mark()
    send("z380m-gui start 10\r")
    check("8 Xorg started again", wait_count(STUBLOG, "Xorg stub: start", n_x + 1, 40))
    last = rd(STUBLOG).split("Xorg stub: start")[-1].split("\n")[0]
    check("8 no vt argument when /dev/tty0 exists", "vt1" not in last, last)
    check("8 watchdog gives the console back", wait_gone(FLAG, 40))
    time.sleep(2.0)
    check("8 serial shell works again", cmd("umount /dev/tty0; echo T8-$((6*7))", "T8-42", 10))
    # --- 9. restart-x: X and the session start again, the screen is NOT given back to the text console
    n_x = count(STUBLOG, "Xorg stub: start")
    n_s = count(GUILOG, "session started")
    n_z = count(STUBLOG, "z380term stub: start")
    mark()
    send("z380m-gui start 300\r")
    check("9 desktop up", wait_count(STUBLOG, "Xorg stub: start", n_x + 1, 40) and wait_count(GUILOG, "session started", n_s + 1, 20))
    time.sleep(1.0)
    sup = rd(FLAG).strip()
    check("9 restart-x is accepted", cmd("z380m-gui restart-x", "restarting X", 10))
    check("9 Xorg and the session started a second time", wait_count(STUBLOG, "Xorg stub: start", n_x + 2, 30)
          and wait_count(GUILOG, "session started", n_s + 2, 20))
    check("9 same supervisor, text console still off", rd(FLAG).strip() == sup and count(STUBLOG, "z380term stub: start") == n_z)
    check("9 old Xorg was stopped first", count(STUBLOG, "Xorg stub: SIGTERM") >= 1)
    time.sleep(1.0)
    check("9 serial shell works", cmd("echo T9-$((6*7))", "T9-42", 10))
    mark()
    send("z380m-gui stop\r")
    check("9 stop gives the console back", wait_gone(FLAG, 25) and wait_count(STUBLOG, "z380term stub: start", n_z + 1, 15))
    time.sleep(1.5)
    check("9 serial shell works again", cmd("echo T9b-$((6*7))", "T9b-42", 10))

    # --- 10. a preload library file is passed to Xorg as LD_PRELOAD
    with open(PRELOAD, "w") as f:
        f.write("/usr/lib/z380m-test-preload.so\n")
    n_x = count(STUBLOG, "Xorg stub: start")
    mark()
    send("z380m-gui start 8\r")
    check("10 Xorg started", wait_count(STUBLOG, "Xorg stub: start", n_x + 1, 40))
    check("10 LD_PRELOAD reached Xorg", wait_file(STUBLOG, "LD_PRELOAD=[/usr/lib/z380m-test-preload.so]", 10), rd(STUBLOG)[-300:])
    check("10 status shows the preload", cmd("z380m-gui status", "Xorg preload: /usr/lib/z380m-test-preload.so", 8))
    check("10 console is back after the watchdog", wait_gone(FLAG, 40))
    os.remove(PRELOAD)
    time.sleep(2.0)

    # --- 11. the kernel has virtual terminals but /dev/tty0 is missing: the nodes are made
    check("11 fake driver list made", cmd("echo '/dev/vc/0 /dev/vc/0 4 0 system:vtmaster' > /tmp/fake_drivers; rm -f /dev/tty0; echo T11-$((6*7))", "T11-42", 8))
    mark()
    send("Z380M_TTY_DRIVERS=/tmp/fake_drivers z380m-gui start 8\r")
    check("11 /dev/tty0 was made", wait_file(GUILOG, "made /dev/tty0", 40))
    check("11 it is a character device and no vt argument was given",
          wait_count(STUBLOG, "Xorg stub: start", n_x + 2, 20) and "vt1" not in rd(STUBLOG).split("Xorg stub: start")[-1].split("\n")[0])
    check("11 console is back after the watchdog", wait_gone(FLAG, 40))
    time.sleep(2.0)
    check("11 serial shell works again", cmd("echo T11b-$((6*7))", "T11b-42", 10))
    # --- 12. Menu > Display > Fix colours = "z380m-gui swapcolors": toggles the preload file, restarts X when it runs
    LIBP = os.path.join(R, "usr", "local", "lib", "z380m-fbfix.so")
    check("12a no library installed: swapcolors refuses and changes nothing", cmd("z380m-gui swapcolors; echo RC-$?", "RC-1", 10) and not os.path.exists(PRELOAD))
    os.makedirs(os.path.dirname(LIBP), exist_ok=True)
    with open(LIBP, "wb") as f:
        f.write(b"not a real library, the stand-in Xorg never loads it")
    check("12b desktop off: colour fix switched on for the next start",
          cmd("z380m-gui swapcolors", "takes effect at the next start", 10) and rd(PRELOAD).strip() == "/usr/local/lib/z380m-fbfix.so")
    check("12c switched off again", cmd("z380m-gui swapcolors", "Colour fix OFF", 10) and not os.path.exists(PRELOAD))
    n_x = count(STUBLOG, "Xorg stub: start")
    n_z = count(STUBLOG, "z380term stub: start")
    mark()
    send("z380m-gui start 300\r")
    check("12d desktop up", wait_count(STUBLOG, "Xorg stub: start", n_x + 1, 40) and wait_file(GUILOG, "session started", 20))
    time.sleep(1.0)
    check("12e swapcolors on a running desktop restarts X with the library preloaded",
          cmd("z380m-gui swapcolors", "Colour fix ON", 10) and wait_count(STUBLOG, "Xorg stub: start", n_x + 2, 30)
          and wait_file(STUBLOG, "LD_PRELOAD=[/usr/local/lib/z380m-fbfix.so]", 10), rd(STUBLOG)[-500:])
    check("12f the answer is also shown in a small window on the desktop", wait_file(STUBLOG, "xterm -geometry 48x6 -title z380m", 10))
    check("12g text console still off after the restart", count(STUBLOG, "z380term stub: start") == n_z)
    n_env = count(STUBLOG, "Xorg stub: env LD_PRELOAD")
    ok_off = cmd("z380m-gui swapcolors", "Colour fix OFF", 10) and wait_count(STUBLOG, "Xorg stub: env LD_PRELOAD", n_env + 1, 30)
    check("12h swapcolors again: off, X restarts without the library",
          # z380m-gui runs "LD_PRELOAD=$PRE Xorg ...", so with the fix off Xorg sees an EMPTY variable (harmless), shown as []
          ok_off and rd(STUBLOG).rsplit("Xorg stub: env LD_PRELOAD=", 1)[-1].startswith(("[]", "[(unset)]")), rd(STUBLOG)[-500:])
    mark()
    send("z380m-gui stop\r")
    check("12i stop gives the console back", wait_gone(FLAG, 25) and wait_count(STUBLOG, "z380term stub: start", n_z + 1, 15))
    time.sleep(1.5)
    check("12j serial shell works again", cmd("echo T12-$((6*7))", "T12-42", 10))

    # --- 13. a preload library that keeps X from starting is taken away (the desktop must not lock itself out)
    with open(PRELOAD, "w") as f:
        f.write("/usr/local/lib/z380m-fbfix.so\n")
    open(os.path.join(R, "tmp", "xorg-fail"), "w").close()
    n_z = count(STUBLOG, "z380term stub: start")
    mark()
    send("z380m-gui start 60\r")
    check("13a failure noticed", wait_file(GUILOG, "Xorg did not come up", 40))
    check("13b the preload file was removed and the log says so", wait_file(GUILOG, "removed /etc/z380m/gui/preload", 10) and not os.path.exists(PRELOAD))
    check("13c console comes back", wait_gone(FLAG, 15) and wait_count(STUBLOG, "z380term stub: start", n_z + 1, 15))
    os.remove(os.path.join(R, "tmp", "xorg-fail"))
    time.sleep(1.5)
    check("13d serial shell works again", cmd("echo T13-$((6*7))", "T13-42", 10))

    # --- 14. first start: the colour test window; "keep" removes the first-run flag, later starts do not show it
    FR = os.path.join(R, "etc", "z380m", "gui", "first-run")
    open(FR, "w").close()
    n_x = count(STUBLOG, "Xorg stub: start")
    n_z = count(STUBLOG, "z380term stub: start")
    mark()
    send("z380m-gui start 300\r")
    check("14a desktop up", wait_count(STUBLOG, "Xorg stub: start", n_x + 1, 40))
    check("14b the colour test window is opened while first-run exists", wait_file(STUBLOG, "xterm -class ColorTest -title Colour check -e z380m-colortest", 15))
    time.sleep(1.0)
    check("14c keep removes the first-run flag", cmd("z380m-gui keep", "the desktop stays", 10) and not os.path.exists(FR))
    mark()
    send("z380m-gui stop\r")
    check("14d stop", wait_gone(FLAG, 25) and wait_count(STUBLOG, "z380term stub: start", n_z + 1, 15))
    time.sleep(1.5)
    n_ct = rd(STUBLOG).count("xterm -class ColorTest")
    mark()
    send("z380m-gui start 12\r")
    check("14e second start", wait_count(STUBLOG, "Xorg stub: start", n_x + 2, 40))
    time.sleep(5)
    check("14f no colour test window without first-run", rd(STUBLOG).count("xterm -class ColorTest") == n_ct)
    check("14g console is back after the watchdog", wait_gone(FLAG, 40))
    time.sleep(2.0)
    check("14h serial shell works again", cmd("echo T14-$((6*7))", "T14-42", 10))
finally:
    # SIGKILL to the whole group takes the namespace's init with it, and the kernel then kills everything inside
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        proc.wait(timeout=10)
    except Exception:
        pass

bad = [n for n, ok in results if not ok]
print("\n%d checks, %d failed" % (len(results), len(bad)))
if bad:
    print("FAILED:", "; ".join(bad))
    print("--- stub.log\n" + rd(STUBLOG)[-1500:])
    print("--- z380m-gui.log\n" + rd(GUILOG)[-1500:])
    print("--- z380m-console.log\n" + rd(CONLOG)[-800:])
sys.exit(1 if bad else 0)
