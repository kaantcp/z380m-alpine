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

"""Host tests of the touch bridge logic (TESTBUILD on x86_64): synthetic panel streams in, generated virtual-device events out."""
__author__ = "kaantcp"
__url__ = "https://github.com/kaantcp"
__license__ = "GPL-3.0-only"
CREDIT = "z380m-alpine by kaantcp - https://github.com/kaantcp"
import os, struct, subprocess, sys, tempfile, time, threading
BIN = sys.argv[1]
EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
SYN_REPORT, SYN_MT_REPORT, SYN_DROPPED = 0, 2, 3
BTN_TOUCH = 0x14a
ABS_X, ABS_Y = 0, 1
SLOT, MTX, MTY, TID = 0x2f, 0x35, 0x36, 0x39
results = []

def check(name, ok, extra=""):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + (("   " + str(extra)) if (extra and not ok) else ""))

def rec(t, c, v):
    return struct.pack('<qqHHi', 0, 0, t, c, v)

def frame(*evs):
    """evs: (type, code, value) tuples; a SYN_REPORT is appended"""
    return b''.join(rec(*e) for e in evs) + rec(EV_SYN, SYN_REPORT, 0)

def A(c, v): return (EV_ABS, c, v)

def decode(data):
    out, cur = [], []
    assert len(data) % 24 == 0, len(data)
    for i in range(0, len(data), 24):
        _, _, t, c, v = struct.unpack('<qqHHi', data[i:i + 24])
        cur.append((t, c, v))
        if (t, c) == (EV_SYN, SYN_REPORT):
            out.append(cur); cur = []
    assert not cur, "events without final SYN_REPORT: %r" % cur
    return out

def run(stream, opts=()):
    with tempfile.TemporaryDirectory() as d:
        fi, fo = os.path.join(d, "in.bin"), os.path.join(d, "out.bin")
        open(fi, "wb").write(stream)
        p = subprocess.run([BIN, "run", "-i", fi, "-o", fo] + list(opts), capture_output=True, timeout=20)
        data = open(fo, "rb").read() if os.path.exists(fo) else b""
        return p.returncode, decode(data), p.stderr.decode()

DOWN = lambda x, y: [A(ABS_X, x), A(ABS_Y, y), (EV_KEY, BTN_TOUCH, 1), (EV_SYN, SYN_REPORT, 0)]
UP = [(EV_KEY, BTN_TOUCH, 0), (EV_SYN, SYN_REPORT, 0)]
def MOVE(*xy):
    l = []
    for code, v in xy: l.append(A(code, v))
    return l + [(EV_SYN, SYN_REPORT, 0)]

# 1 type B single finger: down, moves, up
s = (frame(A(TID, 5), A(MTX, 100), A(MTY, 200)) + frame(A(MTX, 110)) + frame(A(MTY, 210)) +
     frame(A(MTX, 120), A(MTY, 220)) + frame(A(TID, -1)) + frame())
rc, out, err = run(s)
check("1 type B tap/drag/lift", rc == 0 and out == [DOWN(100, 200), MOVE((ABS_X, 110)), MOVE((ABS_Y, 210)),
      MOVE((ABS_X, 120), (ABS_Y, 220)), UP], (rc, out, err))

# 2 two fingers: the first one is the pointer; when it lifts everything is released and the second is ignored until all are up
s = (frame(A(SLOT, 0), A(TID, 1), A(MTX, 10), A(MTY, 20)) +
     frame(A(SLOT, 1), A(TID, 2), A(MTX, 500), A(MTY, 600)) +
     frame(A(SLOT, 0), A(MTX, 15)) +
     frame(A(SLOT, 0), A(TID, -1)) +
     frame(A(SLOT, 1), A(MTX, 510)) +
     frame(A(SLOT, 1), A(TID, -1)) +
     frame(A(SLOT, 0), A(TID, 7), A(MTX, 30), A(MTY, 40)))
rc, out, err = run(s)
check("2 two fingers", rc == 0 and out == [DOWN(10, 20), MOVE((ABS_X, 15)), UP, DOWN(30, 40)], (rc, out))

