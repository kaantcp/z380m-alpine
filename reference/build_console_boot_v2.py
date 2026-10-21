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

__author__ = "kaantcp"
__url__ = "https://github.com/kaantcp"
__license__ = "GPL-3.0-only"
CREDIT = "z380m-alpine by kaantcp - https://github.com/kaantcp"
# Z380M console boot image v2: official kernel (unchanged) + BusyBox + z380term (screen console).
# Usage: python3 build_console_boot_v2.py [z380term.c] [out_dir]
import gzip, hashlib, os, shutil, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
CSRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "z380term.c")
OUT = sys.argv[2] if len(sys.argv) > 2 else HOME + "/linux_console_v2"
SRC = os.environ.get("Z380_SRC_BOOT", HOME + "/official_ref/boot.bin")
BB = os.environ.get("Z380_BUSYBOX", HOME + "/bbx/usr/bin/busybox")
CC = os.environ.get("Z380_CC", "aarch64-linux-gnu-gcc")
MACHINE = int(os.environ.get("Z380_ELF_MACHINE", "183"))   # 183 = AArch64
PART = 0xFF7000
MAGIC = bytes.fromhex("88168858")

INIT = r'''#!/bin/busybox sh
# Z380M console init v2: stock 3.18 kernel + BusyBox + z380term. PID 1 must never exit.
export PATH=/bin:/sbin:/usr/bin:/usr/sbin HOME=/root TERM=linux PS1='z380m# '
/bin/busybox --install -s /bin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev 2>/dev/null
mount -t tmpfs tmpfs /tmp
mkdir -p /dev/pts
mount -t devpts devpts /dev/pts 2>/dev/null
[ -c /dev/ptmx ] || mknod /dev/ptmx c 5 2
chmod 666 /dev/ptmx
mdev -s 2>/dev/null
if [ ! -c /dev/fb0 ] && [ -e /sys/class/graphics/fb0/dev ]; then
  mm=$(cat /sys/class/graphics/fb0/dev); mknod /dev/fb0 c ${mm%%:*} ${mm##*:}
fi
hostname z380m
LOG=/tmp/initlog
log() { echo "$(cut -d' ' -f1 /proc/uptime) $*" >> $LOG; }
log "init v2 start, kernel $(uname -r)"

BL=/sys/class/leds/lcd-backlight/brightness
bright() { [ -w $BL ] && echo 255 > $BL; return 0; }
blink() {
  [ -w $BL ] || return 0
  n=$1
  while [ $n -gt 0 ]; do echo 8 > $BL; sleep 1; echo 255 > $BL; sleep 1; n=$((n-1)); done
}
bright

mkpart() {
  for u in /sys/class/block/*/uevent; do
    grep -q "^PARTNAME=$1\$" $u 2>/dev/null || continue
    mm=$(cat ${u%/uevent}/dev)
    mknod /dev/part_$1 b ${mm%%:*} ${mm##*:} && return 0
  done
  return 1
}
if mkpart expdb; then log "expdb node ok"; else log "expdb node missing"; fi

savelog() {
  [ -b /dev/part_expdb ] || return 0
  {
    echo "=== z380m init log ==="; cat $LOG
    echo "=== z380term log ==="; cat /tmp/z380term.log 2>&1
    echo "=== usb ==="
    for f in enable state functions idVendor idProduct; do echo "$f=$(cat /sys/class/android_usb/android0/$f 2>&1)"; done
    echo "=== tty ==="; ls /sys/class/tty 2>&1 | grep -i gs
    echo "=== dev ==="; ls -l /dev 2>&1 | head -60
    echo "=== dmesg ==="; dmesg
  } 2>&1 | head -c 1000000 > /tmp/full.log
  dd if=/tmp/full.log of=/dev/part_expdb bs=4096 2>/dev/null
  sync
}

blink 1
log "stage1 done"

G=/sys/class/android_usb/android0
if [ -d $G ]; then
  echo 0 > $G/enable
  echo 0E8D > $G/idVendor
  echo 2007 > $G/idProduct
  echo MediaTek > $G/iManufacturer
  echo Z380M-Linux > $G/iProduct
  echo z380m0001 > $G/iSerial
  echo 1 > $G/f_acm/instances
  echo acm > $G/functions
  echo 02 > $G/bDeviceClass
  echo 1 > $G/enable
  log "gadget set: functions=$(cat $G/functions) enable=$(cat $G/enable) state=$(cat $G/state 2>&1)"
  blink 2
else
  log "NO android_usb sysfs"
fi

TTY=
i=0
while [ $i -lt 30 ] && [ -z "$TTY" ]; do
  for t in /sys/class/tty/ttyGS*; do
    [ -e "$t/dev" ] && TTY=${t##*/} && break
  done
  if [ -z "$TTY" ]; then sleep 1; i=$((i+1)); fi
done

launch() {
  while true; do
    t0=$(cut -d. -f1 /proc/uptime)
    if [ -n "$1" ]; then
      /bin/z380term -s /dev/$1 -- /bin/shell-start 2>>/tmp/z380term.log
    else
      /bin/z380term -- /bin/shell-start 2>>/tmp/z380term.log
    fi
    t1=$(cut -d. -f1 /proc/uptime)
    if [ $((t1-t0)) -lt 5 ] && [ -n "$1" ]; then
      log "z380term exited fast, plain shell fallback"
      setsid cttyhack sh </dev/$1 >/dev/$1 2>&1
    fi
    sleep 1
  done
}

if [ -n "$TTY" ]; then
  mdev -s 2>/dev/null
  [ -c /dev/$TTY ] || { mm=$(cat /sys/class/tty/$TTY/dev); mknod /dev/$TTY c ${mm%%:*} ${mm##*:}; }
  log "console on $TTY"
  launch "$TTY" &
  blink 3
else
  log "NO ttyGS device after 30s, screen-only console"
  launch "" &
  blink 5
fi

n=0
while true; do
  [ $n -lt 4 ] && savelog
  n=$((n+1))
  sleep 30
done
'''

