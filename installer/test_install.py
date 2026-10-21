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

"""Test rig for install.sh: runs the REAL installer with Alpine's own BusyBox/apk in an x86 chroot against a fake tablet
(fake packages, fake /proc files, a mock fbset), in throw-away namespaces. usage: python3 -I test_install.py <repository root>"""
__author__ = "kaantcp"
__url__ = "https://github.com/kaantcp"
__license__ = "GPL-3.0-only"
CREDIT = "z380m-alpine by kaantcp - https://github.com/kaantcp"
import os
import shutil
import subprocess
import sys

SCR = sys.argv[1]
BASE = os.path.join(SCR, "rootfs_inst_base")
RUN = os.path.join(SCR, "rootfs_inst_run")
OUTER = os.path.join(SCR, "installer", "rig", "inst_outer.sh")
results = []


def check(name, ok, extra=""):
    results.append((name, bool(ok)))
    print(("PASS  " if ok else "FAIL  ") + name + (("\n      " + extra[-600:].replace("\n", "\n      ")) if extra and not ok else ""))


def payload():
    out = {}
    for line in open(os.path.join(SCR, "installer", "payload.list")):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        src, name = line.split()
        out[name] = os.path.join(SCR, src)
    return out


def fresh():
    if os.path.exists(RUN):
        shutil.rmtree(RUN)
    subprocess.run(["cp", "-a", BASE, RUN], check=True)
    shutil.copy(os.path.join(SCR, "installer", "rig", "inst_inner.sh"), os.path.join(RUN, "tmp", "inst_inner.sh"))
    d = os.path.join(RUN, "tmp", "zgui")
    os.makedirs(d, exist_ok=True)
    for name, src in payload().items():
        shutil.copy(src, os.path.join(d, name))