# 3 type A
s = (frame(A(MTX, 100), A(MTY, 200), (EV_SYN, SYN_MT_REPORT, 0)) +
     frame(A(MTX, 110), A(MTY, 210), (EV_SYN, SYN_MT_REPORT, 0)) +
     frame(A(MTX, 110), A(MTY, 210), (EV_SYN, SYN_MT_REPORT, 0), A(MTX, 900), A(MTY, 900), (EV_SYN, SYN_MT_REPORT, 0)) +
     frame((EV_SYN, SYN_MT_REPORT, 0)) +
     frame() +
     frame(A(MTX, 5), A(MTY, 6), (EV_SYN, SYN_MT_REPORT, 0)) +
     frame((EV_SYN, SYN_MT_REPORT, 0)))
rc, out, err = run(s)
check("3 type A (first contact wins, empty frame = lift)", rc == 0 and out == [DOWN(100, 200), MOVE((ABS_X, 110), (ABS_Y, 210)), UP, DOWN(5, 6), UP], (rc, out))

# 4 mirror options (ranges default to 1472 x 2368 when the ioctl is not available)
s = frame(A(TID, 1), A(MTX, 100), A(MTY, 200)) + frame(A(TID, -1))
rc, out, err = run(s, ["-x", "-y"])
check("4 mirror x and y", rc == 0 and out == [DOWN(1372, 2168), UP], (rc, out))
rc, out, err = run(s, ["-x"])
check("4b mirror x only", rc == 0 and out == [DOWN(1372, 200), UP], (rc, out))

# 5 clamping
s = frame(A(TID, 1), A(MTX, -5), A(MTY, 99999)) + frame(A(TID, -1))
rc, out, err = run(s)
check("5 clamp to the panel range", rc == 0 and out == [DOWN(0, 2368), UP], (rc, out))

# 6 slot number out of range must not crash
s = frame(A(SLOT, 99), A(TID, 3), A(MTX, 1), A(MTY, 2)) + frame(A(SLOT, 99), A(TID, -1))
rc, out, err = run(s)
check("6 slot out of range", rc == 0 and out == [DOWN(1, 2), UP], (rc, out))

# 7 SYN_DROPPED: the finger is let go, later position updates of the lost finger are ignored
s = (frame(A(TID, 1), A(MTX, 10), A(MTY, 20)) + frame((EV_SYN, SYN_DROPPED, 0)) + frame(A(MTX, 30)) +
     frame(A(TID, 2), A(MTX, 40), A(MTY, 50)))
rc, out, err = run(s)
check("7 SYN_DROPPED", rc == 0 and out == [DOWN(10, 20), UP, DOWN(40, 50)], (rc, out))

# 8 two taps at the same place
s = frame(A(TID, 1), A(MTX, 7), A(MTY, 8)) + frame(A(TID, -1)) + frame(A(TID, 2), A(MTX, 7), A(MTY, 8)) + frame(A(TID, -1))
rc, out, err = run(s)
check("8 two taps at the same spot", rc == 0 and out == [DOWN(7, 8), UP, DOWN(7, 8), UP], (rc, out))

# 9 tracking id changes in the same slot without a lift (some drivers): treated as the same finger, moves
s = frame(A(TID, 1), A(MTX, 10), A(MTY, 20)) + frame(A(TID, 2), A(MTX, 11)) + frame(A(TID, -1))
rc, out, err = run(s)
check("9 new tracking id in the same slot", rc == 0 and out == [DOWN(10, 20), MOVE((ABS_X, 11)), UP], (rc, out))

# 10 a touch with no position change after the first frame produces nothing more; a frame of only unrelated events too
s = frame(A(TID, 1), A(MTX, 10), A(MTY, 20)) + frame(A(0x30, 5)) + frame(A(MTX, 10)) + frame(A(TID, -1))
rc, out, err = run(s)
check("10 unchanged frames are silent", rc == 0 and out == [DOWN(10, 20), UP], (rc, out))

# 11 odd tail: a truncated record at the end is ignored
s = frame(A(TID, 1), A(MTX, 10), A(MTY, 20)) + frame(A(TID, -1)) + b"\x01\x02\x03"
rc, out, err = run(s)
check("11 truncated record at the end", rc == 0 and out == [DOWN(10, 20), UP], (rc, out))