SHELL_START = r'''#!/bin/sh
echo "== Z380M Linux console =="
uname -a
echo
echo "-- last kernel messages --"
dmesg | tail -n 20
echo
exec /bin/sh
'''

S_IFDIR, S_IFREG, S_IFLNK, S_IFCHR = 0o040000, 0o100000, 0o120000, 0o020000

def newc(entries):
    out = bytearray()
    ino = 1
    for (name, mode, data, rmaj, rmin, nlink) in entries + [("TRAILER!!!", 0, b"", 0, 0, 1)]:
        nm = name.encode() + b"\0"
        fields = (ino, mode, 0, 0, nlink, 0, len(data), 0, 0, rmaj, rmin, len(nm), 0)
        out.extend(("070701" + "".join("%08X" % f for f in fields)).encode())
        out.extend(nm)
        out.extend(b"\0" * (-len(out) % 4))
        out.extend(data)
        out.extend(b"\0" * (-len(out) % 4))
        ino += 1
    return bytes(out)

def ls_newc(raw):
    pos, res = 0, []
    while True:
        assert raw[pos:pos + 6] == b"070701", "bad cpio magic"
        f = [int(raw[pos + 6 + 8 * i:pos + 14 + 8 * i], 16) for i in range(13)]
        mode, fsize, namesz = f[1], f[6], f[11]
        name = raw[pos + 110:pos + 110 + namesz - 1].decode()
        pos = (pos + 110 + namesz + 3) & ~3
        if name == "TRAILER!!!":
            return res
        res.append((name, oct(mode), fsize))
        pos = (pos + fsize + 3) & ~3

def pad(x, n):
    return x + b"\0" * (-len(x) % n)

def check_elf(path, machine, label):
    d = open(path, "rb").read()
    assert d[:4] == b"\x7fELF" and d[4] == 2 and d[5] == 1, label + ": not a 64-bit little-endian ELF"
    em = struct.unpack_from("<H", d, 18)[0]
    assert em == machine, "%s: wrong CPU type %d (expected %d)" % (label, em, machine)
    phoff = struct.unpack_from("<Q", d, 32)[0]
    phentsize, phnum = struct.unpack_from("<HH", d, 54)
    for i in range(phnum):
        assert struct.unpack_from("<I", d, phoff + i * phentsize)[0] != 3, label + ": dynamically linked"

# ---- compile the screen console ----
if not os.path.exists(CSRC):
    sys.exit("cannot find " + CSRC + " (put z380term.c next to this script)")
if not shutil.which(CC):
    sys.exit("compiler %s not found (sudo apt install gcc-aarch64-linux-gnu)" % CC)
os.makedirs(OUT, exist_ok=True)
TERMBIN = OUT + "/z380term"
r = subprocess.run([CC, "-static", "-O2", "-s", "-Wall", "-o", TERMBIN, CSRC], capture_output=True, text=True)
if r.returncode != 0:
    print(r.stdout + r.stderr)
    sys.exit("compile failed (static libc missing? try: sudo apt install libc6-dev-arm64-cross)")
check_elf(TERMBIN, MACHINE, "z380term")
print("compiled z380term: %d bytes, static, correct CPU type" % os.path.getsize(TERMBIN))