def sh(rel, content, mode=0o755):
    p = os.path.join(RUN, rel.lstrip("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(content)
    os.chmod(p, mode)


def run(env=None, mode="install", timeout=300):
    e = {"HOSTNAME": "z380m", "MODE": mode, "TTY0": "1", "DRIVERS": "/tmp/drivers-vt", "INPUTS": "/tmp/inputs-touch"}
    e.update(env or {})
    sh("/tmp/scn.env", "".join("%s=%s\n" % kv for kv in e.items()), 0o644)
    p = subprocess.run(["unshare", "--mount", "--uts", "--pid", "--fork", "bash", OUTER, RUN, "/tmp/scn.env"],
                       capture_output=True, text=True, timeout=timeout, start_new_session=True)
    out = p.stdout + p.stderr
    rc = None
    for line in out.splitlines():
        if line.startswith("INSTALLER EXIT STATUS"):
            rc = int(line.split()[-1])
    return rc, out


def inroot(*cmd):
    p = subprocess.run(["chroot", RUN] + list(cmd), capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def rd(rel):
    try:
        return open(os.path.join(RUN, rel.lstrip("/")), errors="replace").read()
    except OSError:
        return None


def world():
    return rd("/etc/apk/world") or ""


def installed(*names):
    return all(inroot("/sbin/apk", "info", "-e", n)[0] == 0 for n in names)


ORIG_CONSOLE = open(os.path.join(SCR, "scripts", "gui", "console.sh.orig")).read()

# ---------------------------------------------------------------- 1. check mode
fresh()
rc, out = run(mode="check")
check("1 check mode: exit 0 and says CHECK DONE", rc == 0 and "CHECK DONE" in out, out[-800:])
check("1 check mode: shows the survey (touch, VT, fit)", all(w in out for w in ("touch screen: /dev/input/event11", "virtual terminals in the kernel: 1", "-> it fits")), out[-1500:])
check("1 check mode: installed nothing", ".z380m-gui" not in world() and not os.path.exists(os.path.join(RUN, "root/gui-uninstall.sh")) and rd("/etc/z380m/console.sh") == ORIG_CONSOLE)

# ---------------------------------------------------------------- 2. full install
fresh()
rc, out = run()
check("2 install: exit 0 and INSTALL OK", rc == 0 and "INSTALL OK" in out, out[-1500:])
check("2 install: packages installed under the virtual name", installed("xorg-server", "xf86-video-fbdev", "xf86-input-evdev", "jwm", "xterm", "svkbd", "tcc") and ".z380m-gui" in world(), world())
for rel, mode in (("/usr/local/sbin/z380m-gui", 0o755), ("/usr/local/bin/z380m-kbd", 0o755), ("/usr/local/bin/z380m-bright", 0o755),
                  ("/usr/local/bin/z380m-colortest", 0o755), ("/etc/z380m/gui/xorg.conf", 0o644), ("/etc/z380m/gui/session.sh", 0o755),
                  ("/etc/z380m/gui/jwmrc", 0o644), ("/etc/z380m/gui/Xresources", 0o644), ("/usr/local/src/z380m/fbfix.c", 0o644)):
    p = os.path.join(RUN, rel.lstrip("/"))
    check("2 install: %s present with mode %o" % (rel, mode), os.path.exists(p) and (os.stat(p).st_mode & 0o777) == mode,
          "%s %s" % (os.path.exists(p), oct(os.stat(p).st_mode & 0o777) if os.path.exists(p) else ""))
check("2 install: first-run flag set", os.path.exists(os.path.join(RUN, "etc/z380m/gui/first-run")))
c = rd("/etc/z380m/console.sh") or ""
check("2 install: console.sh has both hooks exactly once", c.count("z380m GUI mode (added for z380m-gui)") == 2 and c.count("# --- end of GUI mode") == 2, c)
check("2 install: console.sh.orig is the untouched original", rd("/etc/z380m/console.sh.orig") == ORIG_CONSOLE)
check("2 install: console.sh keeps its mode and parses", (os.stat(os.path.join(RUN, "etc/z380m/console.sh")).st_mode & 0o777) == 0o755 and inroot("/bin/sh", "-n", "/etc/z380m/console.sh")[0] == 0)
check("2 install: only the two hook blocks were added", len((rd("/etc/z380m/console.sh") or "").splitlines()) - len(ORIG_CONSOLE.splitlines()) == len(open(os.path.join(SCR, "scripts/gui/console_block_a.txt")).read().splitlines()) + len(open(os.path.join(SCR, "scripts/gui/console_block_b.txt")).read().splitlines()))
check("2 install: uninstall script written", os.path.exists(os.path.join(RUN, "root/gui-uninstall.sh")))
check("2 install: colour fix built and self-test saw a change", "colour fix: built and it changes what X would see" in out and os.path.exists(os.path.join(RUN, "usr/local/lib/z380m-fbfix.so")), out[-1200:])
rc2, o2 = inroot("/bin/sh", "-c", "LD_PRELOAD=/usr/local/lib/z380m-fbfix.so /bin/true && echo LOADED-$((6*7))")
check("2 install: the built library loads in a real musl process", "LOADED-42" in o2 and "Error" not in o2, o2)
rc2, o2 = inroot("/usr/local/sbin/z380m-gui", "status")
check("2 install: z380m-gui status runs", rc2 == 0 and "supervisor: not running" in o2, o2)
check("2 install: summary names the next step", "z380m-gui start" in out.split("SUMMARY")[-1] and "svkbd" in out.split("SUMMARY")[-1], out[-800:])

# ---------------------------------------------------------------- 3. the same again (idempotent)
sha_before = rd("/etc/z380m/console.sh.orig")
rc, out = run()
check("3 re-run: exit 0", rc == 0 and "INSTALL OK" in out, out[-1200:])
check("3 re-run: console.sh says already patched and is unchanged in shape", "already patched" in out and (rd("/etc/z380m/console.sh") or "").count("z380m GUI mode (added for z380m-gui)") == 2)
check("3 re-run: .orig still the original", rd("/etc/z380m/console.sh.orig") == sha_before == ORIG_CONSOLE)

# ---------------------------------------------------------------- 4. undo
rc, o = inroot("/bin/sh", "/root/gui-uninstall.sh")
check("4 uninstall: exit 0", rc == 0, o)
check("4 uninstall: packages gone, world clean", not installed("xorg-server") and not installed("jwm") and ".z380m-gui" not in world(), world() + o)
check("4 uninstall: console.sh back to the original", rd("/etc/z380m/console.sh") == ORIG_CONSOLE)
check("4 uninstall: files gone", not any(os.path.exists(os.path.join(RUN, r)) for r in ("etc/z380m/gui", "usr/local/sbin/z380m-gui", "usr/local/bin/z380m-kbd", "usr/local/lib/z380m-fbfix.so")))

# ---------------------------------------------------------------- 5. gates: nothing may change when a gate fails
def untouched(label):
    check("%s: nothing was changed" % label, ".z380m-gui" not in world() and rd("/etc/z380m/console.sh") == ORIG_CONSOLE
          and not os.path.exists(os.path.join(RUN, "root/gui-uninstall.sh")) and not installed("xorg-server"))

fresh(); rc, out = run({"TTY0": "", "DRIVERS": "/tmp/drivers-novt"})
check("5a no virtual terminal: stops with exit 1 and says why", rc == 1 and "STOPPED: the kernel shows no virtual terminals" in out, out[-800:]); untouched("5a")
fresh(); rc, out = run({"TTY0": "1", "DRIVERS": "/tmp/drivers-novt"})
check("5b /dev/tty0 exists although the driver list has no vtmaster: goes on", rc == 0 and "INSTALL OK" in out, out[-800:])
fresh(); sh("/usr/local/bin/ping", "#!/bin/sh\nexit 1\n"); rc, out = run()
check("5c network down: stops with the recipe", rc == 1 and "STOPPED: no internet" in out and "pc_usbnet.sh up" in out, out[-800:]); untouched("5c")
fresh(); sh("/usr/local/bin/df", '#!/bin/sh\necho "Filesystem 1K-blocks Used Available Use% Mounted on"\necho "tmpfs 499300 399300 100000 80% /tmp"\n'); rc, out = run()
check("5d not enough space: stops and says so", rc == 1 and "STOPPED: it does not fit" in out, out[-800:]); untouched("5d")
fresh(); inroot("/bin/sh", "-c", "rm -f /repo3/jwm-*.apk && apk --allow-untrusted mkndx -o /repo3/packages.adb /repo3/*.apk && apk --allow-untrusted update"); rc, out = run()
check("5e required package missing: stops and names it", rc == 1 and "required package 'jwm' is not in the package index" in out, out[-800:]); untouched("5e")
fresh(); rc, out = run({"INPUTS": "/tmp/inputs-none"})
check("5f no touch screen: stops", rc == 1 and "STOPPED: no touch screen found" in out, out[-800:]); untouched("5f")
fresh(); rc, out = run({"HOSTNAME": "some-other-pc"})
check("5g wrong machine: stops at once", rc == 1 and "This is not the tablet" in out and "z380m GUI installer" not in out, out[-400:]); untouched("5g")

# ---------------------------------------------------------------- 6. failures after the gates
fresh(); sh("/etc/z380m/console.sh", "#!/bin/sh\necho no anchors here\n"); rc, out = run()
check("6a console.sh without the anchor lines: exit 5, file unchanged", rc == 5 and "could not patch" in out and rd("/etc/z380m/console.sh") == "#!/bin/sh\necho no anchors here\n", out[-800:])
fresh(); inroot("/bin/sh", "-c", "rm -f /repo3/svkbd-*.apk"); rc, out = run()
check("6b apk add fails (a package file is gone): exit 2, tells how to undo", rc == 2 and "apk add failed" in out and "gui-uninstall.sh" in out, out[-1000:])
fresh(); sh("/tmp/tcc-fail", "x\n", 0o644)
rc, out = run()
check("6c compiler fails: install still finishes, colour fix reported as not built", rc == 0 and "INSTALL OK" in out and "colour fix library: no" in out and not os.path.exists(os.path.join(RUN, "usr/local/lib/z380m-fbfix.so")), out[-900:])
fresh(); inroot("/bin/sh", "-c", "rm -f /repo3/svkbd-*.apk && apk --allow-untrusted mkndx -o /repo3/packages.adb /repo3/*.apk && apk --allow-untrusted update")
rc, out = run()
check("6d no svkbd in the index: falls back to matchbox-keyboard", rc == 0 and "on-screen keyboard: matchbox-keyboard" in out and installed("matchbox-keyboard"), out[-900:])

bad = [n for n, ok in results if not ok]
print("\n%d checks, %d failed" % (len(results), len(bad)))
if bad:
    print("FAILED:", "; ".join(bad))
sys.exit(1 if bad else 0)