# 12 records arriving in odd-sized pieces through a pipe
with tempfile.TemporaryDirectory() as d:
    fo = os.path.join(d, "out.bin")
    fifo = os.path.join(d, "fifo")
    os.mkfifo(fifo)
    p = subprocess.Popen([BIN, "run", "-i", fifo, "-o", fo], stderr=subprocess.PIPE)
    s = (frame(A(TID, 5), A(MTX, 100), A(MTY, 200)) + frame(A(MTX, 110)) + frame(A(TID, -1)))
    w = os.open(fifo, os.O_WRONLY)
    for i in range(0, len(s), 7):
        os.write(w, s[i:i + 7]); time.sleep(0.003)
    os.close(w)
    p.wait(timeout=20)
    out = decode(open(fo, "rb").read())
    check("12 odd-sized pieces", p.returncode == 0 and out == [DOWN(100, 200), MOVE((ABS_X, 110)), UP], (p.returncode, out))

# 13 errors
p = subprocess.run([BIN, "run", "-i", "/nonexistent/event99"], capture_output=True)
check("13 missing device -> exit 1 and a message", p.returncode == 1 and b"cannot open" in p.stderr, p)
p = subprocess.run([BIN, "run", "-q"], capture_output=True)
check("13b unknown option -> exit 2", p.returncode == 2, p)
p = subprocess.run([BIN, "version"], capture_output=True)
check("13c version", p.returncode == 0 and p.stdout.startswith(b"z380m-touchbridge 1"), p)
p = subprocess.run([BIN, "check"], capture_output=True)
check("13d check without /dev/uinput fails cleanly", p.returncode == 1 and b"uinput" in p.stderr and not os.path.exists("/dev/uinput"), p)

# 14 probe: summary and the RESULT line
def probe(stream, secs="1"):
    with tempfile.TemporaryDirectory() as d:
        fi = os.path.join(d, "in.bin"); open(fi, "wb").write(stream)
        p = subprocess.run([BIN, "probe", "-i", fi, "-t", secs], capture_output=True, timeout=30)
        res = [l for l in p.stdout.decode().splitlines() if l.startswith("RESULT")]
        kv = dict(x.split("=") for x in res[0].split()[1:]) if res else {}
        return p.returncode, {k: int(v) for k, v in kv.items()}, p.stdout.decode()
s = frame(A(TID, 1), A(MTX, 100), A(MTY, 200)) + frame(A(MTX, 120), A(MTY, 240)) + frame(A(MTX, 140)) + frame(A(TID, -1)) + frame()
rc, kv, txt = probe(s)
check("14 probe summary", rc == 0 and kv.get("frames") == 3 and kv.get("avgx") == 120 and kv.get("avgy") == 226 and kv.get("minx") == 100
      and kv.get("maxx") == 140 and kv.get("miny") == 200 and kv.get("maxy") == 240 and kv.get("xmax") == 1472 and kv.get("ymax") == 2368, (rc, kv, txt))
rc, kv, txt = probe(frame() + frame())
check("14b probe with no touch", rc == 0 and kv.get("frames") == 0 and "no finger seen" in txt, (rc, kv, txt))
s = (frame(A(MTX, 100), A(MTY, 200), (EV_SYN, SYN_MT_REPORT, 0)) + frame(A(MTX, 100), A(MTY, 200), (EV_SYN, SYN_MT_REPORT, 0)) + frame((EV_SYN, SYN_MT_REPORT, 0)))
rc, kv, txt = probe(s)
check("14c probe, type A", rc == 0 and kv.get("frames") == 2 and "SYN_MT_REPORT 3" in txt, (rc, kv, txt))
# probe waits for its time on a quiet FIFO and stops by itself
with tempfile.TemporaryDirectory() as d:
    fifo = os.path.join(d, "fifo"); os.mkfifo(fifo)
    t0 = time.time()
    p = subprocess.Popen([BIN, "probe", "-i", fifo, "-t", "2"], stdout=subprocess.PIPE)
    w = os.open(fifo, os.O_WRONLY)       # writer stays open, sends nothing
    out = p.communicate(timeout=20)[0].decode()
    os.close(w)
    dt = time.time() - t0
    check("14d probe ends after its time on a silent device", 1.8 < dt < 4 and "RESULT frames=0" in out, (dt, out))

print()
print("%d checks, %d failed" % (len(results), results.count(False)))
sys.exit(1 if False in results else 0)