# ---- read the official boot image ----
b = open(SRC, "rb").read()
assert b[:8] == b"ANDROID!", "source is not an Android boot image"
ksz, kaddr, rsz, raddr, ssz, saddr, taddr, page, _u, osv = struct.unpack_from("<10I", b, 8)
assert page == 2048 and ssz == 0, "unexpected header layout"
kernel = b[page:page + ksz]
roff = page + len(pad(kernel, page))
oldrd = b[roff:roff + rsz]
assert kernel[:4] == MAGIC and kernel[8:14] == b"KERNEL", "kernel has no MTK header"
assert oldrd[:4] == MAGIC and oldrd[8:14] == b"ROOTFS", "ramdisk has no MTK header"

bb = open(BB, "rb").read()
check_elf(BB, 183, "busybox")
term = open(TERMBIN, "rb").read()

ents = [(d, S_IFDIR | 0o755, b"", 0, 0, 2) for d in
        ["bin", "sbin", "dev", "proc", "sys", "tmp", "etc", "root", "usr", "usr/bin", "mnt"]]
ents += [
    ("bin/busybox", S_IFREG | 0o755, bb, 0, 0, 1),
    ("bin/sh", S_IFLNK | 0o777, b"busybox", 0, 0, 1),
    ("bin/z380term", S_IFREG | 0o755, term, 0, 0, 1),
    ("bin/shell-start", S_IFREG | 0o755, SHELL_START.encode(), 0, 0, 1),
    ("init", S_IFREG | 0o755, INIT.encode(), 0, 0, 1),
    ("etc/passwd", S_IFREG | 0o644, b"root:x:0:0:root:/root:/bin/sh\n", 0, 0, 1),
    ("etc/group", S_IFREG | 0o644, b"root:x:0:\n", 0, 0, 1),
    ("dev/console", S_IFCHR | 0o600, b"", 5, 1, 1),
    ("dev/null", S_IFCHR | 0o666, b"", 1, 3, 1),
    ("dev/zero", S_IFCHR | 0o666, b"", 1, 5, 1),
    ("dev/tty", S_IFCHR | 0o666, b"", 5, 0, 1),
    ("dev/urandom", S_IFCHR | 0o666, b"", 1, 9, 1),
    ("dev/ptmx", S_IFCHR | 0o666, b"", 5, 2, 1),
]
gz = gzip.compress(newc(ents), 9, mtime=0)
newrd = MAGIC + struct.pack("<I", len(gz)) + b"ROOTFS".ljust(32, b"\0") + b"\xff" * (512 - 40) + gz
rsz2 = len(newrd)

hdr = bytearray(b[:page])
struct.pack_into("<I", hdr, 16, rsz2)
sha = hashlib.sha1()
for part in (kernel, struct.pack("<I", ksz), newrd, struct.pack("<I", rsz2), b"", struct.pack("<I", 0)):
    sha.update(part)
hdr[0x240:0x260] = sha.digest() + b"\0" * 12
img = bytes(hdr) + pad(kernel, page) + pad(newrd, page)
assert len(img) <= PART, "image larger than the boot partition"

# ---- self-check by re-parsing the result ----
h = struct.unpack_from("<10I", img, 8)
assert h[0] == ksz and h[1] == kaddr and h[3] == raddr and h[5] == saddr and h[6] == taddr and h[7] == page
assert img[page:page + ksz] == kernel, "kernel changed!"
rd = img[roff:roff + h[2]]
assert rd[:4] == MAGIC and struct.unpack_from("<I", rd, 4)[0] == len(rd) - 512
assert rd[8:14] == b"ROOTFS" and set(rd[40:512]) == {0xFF}
files = ls_newc(gzip.decompress(rd[512:]))
assert img[0x40:0x40 + 20] == b[0x40:0x40 + 20], "cmdline changed"

open(OUT + "/init.sh", "w").write(INIT)
open(OUT + "/boot_linux_console.img", "wb").write(img)
full = img + b"\0" * (PART - len(img))
open(OUT + "/boot_linux_console_full.bin", "wb").write(full)
print("kernel: %d bytes, byte-identical to source" % ksz)
print("cmdline: %s" % b[0x40:0x240].split(b"\0")[0].decode())
print("old ramdisk: %d bytes -> new ramdisk: %d bytes (gz payload %d)" % (rsz, rsz2, len(gz)))
print("image: %d bytes, padded file: %d bytes (partition %d)" % (len(img), len(full), PART))
for f in files:
    print("  %-16s %-8s %d" % f)
print("sha256 full: " + hashlib.sha256(full).hexdigest())
print("BUILD OK")
