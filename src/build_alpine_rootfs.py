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

"""build_alpine_rootfs.py -- Alpine Linux root filesystem image for the ASUS ZenPad 8.0 (Z380M, MT8163).

Run on the PC (x86-64 Ubuntu 24.04) as root:

    sudo /usr/bin/python3 build_alpine_rootfs.py --preflight-only     # checks only: nothing is installed or written
    sudo /usr/bin/python3 build_alpine_rootfs.py                      # build ~/linux_alpine_v3/system_alpine.ext4

What it does (all on the PC; it never talks to the tablet and never writes to a block device):
  1. host checks (tools, qemu-user + binfmt_misc, disk space, Alpine mirror reachable, official tarball hash)
  2. unpacks the official Alpine 3.24.2 aarch64 minirootfs into a work directory (copy; your ~/alpine stays untouched)
  3. chroot self-test through qemu-user, then an "apk add --simulate" against the real v3.24 aarch64 index
  4. apk add: openrc busybox-openrc busybox-mdev-openrc mdev-conf busybox-suid e2fsprogs e2fsprogs-extra iproute2
     wpa_supplicant iw openssh ca-certificates tzdata (+ optional: nano htop bash curl strace evtest alpine-conf wireless-tools)
  5. cross-compiles z380term (static aarch64) into /usr/local/bin
  6. writes the configuration: hostname, hosts, fstab, motd, repositories (http), resolv.conf, network/interfaces,
     inittab (stock one kept as /etc/inittab.alpine), /etc/z380m/{sysinit,openrc,postboot,console,shutdown}.sh,
     /usr/local/sbin/z380m-usb, runlevels, the marker /etc/z380m-release.  The root password stays locked.
  7. builds an ext4 image (<= 3,745,886,208 bytes; only features a Linux 3.18 kernel can mount), runs e2fsck, checks the
     feature list and the key files inside the finished image, writes a sha256.

Every claim the script prints is either something it just checked ("OK") or it says it cannot
check it from the PC ("NOT CHECKED HERE").
"""
__author__ = "kaantcp"
__url__ = "https://github.com/kaantcp"
__license__ = "GPL-3.0-only"
CREDIT = "z380m-alpine by kaantcp - https://github.com/kaantcp"
import argparse
import ctypes
import datetime
import glob
import hashlib
import os
import platform
import pwd
import re
import select
import shlex
import shutil
import stat
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request

VERSION = "1.0"
HERE = os.path.dirname(os.path.abspath(__file__))

# ======================================================================================================================
# Facts and choices
# ======================================================================================================================
RELEASE = "3.24.2"
BRANCH = "v3.24"
MIRROR = "dl-cdn.alpinelinux.org"          # the host named in the minirootfs' own /etc/apk/repositories
REF_TARBALL = "alpine-minirootfs-3.24.2-aarch64.tar.gz"
# Reference hashes of that tarball.  The sha512 is the one published in Alpine's own docker-alpine repository (branch v3.24,
# commit 1c744e2 "Update Alpine v3.24 - 3.24.2", file checksums.sha512, line for aarch64/alpine-minirootfs-3.24.2-aarch64.tar.gz).
# The sha256 was computed from the tarball in that same repository checkout.
REF_SHA256 = "9bf70a7f18ea44094cbb5f70c58f9af129c8214745743db0e68e5502cc2ce773"
REF_SHA512 = "c717aa68d67a354c7f46488eacb459c7a80951bcd7ea255f04a574aba1a6c5144f2117866e674f27fc92df0f05dd7685c1e6824b88ddd41994803d6fb025395c"
MAX_IMAGE = 3745886208                      # 4 GiB - 0x20ba5000 (start of "system"): keeps every write below 4 GiB
BLOCK = 4096
LABEL = "z380m-alpine"

REQUIRED_PKGS = ["openrc", "busybox-openrc", "busybox-mdev-openrc", "mdev-conf", "busybox-suid", "e2fsprogs",
                 "e2fsprogs-extra", "iproute2", "wpa_supplicant", "iw", "openssh", "ca-certificates", "tzdata"]
OPTIONAL_PKGS = ["nano", "htop", "bash", "curl", "strace", "evtest", "alpine-conf", "wireless-tools"]

# OpenRC services per runlevel.  A service is only linked if its init script exists in the tree.
RUNLEVELS = (
    ("sysinit", ("devfs", "dmesg", "mdev")),
    ("boot", ("swclock", "hostname", "sysctl", "modules", "bootmisc", "syslog", "networking")),
    ("shutdown", ("mount-ro", "killprocs")),
)

# ext4 features a Linux 3.18 kernel can mount (own allow-list; metadata_csum and 64bit are left out on purpose, as are
# orphan_file, metadata_csum_seed, large_dir, ea_inode, casefold, project, encrypt, mmp, bigalloc, meta_bg, inline_data ...)
EXT4_FEATURES = ["has_journal", "extent", "huge_file", "flex_bg", "uninit_bg", "dir_nlink", "extra_isize"]
EXT4_BASE = ["sparse_super", "large_file", "filetype", "resize_inode", "dir_index", "ext_attr"]
EXT4_ALLOWED = set(EXT4_FEATURES + EXT4_BASE)

# CPU type of the Alpine userland and of z380term.  The defaults are the real ones (aarch64).  Two environment variables exist
# only so that the whole script can be exercised on an x86-64 machine with an x86-64 Alpine tree (the tests in this project do
# that); they are never needed on the PC that builds the real image.
ROOT_ARCH = os.environ.get("Z380_ROOT_ARCH", "aarch64")             # test hook: "aarch64" (real) or "x86_64" (tests only)
if ROOT_ARCH not in ("aarch64", "x86_64"):
    sys.exit("Z380_ROOT_ARCH must be aarch64 (or x86_64 for tests)")
ROOT_MACHINE = {"aarch64": 183, "x86_64": 62}[ROOT_ARCH]            # ELF e_machine of the Alpine userland
ROOT_LOADER = "lib/ld-musl-%s.so.1" % ROOT_ARCH                     # musl dynamic loader inside the tree
ROOT_HOST_NAMES = {"aarch64": ("aarch64", "arm64"), "x86_64": ("x86_64", "amd64")}[ROOT_ARCH]
TERM_MACHINE = int(os.environ.get("Z380_ELF_MACHINE", str(ROOT_MACHINE)))   # test hook, like build_boot_v3.py
CC = os.environ.get("Z380_CC", "aarch64-linux-gnu-gcc")
AARCH64_MAGIC = "7f454c460201010000000000000000000200b700"          # binfmt_misc magic of the aarch64 ELF handler
SENTINEL = ".z380m-work"
EXTRA_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
CHROOT_ENV = {"PATH": EXTRA_PATH, "HOME": "/root", "TERM": "dumb", "LANG": "C", "LC_ALL": "C", "SHELL": "/bin/sh"}


class Fail(Exception):
    pass


# ======================================================================================================================
# The files this script adds to the Alpine tree (everything below is plain text; nothing is generated at run time except
# the few values filled in by write_config())
# ======================================================================================================================
INITTAB = r'''# /etc/inittab -- z380m: Alpine Linux on the ASUS ZenPad 8.0 (Z380M).  The stock Alpine file is kept as /etc/inittab.alpine.
#
# BusyBox init runs every ::sysinit: entry first (one after the other), then starts the ::once: and ::respawn: entries
# without waiting for them.  The console below therefore comes up even when an OpenRC service hangs or fails.
::sysinit:/etc/z380m/sysinit.sh
::once:/etc/z380m/openrc.sh
::respawn:/etc/z380m/console.sh

# "reboot" / Ctrl-Alt-Del and the shutdown sequence (poweroff, halt, reboot)
::ctrlaltdel:/sbin/reboot
::shutdown:/etc/z380m/shutdown.sh
'''

SYSINIT_SH = r'''#!/bin/sh
# z380m sysinit -- the first thing BusyBox init runs (see /etc/inittab).  Quick, never blocks, never fails the boot.
# The ramdisk has already moved /proc, /sys and /dev into this root; everything below only fills in what is missing.
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
LOG=/var/log/z380m-boot.log

up() { u=; [ -r /proc/uptime ] && read -r u _ < /proc/uptime; echo "${u:-?}"; }
say() { echo "[$(up)] sysinit: $*" >> $LOG 2>/dev/null; }
mounted() { [ -r /proc/mounts ] || return 1; while read -r _ mp _; do [ "$mp" = "$1" ] && return 0; done < /proc/mounts; return 1; }

mkdir -p /var/log 2>/dev/null
say "start (release: $(head -n 2 /etc/z380m-release 2>/dev/null | tr '\n' ' '))"

[ -r /proc/mounts ] || { mount -t proc proc /proc 2>/dev/null; say "WARNING: /proc was not mounted, mounted it now"; }
mounted /sys || { mount -t sysfs sysfs /sys 2>/dev/null; say "WARNING: /sys was not mounted, mounted it now"; }
if ! mounted /dev; then
  mount -t devtmpfs devtmpfs /dev 2>/dev/null || mount -t tmpfs -o mode=0755 tmpfs /dev 2>/dev/null
  say "WARNING: /dev was not mounted (the ramdisk hand-over did not happen?), mounted a new one"
fi
for n in "console c 600 5 1" "null c 666 1 3" "zero c 666 1 5" "full c 666 1 7" "random c 666 1 8" \
         "urandom c 666 1 9" "tty c 666 5 0" "ptmx c 666 5 2" "kmsg c 600 1 11"; do
  set -- $n
  [ -e /dev/$1 ] || mknod -m $3 /dev/$1 $2 $4 $5 2>/dev/null
done
mkdir -p /dev/pts /dev/shm 2>/dev/null
mounted /dev/pts || mount -t devpts devpts /dev/pts 2>/dev/null
mounted /dev/shm || mount -t tmpfs -o mode=1777,nosuid,nodev tmpfs /dev/shm 2>/dev/null
mounted /run || mount -t tmpfs -o mode=0755,nosuid,nodev tmpfs /run 2>/dev/null
mkdir -p /run/lock /run/openrc 2>/dev/null
mounted /tmp || mount -t tmpfs -o mode=1777,nosuid,nodev tmpfs /tmp 2>/dev/null
hostname -F /etc/hostname 2>/dev/null

# keep a kernel VT console (if the kernel has one) from blanking the panel; harmless otherwise
[ -w /dev/tty0 ] && printf '\033[9;0]' > /dev/tty0 2>/dev/null

say "done"
exit 0
'''

OPENRC_SH = r'''#!/bin/sh
# z380m openrc -- started once by BusyBox init (::once:), in the background.  Runs the three OpenRC runlevels in the same
# order as the stock Alpine inittab and logs everything to /var/log/z380m-openrc.log.  Then postboot.sh.
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
L=/var/log/z380m-openrc.log
B=/var/log/z380m-boot.log
up() { u=; [ -r /proc/uptime ] && read -r u _ < /proc/uptime; echo "${u:-?}"; }

echo "[$(up)] openrc: starting runlevels sysinit, boot, default" >> $B
for lvl in sysinit boot default; do
  echo "== [$(up)] openrc $lvl ==" >> $L
  /sbin/openrc "$lvl" >> $L 2>&1
  rc=$?
  echo "== [$(up)] openrc $lvl finished, exit status $rc ==" >> $L
done
echo "[$(up)] openrc: runlevels done" >> $B
exec /etc/z380m/postboot.sh
'''

POSTBOOT_SH = r'''#!/bin/sh
# z380m postboot -- runs once after the OpenRC runlevels: boot summary into /var/log/z380m-boot.log, and device hot-plug
# via "mdev -d" if the kernel's hotplug helper could not be set.
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
B=/var/log/z380m-boot.log
up() { u=; [ -r /proc/uptime ] && read -r u _ < /proc/uptime; echo "${u:-?}"; }

{
  echo "[$(up)] postboot: ---- boot summary ----"
  echo "-- release --";   cat /etc/z380m-release 2>&1
  echo "-- kernel --";    uname -a; cat /proc/cmdline 2>&1
  echo "-- mounts --";    cat /proc/mounts 2>&1
  echo "-- OpenRC --";    rc-status -a 2>&1
  echo "-- network --";   ip addr 2>&1
  echo "-- usb gadget (android_usb) --"
  for f in enable state functions idVendor idProduct; do echo "$f=$(cat /sys/class/android_usb/android0/$f 2>/dev/null)"; done
  echo "-- framebuffer --"
  fbset -fb /dev/fb0 2>&1 | head -n 20
  for f in name bits_per_pixel stride virtual_size; do echo "fb0/$f: $(cat /sys/class/graphics/fb0/$f 2>/dev/null)"; done
  echo "-- input devices --"
  for d in /sys/class/input/event*; do [ -d "$d" ] && echo "${d##*/}: $(cat $d/device/name 2>/dev/null)"; done
  echo "-- other sysfs classes --"
  for c in net rtc power_supply backlight leds; do echo "$c: $(ls /sys/class/$c 2>/dev/null | tr '\n' ' ')"; done
  echo "-- memory --";    free 2>&1
  echo "-- dmesg (last 40 lines) --"; dmesg | tail -n 40
} >> $B 2>&1

hp=
[ -r /proc/sys/kernel/hotplug ] && read -r hp < /proc/sys/kernel/hotplug
case "$hp" in
  *mdev*) echo "[$(up)] postboot: kernel hotplug helper is '$hp'" >> $B ;;
  *)
    if pidof mdev > /dev/null 2>&1; then
      echo "[$(up)] postboot: mdev already running" >> $B
    elif mdev -d 2>> $B; then
      echo "[$(up)] postboot: no hotplug helper ('$hp'); started 'mdev -d' (netlink)" >> $B
    else
      echo "[$(up)] postboot: WARNING: could not start 'mdev -d'" >> $B
    fi ;;
esac
echo "[$(up)] postboot: done" >> $B
exit 0
'''

CONSOLE_SH = r'''#!/bin/sh
# z380m console -- respawned forever by BusyBox init (::respawn: in /etc/inittab).
# z380term draws a terminal on the tablet screen (/dev/fb0), mirrors it to the USB serial line (/dev/ttyGS0 here,
# /dev/ttyACM0 on the PC) and runs a root shell on a pty.  If z380term keeps dying, a plain shell on the serial line is
# offered instead so the system is never left without a way in.
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
TERM=linux
HOME=/root
SHELL=/bin/sh
export PATH TERM HOME SHELL
Z=/usr/local/bin/z380term
LOG=/var/log/z380m-console.log

up() { u=0; [ -r /proc/uptime ] && read -r u _ < /proc/uptime; echo "${u%%.*}"; }

SER=
w=0
while [ -z "$SER" ] && [ $w -le 3 ]; do
  for c in /dev/ttyGS0 /dev/ttyGS1; do
    [ -c $c ] && { SER=$c; break; }
  done
  [ -n "$SER" ] || { sleep 1; w=$((w+1)); }
done

t0=$(up)
if [ -x "$Z" ]; then
  if [ -n "$SER" ]; then "$Z" -s "$SER" -- /bin/sh -l 2>> $LOG; else "$Z" -- /bin/sh -l 2>> $LOG; fi
  rc=$?
else
  rc=127
  echo "[$t0] z380term is missing ($Z)" >> $LOG
fi
t1=$(up)
echo "[$t1] z380term exited with status $rc after $((t1-t0)) s (serial line: ${SER:-none})" >> $LOG

if [ $((t1-t0)) -lt 5 ]; then
  if [ -n "$SER" ]; then
    echo "[$t1] z380term fails fast: plain shell on $SER" >> $LOG
    setsid -c /bin/sh -l < $SER > $SER 2>&1
  fi
  sleep 5
fi
exit 0
'''

SHUTDOWN_SH = r'''#!/bin/sh
# z380m shutdown -- BusyBox init runs this for reboot / poweroff / halt (::shutdown: in /etc/inittab).
# The OpenRC "shutdown" runlevel stops the services, kills the remaining processes and (mount-ro) remounts / read-only.
# Its output goes to /run (a tmpfs): a log file that is open for writing on / would make that read-only remount fail
# ("failed because we are using /").  When it is over, / gets a short read-write window to save the log, then read-only again.
# If the runlevel takes longer than 45 s it is abandoned, so a stuck service cannot keep the tablet from powering off.
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
B=/var/log/z380m-boot.log
L=/run/z380m-shutdown.log
up() { u=; [ -r /proc/uptime ] && read -r u _ < /proc/uptime; echo "${u:-?}"; }

echo "[$(up)] shutdown: running the OpenRC shutdown runlevel" >> $B 2>/dev/null
/sbin/openrc shutdown > $L 2>&1 &
pid=$!
n=0
while kill -0 $pid 2>/dev/null; do
  [ $n -ge 45 ] && break
  sleep 1
  n=$((n+1))
done
if kill -0 $pid 2>/dev/null; then
  echo "[$(up)] shutdown: WARNING: 'openrc shutdown' still running after ${n} s, giving up on it" >> $L
  kill $pid 2>/dev/null
  rc=timeout
else
  wait $pid
  rc=$?
fi
sync
if mount -o remount,rw / 2>/dev/null; then
  { echo "== [$(up)] openrc shutdown finished (exit status $rc) =="; cat $L; } >> /var/log/z380m-openrc.log 2>/dev/null
  echo "[$(up)] shutdown: done (openrc shutdown: $rc)" >> $B 2>/dev/null
  sync
  mount -o remount,ro / 2>/dev/null
fi
exit 0
'''

USB_SH = r'''#!/bin/sh
# z380m-usb -- helper for the android_usb USB gadget of the stock 3.18 kernel.
#
#   z380m-usb status      show the gadget (read-only)
#   z380m-usb acm         serial console only -- the configuration the boot image sets up (VERIFIED on this tablet)
#   z380m-usb rndis-acm   EXPERIMENTAL, NEVER TRIED ON THIS TABLET: USB network (RNDIS) plus the serial console.
#                         Your serial session drops for a few seconds while USB re-enumerates; reconnect afterwards.
#                         The serial function is always kept.  If no new network interface shows up within 25 s the
#                         gadget is put back to "acm" by itself.  Log: /var/log/z380m-usb.log
#
# After "rndis-acm" the tablet side is 192.168.7.2/24 (default gateway 192.168.7.1).  On the PC, give the new USB network
# interface 192.168.7.1/24 (and set up NAT there if you want internet access through it).
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
G=${Z380_ANDROID_USB:-/sys/class/android_usb/android0}
NET=${Z380_SYS_NET:-/sys/class/net}
LOG=${Z380_USB_LOG:-/var/log/z380m-usb.log}
TABLET_IP=${Z380_USB_IP:-192.168.7.2/24}
PC_IP=192.168.7.1
SWAIT=${Z380_USB_WAIT:-25}

up() { u=; [ -r /proc/uptime ] && read -r u _ < /proc/uptime; echo "${u:-?}"; }
log() { echo "[$(up)] $*" >> "$LOG"; }
need_gadget() {
  [ -d "$G" ] && return 0
  echo "z380m-usb: $G not found (kernel without android_usb?)" >&2
  exit 1
}
w() {   # w <value> <attribute> : write one gadget attribute, remember failures in the log
  if ! echo "$1" > "$G/$2" 2>> "$LOG"; then log "WARNING: could not write '$1' to $G/$2"; return 1; fi
  return 0
}
show() {
  for f in enable state functions idVendor idProduct bDeviceClass iManufacturer iProduct iSerial; do
    printf '%-14s %s\n' "$f" "$(cat "$G/$f" 2>/dev/null)"
  done
  echo "serial nodes : $(ls /dev/ttyGS* 2>/dev/null | tr '\n' ' ')"
  echo "net devices  : $(ls "$NET" 2>/dev/null | tr '\n' ' ')"
}
set_acm() {     # same sequence as the boot image (verified)
  w 0 enable
  w 0E8D idVendor; w 2007 idProduct
  w MediaTek iManufacturer; w Z380M-Alpine iProduct; w z380m0001 iSerial
  [ -d "$G/f_acm" ] && w 1 f_acm/instances
  w acm functions
  w 02 bDeviceClass
  w 1 enable
}
set_rndis_acm() {   # untested
  w 0 enable
  w 0E8D idVendor; w 2008 idProduct
  w MediaTek iManufacturer; w Z380M-Alpine-net iProduct; w z380m0001 iSerial
  [ -d "$G/f_acm" ] && w 1 f_acm/instances
  [ -e "$G/f_rndis/ethaddr" ] && w 02:5a:38:30:4d:01 f_rndis/ethaddr
  w rndis,acm functions
  w EF bDeviceClass; w 02 bDeviceSubClass; w 01 bDeviceProtocol
  w 1 enable
}
restart_console() {   # init respawns /etc/z380m/console.sh, which opens the (possibly re-created) serial node again
  killall z380term 2>/dev/null     # (BusyBox "pkill -x NAME" would not match: it compares the full argv[0] path)
  return 0
}
find_gadget_net() {   # $1 = interfaces before the switch ; prints the gadget interface, if any
  for i in $(ls "$NET" 2>/dev/null); do
    case " $1 " in *" $i "*) ;; *) echo "$i"; return 0 ;; esac
  done
  for i in rndis0 usb0; do [ -e "$NET/$i" ] && { echo "$i"; return 0; }; done
  return 1
}
rndis_inner() {
  before=$(ls "$NET" 2>/dev/null | tr '\n' ' ')
  log "rndis-acm: switching (interfaces before: $before)"
  set_rndis_acm
  n=0; nif=
  while [ $n -lt "$SWAIT" ]; do
    nif=$(find_gadget_net "$before") && [ -n "$nif" ] && break
    nif=; sleep 1; n=$((n+1))
  done
  if [ -z "$nif" ]; then
    log "rndis-acm: no network interface after ${SWAIT}s -> back to acm"
    set_acm
    sleep 2; restart_console
    return 1
  fi
  log "rndis-acm: interface $nif appeared after ${n}s"
  ip link set "$nif" up 2>> "$LOG"
  ip addr add "$TABLET_IP" dev "$nif" 2>> "$LOG"
  sleep 1; restart_console
  log "rndis-acm: done; tablet side $TABLET_IP on $nif (PC side should be $PC_IP/24)"
  return 0
}

case "${1:-status}" in
  status) need_gadget; show ;;
  acm)    need_gadget; log "acm requested"; set_acm; sleep 2; restart_console; show ;;
  rndis-acm)
    need_gadget
    echo "z380m-usb: EXPERIMENTAL. Switching to RNDIS+ACM; the serial session will drop for a few seconds."
    echo "           Log: $LOG   (automatic fall-back to plain 'acm' after ${SWAIT}s without a network interface)"
    log "rndis-acm requested"
    ( setsid "$0" --inner-rndis-acm < /dev/null > /dev/null 2>&1 & )
    ;;
  --inner-rndis-acm) need_gadget; rndis_inner ;;
  *) echo "usage: z380m-usb status | acm | rndis-acm"; exit 2 ;;
esac
exit 0
'''

PROFILE_Z380M = r'''# z380m: the console has no login(1), so show the message of the day once per console shell
if [ -t 0 ] && [ -z "$Z380M_MOTD" ] && [ -r /etc/motd ]; then
	cat /etc/motd
	Z380M_MOTD=1
	export Z380M_MOTD
fi
'''

MOTD = r'''
z380m -- Alpine Linux %(release)s (%(arch)s) on the ASUS ZenPad 8.0 (Z380M / MT8163), stock kernel 3.18.35
z380m-alpine by kaantcp - https://github.com/kaantcp

  Console : this screen and the USB serial line (PC side: /dev/ttyACM0).  The shell is root; the account has no password.
  Logs    : /var/log/z380m-boot.log  z380m-openrc.log  z380m-console.log  z380m-ramdisk.log
  Network : none yet.  Experimental USB networking: z380m-usb status | rndis-acm
  Careful : never write to /dev/mmcblk0boot0, /dev/mmcblk0boot1 or the boot, lk and preloader partitions from here, and never
            run e2fsck on / while it is mounted read-write.  Shut down with "poweroff" or "reboot".

'''

INTERFACES = r'''# /etc/network/interfaces -- z380m
# Only the loopback comes up at boot.  The USB network (see z380m-usb) is not "auto"; bring it up by hand: ifup usb0
auto lo
iface lo inet loopback

iface usb0 inet static
	address 192.168.7.2
	netmask 255.255.255.0
	gateway 192.168.7.1
'''

FSTAB = r'''# /etc/fstab -- z380m.  The root filesystem is mounted by the ramdisk before init starts.
# /dev/part_system is a device node the ramdisk creates for the tablet's "system" partition.
# Pass 0 on purpose: the root filesystem is never fsck'ed while it is mounted.
/dev/part_system	/	ext4	rw,noatime	0 0
'''


# ======================================================================================================================
# Output, logging, subprocess helpers
# ======================================================================================================================
T0 = time.time()
LOGF = None


def log(text=""):
    if LOGF:
        LOGF.write(text + "\n")
        LOGF.flush()


def say(msg):
    print("[%4ds] %s" % (time.time() - T0, msg), flush=True)
    log(msg)


def note(msg):
    print("        " + msg, flush=True)
    log("    " + msg)


def tail(text, n=25):
    lines = [x for x in text.splitlines() if x.strip()]
    return "\n".join(lines[-n:])


def run(cmd, check=True, env=None, cwd=None, timeout=None, input_text=None):
    cmd = [str(c) for c in cmd]
    log("$ " + " ".join(shlex.quote(c) for c in cmd))
    try:
        p = subprocess.run(cmd, env=env, cwd=cwd, input=input_text, text=True, errors="replace", capture_output=True, timeout=timeout)
    except FileNotFoundError:
        raise Fail("program not found: " + cmd[0])
    except subprocess.TimeoutExpired:
        raise Fail("timed out: " + " ".join(cmd))
    p.out = (p.stdout or "") + (p.stderr or "")
    log(p.out.rstrip("\n"))
    log("(exit %d)" % p.returncode)
    if check and p.returncode != 0:
        raise Fail("command failed (exit %d): %s\n%s" % (p.returncode, " ".join(cmd), tail(p.out)))
    return p


def run_stream(cmd, env, show, timeout):
    """Run a long command, copy all output to the log, print only lines for which show(line) is true."""
    cmd = [str(c) for c in cmd]
    log("$ " + " ".join(shlex.quote(c) for c in cmd))
    p = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines, buf, t0 = [], b"", time.time()
    fd = p.stdout.fileno()
    try:
        while True:
            if time.time() - t0 > timeout:
                p.kill()
                raise Fail("timed out after %d s: %s" % (timeout, " ".join(cmd)))
            r, _, _ = select.select([fd], [], [], 5)
            if not r:
                continue
            chunk = os.read(fd, 8192)
            if not chunk:
                break
            buf += chunk
            while True:
                m = re.search(rb"[\r\n]", buf)
                if not m:
                    break
                line, buf = buf[:m.start()].decode("utf-8", "replace"), buf[m.end():]
                if line.strip():
                    lines.append(line)
                    log(line)
                    if show(line):
                        note(line)
    finally:
        if p.poll() is None:
            p.kill()
    rc = p.wait()
    log("(exit %d)" % rc)
    return rc, "\n".join(lines)


def which(name):
    for d in EXTRA_PATH.split(":"):
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return shutil.which(name)


def sha256_file(path, chunk=8 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def file_hashes(path, chunk=8 << 20):
    """(sha256, sha512) of a file, read once."""
    h2, h5 = hashlib.sha256(), hashlib.sha512()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h2.update(b)
            h5.update(b)
    return h2.hexdigest(), h5.hexdigest()


def real_user():
    name = os.environ.get("SUDO_USER")
    if name and name != "root":
        try:
            pw = pwd.getpwnam(name)
            return pw.pw_name, pw.pw_uid, pw.pw_gid, pw.pw_dir
        except KeyError:
            pass
    pw = pwd.getpwuid(os.geteuid())
    return pw.pw_name, pw.pw_uid, pw.pw_gid, pw.pw_dir


def give_to_user(path, uid, gid):
    try:
        if os.geteuid() == 0:
            os.chown(path, uid, gid)
    except OSError:
        pass


def mounts_under(path):
    """Mount points at or below path (from /proc/self/mountinfo)."""
    path = os.path.realpath(path)
    found = []
    try:
        with open("/proc/self/mountinfo") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 5:
                    continue
                mp = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), parts[4])
                if mp == path or mp.startswith(path.rstrip("/") + "/"):
                    found.append(mp)
    except OSError:
        pass
    return found


def safe_rmtree(path):
    """Delete a work directory made by this script -- but never one with a mount below it."""
    path = os.path.abspath(path)
    if not os.path.lexists(path):
        return
    if os.path.islink(path) or not os.path.isdir(path):
        raise Fail("refusing to delete %s: not a plain directory" % path)
    if not os.path.exists(os.path.join(path, SENTINEL)):
        raise Fail("refusing to delete %s: it has no %s marker (not a work directory made by this script)" % (path, SENTINEL))
    m = mounts_under(path)
    if m:
        raise Fail("refusing to delete %s: still mounted: %s" % (path, " ".join(m)))
    run(["rm", "-rf", "--one-file-system", "--", path])
    if os.path.lexists(path):
        raise Fail("could not remove " + path)


# ======================================================================================================================
# ELF helpers
# ======================================================================================================================
def elf_info(path):
    with open(path, "rb") as f:
        h = f.read(64)
        if len(h) < 64 or h[:4] != b"\x7fELF":
            return None
        info = {"cls": h[4], "data": h[5], "type": struct.unpack_from("<H", h, 16)[0],
                "machine": struct.unpack_from("<H", h, 18)[0], "interp": False}
        phoff = struct.unpack_from("<Q", h, 32)[0]
        phentsize, phnum = struct.unpack_from("<HH", h, 54)
        f.seek(phoff)
        for _ in range(phnum):
            ph = f.read(phentsize)
            if len(ph) >= 4 and struct.unpack_from("<I", ph, 0)[0] == 3:
                info["interp"] = True
    return info


def check_static_elf(path, machine, label):
    i = elf_info(path)
    if not i or i["cls"] != 2 or i["data"] != 1:
        raise Fail("%s: not a 64-bit little-endian ELF file" % label)
    if i["machine"] != machine:
        raise Fail("%s: wrong CPU type %d (expected %d)" % (label, i["machine"], machine))
    if i["interp"]:
        raise Fail("%s: dynamically linked (needs a static binary)" % label)


# ======================================================================================================================
# Configuration written into the Alpine tree (pure file operations: no chroot, no qemu; used by the build and by the tests)
# ======================================================================================================================
def write_file(root, rel, text, mode=0o644):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if os.path.lexists(p):
        os.unlink(p)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.chmod(p, mode)
    if os.geteuid() == 0:
        os.chown(p, 0, 0)


def enable_service(root, svc, level):
    if not os.path.lexists(os.path.join(root, "etc/init.d", svc)):
        return False
    d = os.path.join(root, "etc/runlevels", level)
    os.makedirs(d, exist_ok=True)
    link = os.path.join(d, svc)
    if os.path.lexists(link):
        os.unlink(link)
    os.symlink("/etc/init.d/" + svc, link)
    return True


def ssh_key_text(path):
    txt = open(path, encoding="utf-8", errors="replace").read()
    if "PRIVATE KEY" in txt:
        raise Fail("%s looks like a PRIVATE key. Give the .pub file." % path)
    keys = [l.strip() for l in txt.splitlines() if re.match(r"^(ssh-|ecdsa-|sk-ssh-|sk-ecdsa-)\S+ \S+", l.strip())]
    if not keys:
        raise Fail("%s contains no public key line (expected 'ssh-ed25519 AAAA... comment')" % path)
    return "\n".join(keys) + "\n"


def write_config(root, hostname="z380m", dns=("1.1.1.1", "9.9.9.9"), ssh_pubkey=None, marker="z380m-alpine",
                 built=None, arch=None):
    """Write every file this project adds to the Alpine tree at `root`.  Returns a report dict."""
    arch = arch or ROOT_ARCH
    built = built or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    release = "unknown"
    try:
        release = open(os.path.join(root, "etc/alpine-release")).read().strip()
    except OSError:
        pass
    rep = {"enabled": {}, "missing": [], "release": release}

    # inittab: keep the stock file once
    it = os.path.join(root, "etc/inittab")
    alt = os.path.join(root, "etc/inittab.alpine")
    if os.path.isfile(it) and not os.path.lexists(alt):
        cur = open(it, encoding="utf-8", errors="replace").read()
        if not cur.startswith("# /etc/inittab -- z380m"):
            write_file(root, "etc/inittab.alpine", cur, 0o644)
    write_file(root, "etc/inittab", INITTAB)

    scripts = (("etc/z380m/sysinit.sh", SYSINIT_SH), ("etc/z380m/openrc.sh", OPENRC_SH), ("etc/z380m/postboot.sh", POSTBOOT_SH),
               ("etc/z380m/console.sh", CONSOLE_SH), ("etc/z380m/shutdown.sh", SHUTDOWN_SH), ("usr/local/sbin/z380m-usb", USB_SH))
    for rel, text in scripts:
        write_file(root, rel, text, 0o755)
    write_file(root, "etc/profile.d/z380m.sh", PROFILE_Z380M, 0o644)

    write_file(root, "etc/hostname", hostname + "\n")
    write_file(root, "etc/hosts", "127.0.0.1\tlocalhost localhost.localdomain %s\n::1\t\tlocalhost localhost.localdomain %s\n" % (hostname, hostname))
    write_file(root, "etc/fstab", FSTAB)
    write_file(root, "etc/motd", MOTD % {"release": release, "arch": arch})
    write_file(root, "etc/apk/repositories", "http://%s/alpine/%s/main\nhttp://%s/alpine/%s/community\n" % (MIRROR, BRANCH, MIRROR, BRANCH))
    write_file(root, "etc/resolv.conf", "# z380m: static resolvers; nothing rewrites this file -- edit as needed\n" + "".join("nameserver %s\n" % d for d in dns))
    write_file(root, "etc/network/interfaces", INTERFACES)
    write_file(root, "etc/z380m-release", "%s\nalpine %s %s\nbuilt %s\nbuilder build_alpine_rootfs.py %s\ncredit %s\n" % (marker, release, arch, built, VERSION, CREDIT))

    # OpenRC runlevels (symlinks), only for services whose init script exists
    plan = [(lvl, svc) for lvl, svcs in RUNLEVELS for svc in svcs]
    if ssh_pubkey:
        plan.append(("default", "sshd"))
    for lvl, svc in plan:
        if enable_service(root, svc, lvl):
            rep["enabled"].setdefault(lvl, []).append(svc)
        else:
            rep["missing"].append("%s/%s" % (lvl, svc))

    if ssh_pubkey:
        d = os.path.join(root, "root/.ssh")
        os.makedirs(d, exist_ok=True)
        os.chmod(d, 0o700)
        write_file(root, "root/.ssh/authorized_keys", ssh_pubkey, 0o600)
        if os.geteuid() == 0:
            os.chown(d, 0, 0)
    return rep


def owner_problems(root, strict):
    """Files in the tree that are not owned by root.  strict=True (a pristine minirootfs): anything but root:root, except
    /etc/shadow (root:shadow, group 42) is reported.  strict=False (after apk add): packages may legitimately use other
    system users/groups, so only owners that look like an ordinary login user of the build PC (uid 1000..65533) are
    reported -- that is what a tree unpacked by a non-root user would show."""
    bad = []
    for rel, st in walk_tree(root):
        if strict:
            if st.st_uid != 0 or (st.st_gid != 0 and rel != "etc/shadow"):
                bad.append("/%s (uid %d gid %d)" % (rel, st.st_uid, st.st_gid))
        elif 1000 <= st.st_uid < 65534 or 1000 <= st.st_gid < 65534:
            bad.append("/%s (uid %d gid %d)" % (rel, st.st_uid, st.st_gid))
    return bad


def walk_tree(root):
    """Yield (relative path, lstat) for everything below root (no mount crossing: caller makes sure nothing is mounted)."""
    stack = [""]
    while stack:
        rel = stack.pop()
        full = os.path.join(root, rel)
        try:
            entries = list(os.scandir(full))
        except OSError:
            continue
        for e in entries:
            r = os.path.join(rel, e.name)
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            yield r, st
            if stat.S_ISDIR(st.st_mode):
                stack.append(r)


def read_apk_db(root):
    """{package: version} from the apk database inside the tree (no apk, no qemu needed)."""
    res, cur = {}, {}
    path = os.path.join(root, "lib/apk/db/installed")
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                if "P" in cur:
                    res[cur["P"]] = cur.get("V", "?")
                cur = {}
            elif len(line) > 2 and line[1] == ":" and line[0] in "PV":
                cur[line[0]] = line[2:]
    if "P" in cur:
        res[cur["P"]] = cur.get("V", "?")
    return res


def verify_tree(root, need_packages=True, term=True):
    """Problems found in the finished tree (empty list = fine)."""
    bad = []

    def need(rel, kind=None):
        p = os.path.join(root, rel)
        if not os.path.lexists(p):
            bad.append("missing: /" + rel)
            return None
        return p

    for rel in ("etc/inittab", "etc/inittab.alpine", "etc/z380m/sysinit.sh", "etc/z380m/openrc.sh", "etc/z380m/postboot.sh",
                "etc/z380m/console.sh", "etc/z380m/shutdown.sh", "usr/local/sbin/z380m-usb", "etc/z380m-release", "etc/fstab",
                "etc/hostname", "etc/hosts", "etc/motd", "etc/network/interfaces", "etc/apk/repositories", "etc/resolv.conf",
                "bin/busybox", ROOT_LOADER, "sbin/init", "etc/profile.d/z380m.sh"):
        need(rel)
    if term:
        need("usr/local/bin/z380term")
    for rel in ("etc/z380m/sysinit.sh", "etc/z380m/openrc.sh", "etc/z380m/postboot.sh", "etc/z380m/console.sh",
                "etc/z380m/shutdown.sh", "usr/local/sbin/z380m-usb"):
        p = os.path.join(root, rel)
        if os.path.isfile(p):
            if not os.access(p, os.X_OK):
                bad.append("not executable: /" + rel)
            if open(p, "rb").read(10) != b"#!/bin/sh\n":
                bad.append("no #!/bin/sh first line: /" + rel)
    p = os.path.join(root, "sbin/init")
    if os.path.islink(p) and os.readlink(p) not in ("/bin/busybox", "../bin/busybox", "busybox"):
        bad.append("/sbin/init does not point to busybox: " + os.readlink(p))
    if need_packages:
        need("sbin/openrc")
        need("sbin/openrc-run")
        for svc in ("devfs", "dmesg", "mdev", "hostname", "bootmisc", "networking", "syslog", "mount-ro", "killprocs"):
            need("etc/init.d/" + svc)
        try:
            db = read_apk_db(root)
            miss = [x for x in REQUIRED_PKGS if x not in db]
            if miss:
                bad.append("packages not installed: " + " ".join(miss))
        except OSError as e:
            bad.append("cannot read the apk database: %s" % e)
    # marker
    mp = os.path.join(root, "etc/z380m-release")
    if os.path.isfile(mp):
        l = open(mp).read().splitlines()
        if len(l) < 3 or l[0] not in ("z380m-alpine", "z380m-selftest"):
            bad.append("marker /etc/z380m-release is wrong")
    # root account locked
    sp = os.path.join(root, "etc/shadow")
    if os.path.isfile(sp):
        for line in open(sp):
            f = line.split(":")
            if f[0] == "root" and not (f[1].startswith("*") or f[1].startswith("!")):
                bad.append("root has a password hash in /etc/shadow (the plan says: stays locked)")
    # nothing owned by an ordinary login user (a tree unpacked without root would be), no emulator left behind
    odd = owner_problems(root, strict=False)
    for o in odd[:5]:
        bad.append("owned by a login user instead of root: " + o)
    if len(odd) > 5:
        bad.append("... and %d more files with such owners" % (len(odd) - 5))
    for rel, st in walk_tree(root):
        if re.search(r"(^|/)qemu-[a-z0-9_]+(-static)?$", rel):
            bad.append("emulator file left in the tree: /" + rel)
    for d in ("proc", "sys", "dev", "tmp"):
        p = os.path.join(root, d)
        if os.path.isdir(p) and os.listdir(p):
            bad.append("/%s is not empty (%d entries)" % (d, len(os.listdir(p))))
    return bad


# ======================================================================================================================
# Host checks
# ======================================================================================================================
class Checks:
    def __init__(self):
        self.rows = []
        self.failed = False

    def add(self, state, text):
        self.rows.append((state, text))
        if state == "FAIL":
            self.failed = True
        print("        [%-4s] %s" % (state, text), flush=True)
        log("[%s] %s" % (state, text))

    def ok(self, t):
        self.add("OK", t)

    def warn(self, t):
        self.add("WARN", t)

    def fail(self, t):
        self.add("FAIL", t)

    def skip(self, t):
        self.add("SKIP", t)


def binfmt_entry():
    """The binfmt_misc entry that handles aarch64 ELF files: dict with name, enabled, interpreter, flags -- or None."""
    base = "/proc/sys/fs/binfmt_misc"
    if not os.path.isdir(base):
        return None
    cands = []
    for name in sorted(os.listdir(base)):
        p = os.path.join(base, name)
        if name in ("register", "status") or not os.path.isfile(p):
            continue
        try:
            txt = open(p).read()
        except OSError:
            continue
        d = {"name": name, "enabled": txt.startswith("enabled"), "interpreter": "", "flags": "", "magic": ""}
        for line in txt.splitlines():
            if line.startswith("interpreter "):
                d["interpreter"] = line.split(" ", 1)[1].strip()
            elif line.startswith("flags:"):
                d["flags"] = line.split(":", 1)[1].strip()
            elif line.startswith("magic "):
                d["magic"] = line.split(" ", 1)[1].strip()
        cands.append(d)
    for d in cands:
        if d["magic"].lower() == AARCH64_MAGIC:
            return d
    for d in cands:
        if d["name"] == "qemu-aarch64":
            return d
    return None


def free_bytes(path):
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize


def e2fsprogs_version():
    p = run(["mke2fs", "-V"], check=False)
    m = re.search(r"mke2fs (\d+)\.(\d+)\.(\d+)", p.out)
    return tuple(int(x) for x in m.groups()) if m else None


def net_check(scheme):
    url = "%s://%s/alpine/%s/main/aarch64/APKINDEX.tar.gz" % (scheme, MIRROR, BRANCH)
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "z380m-builder"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return True, "%s -> HTTP %d" % (url, r.status)
    except urllib.error.HTTPError as e:
        return False, "%s -> HTTP %d" % (url, e.code)
    except Exception as e:
        return False, "%s -> %s" % (url, e)


def resolve_source(ctx, chk):
    """Decide where the minirootfs comes from.  Sets ctx.src_kind ('tarball'|'dir') and ctx.src_path."""
    ctx.src_kind = ctx.src_path = None
    tb = ctx.tarball
    if not tb and not ctx.source_given:
        found = sorted(glob.glob(os.path.join(ctx.home, "alpine", "alpine-minirootfs-*-aarch64.tar.gz")))
        if len(found) == 1:
            tb = found[0]
        elif len(found) > 1:
            chk.fail("several minirootfs tarballs in ~/alpine (%s); name one with --tarball" % ", ".join(os.path.basename(x) for x in found))
            return
    if tb:
        if not os.path.isfile(tb):
            chk.fail("tarball not found: " + tb)
            return
        h2, h5 = file_hashes(tb)
        if ctx.tarball_sha256:
            if h2 != ctx.tarball_sha256.lower():
                chk.fail("tarball sha256 mismatch: file %s, you gave %s" % (h2, ctx.tarball_sha256.lower()))
                return
            how = "the sha256 you gave with --tarball-sha256"
        elif os.path.basename(tb) == REF_TARBALL:
            if h5 != REF_SHA512 or h2 != REF_SHA256:
                chk.fail("%s does not match the reference hashes (sha256 %s, sha512 %s...; expected sha256 %s, sha512 %s...). "
                         "Compare with the .sha256/.sha512 file Alpine publishes next to the download; do not use a file that differs." % (
                             REF_TARBALL, h2, h5[:16], REF_SHA256, REF_SHA512[:16]))
                return
            how = "the reference sha256 and the sha512 published in Alpine's docker-alpine repository"
        else:
            chk.fail("%s is not %s and no --tarball-sha256 given (its sha256 is %s)" % (os.path.basename(tb), REF_TARBALL, h2))
            return
        ctx.src_kind, ctx.src_path = "tarball", tb
        chk.ok("minirootfs tarball %s: hashes match %s" % (tb, how))
        return
    d = ctx.source
    if not os.path.isdir(d):
        chk.fail("no minirootfs found: no tarball in ~/alpine and no directory %s (use --tarball or --source)" % d)
        return
    problems = []
    try:
        rel = open(os.path.join(d, "etc/alpine-release")).read().strip()
    except OSError:
        rel = None
    if rel is None or not rel.startswith("3.24."):
        problems.append("etc/alpine-release is %r (expected 3.24.x)" % rel)
    bb = os.path.join(d, "bin/busybox")
    i = elf_info(bb) if os.path.isfile(bb) else None
    if not i or i["machine"] != ROOT_MACHINE:
        problems.append("bin/busybox is not an %s ELF file" % ROOT_ARCH)
    odd = owner_problems(d, strict=True)
    if odd:
        problems.append("%d files are not owned by root (e.g. %s): it was not extracted with sudo" % (len(odd), ", ".join(odd[:3])))
    if problems:
        chk.fail("%s: %s.  Extract the tarball again, as root, into an empty directory: sudo tar --numeric-owner -xpf <tarball> -C <dir>" % (d, "; ".join(problems)))
        return
    ctx.src_kind, ctx.src_path = "dir", d
    chk.ok("extracted minirootfs %s: Alpine %s, %s busybox, everything owned by root (no tarball to compare with)" % (d, rel, ROOT_ARCH))


def host_checks(ctx):
    chk = Checks()
    host_native = platform.machine() in ROOT_HOST_NAMES
    if os.geteuid() != 0:
        chk.fail("not root: run with sudo (chroot, mount and the ext4 image need it)")
    else:
        chk.ok("running as root")
    if platform.system() != "Linux":
        chk.fail("this must run on Linux")
    tools = ["mke2fs", "e2fsck", "dumpe2fs", "debugfs", "tune2fs", "tar", "mount", "umount", "chroot", "cp", "rm"]
    miss = [t for t in tools if not which(t)]
    if miss:
        chk.fail("missing tools: %s (e2fsprogs, tar, util-linux, coreutils)" % " ".join(miss))
    else:
        v = e2fsprogs_version()
        if v is None:
            chk.warn("could not read the e2fsprogs version")
        elif v < (1, 43, 0):
            chk.fail("e2fsprogs %d.%d.%d is too old (mke2fs -d needs 1.43 or newer)" % v)
        else:
            chk.ok("e2fsprogs %d.%d.%d (mke2fs -d works)" % v)
    if not ctx.no_apk:
        if host_native:
            chk.ok("host is %s: no emulation needed" % platform.machine())
        else:
            e = binfmt_entry()
            if e is None:
                chk.fail("no binfmt_misc handler for aarch64 ELF files (install qemu-user-static + binfmt-support; check /proc/sys/fs/binfmt_misc)")
            elif not e["enabled"]:
                chk.fail("binfmt_misc handler %s is disabled" % e["name"])
            else:
                ip = e["interpreter"]
                if not os.path.exists(ip):
                    chk.fail("binfmt handler %s points to %s, which does not exist" % (e["name"], ip))
                else:
                    ctx.binfmt = e
                    chk.ok("binfmt_misc handler %s: interpreter %s, flags %s%s" % (
                        e["name"], ip, e["flags"] or "-", "" if "F" in e["flags"] else
                        "  (no F flag: the interpreter will be copied into the work tree and removed again)"))
                    if "F" not in e["flags"]:
                        ii = elf_info(os.path.realpath(ip))
                        if ii is None or ii["interp"]:
                            chk.fail("the interpreter %s is not a static program and the handler has no F flag, so it cannot work inside the chroot. "
                                     "Install qemu-user-static (not qemu-user) and re-register: sudo apt install qemu-user-static binfmt-support" % ip)
                    q = which("qemu-aarch64-static")
                    if q:
                        chk.ok("qemu-aarch64-static found: " + q)
                    else:
                        chk.warn("qemu-aarch64-static not found in PATH (the registered interpreter is used)")
    else:
        chk.skip("emulation/binfmt checks (test mode: --no-apk)")
    if ctx.term_bin:
        if not os.path.isfile(ctx.term_bin):
            chk.fail("--term-bin file not found: " + ctx.term_bin)
        else:
            try:
                check_static_elf(ctx.term_bin, TERM_MACHINE, "z380term (--term-bin)")
                chk.ok("z380term binary %s: static, right CPU type" % ctx.term_bin)
            except Fail as e:
                chk.fail(str(e))
    else:
        if not os.path.isfile(ctx.term_src):
            chk.fail("z380term.c not found: %s (put it next to this script or use --term-src)" % ctx.term_src)
        elif not which(CC):
            chk.fail("compiler %s not found (sudo apt install gcc-aarch64-linux-gnu), or give a prebuilt binary with --term-bin" % CC)
        else:
            chk.ok("z380term.c found, compiler %s found" % CC)
    out_parent = ctx.out_dir if os.path.isdir(ctx.out_dir) else os.path.dirname(ctx.out_dir.rstrip("/")) or "/"
    try:
        fb = free_bytes(out_parent)
        if fb < 2 * (1 << 30):
            chk.fail("only %.1f GiB free where %s is (need about 2 GiB for the work tree and the image data)" % (fb / (1 << 30), ctx.out_dir))
        else:
            chk.ok("%.1f GiB free for %s" % (fb / (1 << 30), ctx.out_dir))
    except OSError as e:
        chk.fail("cannot check free space for %s: %s" % (ctx.out_dir, e))
    if ctx.work_dir and os.path.lexists(ctx.work_dir):
        m = mounts_under(ctx.work_dir)
        if m:
            chk.fail("old work directory %s still has mounts: %s" % (ctx.work_dir, " ".join(m)))
    resolve_source(ctx, chk)
    if ctx.ssh_pubkey_file:
        try:
            ctx.ssh_pubkey = ssh_key_text(ctx.ssh_pubkey_file)
            chk.ok("ssh public key: %d key line(s) from %s (sshd will be enabled; root stays without password)" % (len(ctx.ssh_pubkey.splitlines()), ctx.ssh_pubkey_file))
        except (Fail, OSError) as e:
            chk.fail(str(e))
    if not ctx.no_apk:
        got = {}
        for scheme in ("https", "http"):
            got[scheme] = net_check(scheme)
            (chk.ok if got[scheme][0] else chk.warn)("Alpine mirror via %s: %s" % (scheme, got[scheme][1]))
        if not got["https"][0] and not got["http"][0]:
            chk.fail("the Alpine mirror %s is not reachable (neither https nor http): apk cannot download packages" % MIRROR)
        ctx.https_ok = got["https"][0]
    else:
        chk.skip("Alpine mirror reachability (test mode: --no-apk)")
    return chk


# ======================================================================================================================
# Work tree, chroot, apk
# ======================================================================================================================
def private_mount_namespace():
    """Own mount namespace: every mount made below disappears when this process ends, even if it is killed."""
    CLONE_NEWNS = 0x00020000
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.unshare(CLONE_NEWNS) != 0:
        e = ctypes.get_errno()
        raise Fail("unshare(CLONE_NEWNS) failed: %s" % os.strerror(e))
    run(["mount", "--make-rprivate", "/"])


class ChrootEnv:
    NODES = (("null", 1, 3), ("zero", 1, 5), ("full", 1, 7), ("random", 1, 8), ("urandom", 1, 9), ("tty", 5, 0))

    def __init__(self, root, interp_copy=None):
        self.root = os.path.realpath(root)
        self.interp_copy = interp_copy
        self.copied = []

    def up(self):
        r = self.root
        run(["mount", "-t", "proc", "proc", r + "/proc"])
        run(["mount", "-t", "tmpfs", "-o", "mode=0755,size=32m", "tmpfs", r + "/dev"])
        for name, maj, mino in self.NODES:
            p = "%s/dev/%s" % (r, name)
            try:
                os.mknod(p, stat.S_IFCHR | 0o666, os.makedev(maj, mino))
                os.chmod(p, 0o666)
            except PermissionError:
                open(p, "w").close()
                run(["mount", "--bind", "/dev/" + name, p])
        if self.interp_copy:
            dst = r + self.interp_copy
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.realpath(self.interp_copy), dst)
            os.chmod(dst, 0o755)
            self.copied.append(dst)

    def down(self):
        for _ in range(3):
            mps = sorted(mounts_under(self.root), key=len, reverse=True)      # deepest first
            if not mps:
                break
            for mp in mps:
                if run(["umount", mp], check=False).returncode != 0:
                    run(["umount", "-l", mp], check=False)
        left = mounts_under(self.root)
        if left:
            raise Fail("could not unmount %s" % " ".join(left))
        for c in self.copied:
            try:
                os.unlink(c)
                d = os.path.dirname(c)
                while d.startswith(self.root + "/usr") and not os.listdir(d) and d != self.root + "/usr":
                    os.rmdir(d)
                    d = os.path.dirname(d)
            except OSError:
                pass
        self.copied = []

    def cmd(self, argv):
        return ["chroot", self.root] + list(argv)


def chroot_env_vars():
    return dict(CHROOT_ENV)


def prepare_tree(ctx):
    """Create the work tree from the tarball (or a copy of the extracted directory)."""
    wd = ctx.work_dir
    if os.path.lexists(wd):
        safe_rmtree(wd)
    os.makedirs(wd)
    open(os.path.join(wd, SENTINEL), "w").write("work directory of build_alpine_rootfs.py; safe to delete when nothing is mounted below\n")
    root = os.path.join(wd, "root")
    os.makedirs(root)
    if ctx.src_kind == "tarball":
        run(["tar", "--numeric-owner", "--same-owner", "-xpf", ctx.src_path, "-C", root])
    else:
        run(["cp", "-a", ctx.src_path + "/.", root])
    # identity of what we unpacked
    rel = open(os.path.join(root, "etc/alpine-release")).read().strip()
    if not rel.startswith("3.24."):
        raise Fail("unpacked tree is Alpine %r, expected 3.24.x" % rel)
    i = elf_info(os.path.join(root, "bin/busybox"))
    if not i or i["machine"] != ROOT_MACHINE:
        raise Fail("unpacked bin/busybox is not an %s ELF file" % ROOT_ARCH)
    bad = owner_problems(root, strict=True)
    if bad:
        raise Fail("%d files in the work tree are not owned by root (e.g. %s)" % (len(bad), ", ".join(bad[:3])))
    return root, rel


def host_resolv():
    try:
        txt = open("/etc/resolv.conf").read()
    except OSError:
        txt = ""
    if "nameserver" not in txt:
        txt = "nameserver 1.1.1.1\nnameserver 9.9.9.9\n"
    return txt


def apk(ch, args, **kw):
    return run(ch.cmd(["/sbin/apk"] + args), env=chroot_env_vars(), **kw)


def parse_missing(text):
    return re.findall(r"^\s+(\S+) \(no such package\)", text, re.M)


def chroot_selftest(ctx, ch):
    p = run(ch.cmd(["/bin/busybox", "uname", "-m"]), env=chroot_env_vars(), check=False)
    if p.returncode != 0 or p.out.strip() != ROOT_ARCH:
        raise Fail("chroot self-test failed: 'uname -m' in the Alpine tree said %r (exit %d), expected %r.\n"
                   "Is the binfmt_misc aarch64 handler enabled (flags F) and qemu-user-static installed?\n%s" % (p.out.strip(), p.returncode, ROOT_ARCH, tail(p.out)))
    p2 = run(ch.cmd(["/bin/busybox", "cat", "/etc/alpine-release"]), env=chroot_env_vars())
    p3 = run(ch.cmd(["/sbin/apk", "--version"]), env=chroot_env_vars(), check=False)
    if p3.returncode != 0:
        raise Fail("apk does not run in the chroot: " + tail(p3.out))
    return "uname -m: %s | /etc/alpine-release: %s | %s" % (ROOT_ARCH, p2.out.strip(), p3.out.strip())


def repos_text(scheme):
    return "%s://%s/alpine/%s/main\n%s://%s/alpine/%s/community\n" % (scheme, MIRROR, BRANCH, scheme, MIRROR, BRANCH)


def index_problems(out):
    """Lines in apk's output that say a repository index could not be fetched or verified.  (apk then goes on to report every
    package as 'no such package', which would be a misleading diagnosis.)"""
    return [l for l in out.splitlines() if re.match(r"^(WARNING|ERROR): (fetching )?(https?|ftp)://", l)]


def simulate_packages(ctx, ch):
    """apk add --simulate against the real v3.24 index.  Returns (required, optional_that_exist, dropped_optional)."""
    req = list(REQUIRED_PKGS)
    opt = [] if ctx.no_optional else list(OPTIONAL_PKGS)
    dropped = []
    http_tried = False
    repo_file = os.path.join(ctx.root, "etc/apk/repositories")
    if ctx.https_ok is False and "https://" in open(repo_file).read():
        write_file(ctx.root, "etc/apk/repositories", repos_text("http"))
        http_tried = True
        note("https to the mirror did not work in the preflight check: using http for the build (packages are signature-checked either way)")
    for _ in range(6):
        p = apk(ch, ["add", "--no-cache", "--simulate"] + req + opt, check=False)
        if p.returncode == 0:
            return req, opt, dropped
        ip = index_problems(p.out)
        if ip:
            if not http_tried and "https://" in open(repo_file).read():
                http_tried = True
                note("apk could not read the package index over https; retrying over http (packages are signature-checked either way)")
                write_file(ctx.root, "etc/apk/repositories", repos_text("http"))
                continue
            raise Fail("apk could not read the package index from the mirror:\n  " + "\n  ".join(ip[:6]) +
                       "\nCheck the network of this PC (and the date/time if the message mentions certificates).")
        miss = parse_missing(p.out)
        req_gone = [m for m in miss if m in req]
        if req_gone:
            raise Fail("these REQUIRED packages do not exist in the Alpine %s %s index: %s\n%s" % (BRANCH, ROOT_ARCH, " ".join(req_gone), tail(p.out)))
        gone = [m for m in miss if m in opt]
        if gone:
            dropped += gone
            opt = [x for x in opt if x not in gone]
            continue
        raise Fail("apk add --simulate failed:\n" + tail(p.out, 30))
    raise Fail("apk add --simulate did not converge")


def install_packages(ctx, ch, req, opt):
    def show(line):
        return bool(re.match(r"^\(\d+/\d+\) (Installing|Purging|Upgrading)|^OK:|^ERROR|^WARNING", line))
    say("apk add (required): %s" % " ".join(req))
    rc, out = run_stream(ch.cmd(["/sbin/apk", "add", "--no-cache"] + req), chroot_env_vars(), show, 3600)
    if rc != 0:
        raise Fail("apk add failed (exit %d):\n%s" % (rc, tail(out, 30)))
    done_opt = []
    if opt:
        say("apk add (optional): %s" % " ".join(opt))
        rc, out = run_stream(ch.cmd(["/sbin/apk", "add", "--no-cache"] + opt), chroot_env_vars(), show, 3600)
        if rc != 0:
            ctx.warnings.append("optional packages: apk add failed (exit %d); continuing without some of them:\n%s" % (rc, tail(out, 10)))
        else:
            done_opt = opt
    return done_opt


def build_term(ctx, workdir):
    if ctx.term_bin:
        out = ctx.term_bin
    else:
        out = os.path.join(workdir, "z380term")
        p = run([CC, "-static", "-O2", "-s", "-Wall", "-o", out, ctx.term_src], check=False)
        if p.returncode != 0:
            raise Fail("compiling z380term failed (static libc missing? sudo apt install libc6-dev-arm64-cross):\n" + tail(p.out))
        if p.out.strip():
            note("compiler output: " + tail(p.out, 5).replace("\n", " | "))
    check_static_elf(out, TERM_MACHINE, "z380term")
    return out


# ======================================================================================================================
# ext4 image
# ======================================================================================================================
MKE2FS_CONF = '''[defaults]
	base_features = %(base)s
	blocksize = 4096
	inode_size = 256
	inode_ratio = 16384
	enable_periodic_fsck = 0
	lazy_itable_init = 1

[fs_types]
	ext4 = {
		features = %(feat)s
		inode_size = 256
	}
'''


def parse_dumpe2fs(text):
    d = {}
    for line in text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            d.setdefault(k.strip(), v.strip())
    return d


def make_image(ctx, root, img):
    blocks = ctx.size_bytes // BLOCK
    conf = os.path.join(ctx.work_dir, "mke2fs.conf")
    open(conf, "w").write(MKE2FS_CONF % {"base": ",".join(EXT4_BASE), "feat": ",".join(EXT4_FEATURES)})
    env = dict(os.environ, MKE2FS_CONFIG=conf, PATH=EXTRA_PATH)
    if os.path.lexists(img):
        os.unlink(img)
    with open(img, "wb") as f:
        f.truncate(ctx.size_bytes)
    run(["mke2fs", "-q", "-t", "ext4", "-b", str(BLOCK), "-L", LABEL, "-m", "1",
         "-E", "root_owner=0:0,lazy_itable_init=1,nodiscard", "-d", root, "-F", img, str(blocks)], env=env)
    run(["tune2fs", "-o", "^acl,^user_xattr", img])


def verify_image(ctx, img, tmpdir):
    """Checks on the finished image.  Returns a list of 'OK ...' lines; raises Fail on any problem."""
    res = []
    size = os.path.getsize(img)
    if size > MAX_IMAGE:
        raise Fail("image is %d bytes, more than the limit %d" % (size, MAX_IMAGE))
    if size % 512 or size % BLOCK:
        raise Fail("image size %d is not a multiple of %d" % (size, BLOCK))
    res.append("size %d bytes (limit %d), multiple of %d" % (size, MAX_IMAGE, BLOCK))

    p = run(["e2fsck", "-fn", img], check=False)
    if p.returncode != 0:
        raise Fail("e2fsck -fn reported problems (exit %d):\n%s" % (p.returncode, tail(p.out, 30)))
    res.append("e2fsck -fn: clean (%s)" % (re.findall(r"^.*\d+/\d+ files.*blocks\s*$", p.out, re.M) or ["no summary line"])[-1].strip())

    d = parse_dumpe2fs(run(["dumpe2fs", "-h", img], check=False).out)
    feats = set(d.get("Filesystem features", "").split())
    if not feats:
        raise Fail("dumpe2fs printed no feature list")
    extra = sorted(feats - EXT4_ALLOWED)
    if extra:
        raise Fail("the image has features outside the Linux-3.18 allow-list: %s" % " ".join(extra))
    missing = sorted({"extent", "flex_bg", "filetype"} - feats)
    if missing:
        raise Fail("expected features missing: %s" % " ".join(missing))
    res.append("features (all in the allow-list): " + " ".join(sorted(feats)))
    if d.get("Filesystem state") != "clean":
        raise Fail("filesystem state is %r" % d.get("Filesystem state"))
    if d.get("Block size") != str(BLOCK):
        raise Fail("block size is %r" % d.get("Block size"))
    if d.get("Filesystem volume name") != LABEL:
        raise Fail("volume name is %r" % d.get("Filesystem volume name"))
    dm = d.get("Default mount options", "")
    if dm not in ("(none)", ""):
        raise Fail("default mount options are %r (expected none)" % dm)
    jf = d.get("Journal features", "(none)")
    if "checksum" in jf or "64bit" in jf:
        raise Fail("journal features %r are not allowed" % jf)
    res.append("state clean, 4096-byte blocks, label %s, default mount options none, journal features %s" % (LABEL, jf))

    # look inside the image the way a reader would (no mount needed)
    def dbg(cmd):
        return run(["debugfs", "-R", cmd, img], check=False).out

    if re.search(r"\s", tmpdir):
        raise Fail("the work directory path contains white space (%r); debugfs cannot dump files there" % tmpdir)

    marker = dbg("cat /etc/z380m-release").splitlines()
    exp = ctx.marker_first
    if not marker or marker[0].strip() != exp:
        raise Fail("marker inside the image: first line %r, expected %r" % (marker[:1], exp))
    res.append("marker inside the image: %s | %s | %s" % tuple((marker + ["", "", ""])[:3]))
    for path, want in (("/sbin/init", "symlink"), ("/bin/busybox", "regular"), ("/" + ROOT_LOADER, "regular"),
                       ("/etc/inittab", "regular"), ("/etc/inittab.alpine", "regular"), ("/usr/local/bin/z380term", "regular"),
                       ("/etc/z380m/console.sh", "regular"), ("/etc/z380m/sysinit.sh", "regular"), ("/usr/local/sbin/z380m-usb", "regular"),
                       ("/etc/fstab", "regular")) + ((("/sbin/openrc", "regular"), ("/sbin/openrc-run", "regular")) if not ctx.no_apk else ()):
        s = dbg("stat " + path)
        m = re.search(r"Type: (\w+)", s)
        u = re.search(r"User:\s+(\d+)\s+Group:\s+(\d+)", s)
        if not m or m.group(1) != want:
            raise Fail("inside the image: %s is %s (expected %s)\n%s" % (path, m.group(1) if m else "missing", want, tail(s, 5)))
        if not u or u.group(1) != "0":
            raise Fail("inside the image: %s is not owned by root" % path)
    res.append("key files present, regular/symlink as expected, owned by root")
    s = dbg("stat /usr/bin/qemu-aarch64-static")
    if "Type:" in s:
        raise Fail("the emulator binary is inside the image")
    tb = os.path.join(tmpdir, "z380term.from-image")
    dbg("dump /usr/local/bin/z380term " + tb)
    check_static_elf(tb, TERM_MACHINE, "z380term inside the image")
    res.append("z380term inside the image: static ELF, right CPU type")
    bb = os.path.join(tmpdir, "busybox.from-image")
    dbg("dump /bin/busybox " + bb)
    i = elf_info(bb)
    if not i or i["machine"] != ROOT_MACHINE:
        raise Fail("busybox inside the image is not an %s ELF file" % ROOT_ARCH)
    res.append("busybox inside the image: %s ELF" % ROOT_ARCH)
    init_inittab = dbg("cat /etc/inittab")
    if "::respawn:/etc/z380m/console.sh" not in init_inittab:
        raise Fail("inittab inside the image has no console respawn entry")
    res.append("inittab inside the image has the console respawn entry")
    return res


# ======================================================================================================================
# main
# ======================================================================================================================
class Ctx:
    pass


def parse_args(argv):
    ap = argparse.ArgumentParser(
        description="Build the Alpine root filesystem image for the Z380M.  Needs root (sudo).  Never flashes anything.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="examples:\n"
               "  sudo /usr/bin/python3 build_alpine_rootfs.py --preflight-only\n"
               "  sudo /usr/bin/python3 build_alpine_rootfs.py\n"
               "  sudo /usr/bin/python3 build_alpine_rootfs.py --size-mb 1024 --ssh-pubkey ~/.ssh/id_ed25519.pub\n"
               "  python3 build_alpine_rootfs.py --dump-config /tmp/cfg      (no root: only writes the config files for reading)\n")
    ap.add_argument("--tarball", metavar="FILE", help="Alpine minirootfs tarball (default: the only alpine-minirootfs-*-aarch64.tar.gz in ~/alpine)")
    ap.add_argument("--tarball-sha256", metavar="HEX", help="accept a tarball other than %s if it has this sha256 (check it against Alpine's own .sha256 file first)" % REF_TARBALL)
    ap.add_argument("--source", metavar="DIR", default=None, help="already extracted minirootfs (default ~/alpine/root); only used when no tarball is found")
    ap.add_argument("--out-dir", metavar="DIR", default=None, help="output directory (default ~/linux_alpine_v3)")
    ap.add_argument("--size-mb", type=int, metavar="N", help="image size in MiB (default: the maximum, %d bytes)" % MAX_IMAGE)
    ap.add_argument("--term-src", metavar="FILE", default=os.path.join(HERE, "z380term.c"), help="z380term.c (default: next to this script)")
    ap.add_argument("--term-bin", metavar="FILE", help="use this already built static aarch64 z380term instead of compiling")
    ap.add_argument("--ssh-pubkey", metavar="FILE", help="install this public key for root and enable sshd (root keeps no password)")
    ap.add_argument("--hostname", default="z380m")
    ap.add_argument("--dns", default="1.1.1.1,9.9.9.9", help="resolvers for /etc/resolv.conf (default 1.1.1.1,9.9.9.9)")
    ap.add_argument("--no-optional", action="store_true", help="skip the optional packages")
    ap.add_argument("--preflight-only", action="store_true", help="host checks, unpack, chroot self-test and 'apk add --simulate'; install nothing, write no image")
    ap.add_argument("--keep-work", action="store_true", help="keep the work tree after a successful build")
    ap.add_argument("--dump-config", metavar="DIR", help="write the configuration files this script adds into DIR and exit (no root needed)")
    ap.add_argument("--no-apk", action="store_true", help="TEST MODE: no chroot/apk/network; the image gets the marker 'z380m-selftest' so the boot ramdisk refuses it")
    return ap.parse_args(argv)


def main(argv=None):
    global LOGF
    a = parse_args(argv if argv is not None else sys.argv[1:])
    if a.preflight_only and a.no_apk:
        print("--preflight-only and --no-apk exclude each other (preflight is the apk/chroot check)")
        return 2
    os.environ["PATH"] = os.environ.get("PATH", "") + ":" + EXTRA_PATH
    uname, uid, gid, home = real_user()

    if a.dump_config:
        os.makedirs(a.dump_config, exist_ok=True)
        rep = write_config(a.dump_config, hostname=a.hostname, dns=[d for d in a.dns.split(",") if d], ssh_pubkey=None)
        n = sum(1 for _, st in walk_tree(a.dump_config) if stat.S_ISREG(st.st_mode))
        print("wrote %d files into %s (runlevel links are only made when the init scripts exist, so none here)" % (n, a.dump_config))
        return 0

    ctx = Ctx()
    ctx.home = home
    ctx.tarball = os.path.abspath(os.path.expanduser(a.tarball)) if a.tarball else None
    ctx.tarball_sha256 = a.tarball_sha256
    ctx.source_given = a.source is not None
    ctx.source = os.path.abspath(os.path.expanduser(a.source)) if a.source else os.path.join(home, "alpine", "root")
    ctx.out_dir = os.path.abspath(os.path.expanduser(a.out_dir)) if a.out_dir else os.path.join(home, "linux_alpine_v3")
    ctx.work_dir = os.path.join(ctx.out_dir, "work-alpine-rootfs")
    ctx.term_src = os.path.abspath(os.path.expanduser(a.term_src))
    ctx.term_bin = os.path.abspath(os.path.expanduser(a.term_bin)) if a.term_bin else None
    ctx.ssh_pubkey_file = os.path.abspath(os.path.expanduser(a.ssh_pubkey)) if a.ssh_pubkey else None
    ctx.ssh_pubkey = None
    ctx.no_optional = a.no_optional
    ctx.no_apk = a.no_apk
    ctx.https_ok = None
    ctx.binfmt = None
    ctx.warnings = []
    if a.size_mb is not None:
        ctx.size_bytes = a.size_mb * 1024 * 1024
        if ctx.size_bytes > MAX_IMAGE:
            print("--size-mb too large: the image may not exceed %d bytes (%d MiB)" % (MAX_IMAGE, MAX_IMAGE // (1 << 20)))
            return 2
        if ctx.size_bytes < 64 * 1024 * 1024:
            print("--size-mb must be at least 64")
            return 2
    else:
        ctx.size_bytes = MAX_IMAGE
    ctx.size_bytes -= ctx.size_bytes % BLOCK
    ctx.marker_first = "z380m-selftest" if a.no_apk else "z380m-alpine"

    print("build_alpine_rootfs.py %s -- Alpine %s for the Z380M -- %s" % (VERSION, RELEASE, CREDIT))
    if os.geteuid() == 0:
        os.makedirs(ctx.out_dir, exist_ok=True)
        give_to_user(ctx.out_dir, uid, gid)
    elif not os.path.isdir(ctx.out_dir):
        os.makedirs(ctx.out_dir, exist_ok=True)
    LOGF = open(os.path.join(ctx.out_dir, "build_alpine_rootfs.log"), "w")
    log("build_alpine_rootfs.py %s started %s as uid %d (real user %s)" % (VERSION, datetime.datetime.now().isoformat(), os.geteuid(), uname))
    log(CREDIT)
    log("argv: " + " ".join(sys.argv))

    total = 3 if a.preflight_only else 9
    try:
        say("[1/%d] host checks" % total)
        chk = host_checks(ctx)
        if chk.failed:
            print("\nPREFLIGHT FAILED -- fix the FAIL lines above and run again.  Nothing was changed.")
            return 2
        if os.geteuid() != 0:
            raise Fail("not root")

        private_mount_namespace()
        say("[2/%d] unpacking the minirootfs into the work tree (%s)" % (total, ctx.work_dir))
        root, rel = prepare_tree(ctx)
        ctx.root = root
        note("Alpine %s, %s busybox, everything root-owned" % (rel, ROOT_ARCH))

        ch = None
        if not a.no_apk:
            interp = None
            if ctx.binfmt and "F" not in ctx.binfmt["flags"]:
                interp = ctx.binfmt["interpreter"]
            ch = ChrootEnv(root, interp)
            ch.up()
            write_file(root, "etc/resolv.conf", host_resolv())
            say("[3/%d] chroot self-test (%s) and apk dry run against the %s %s index" % (total, "native" if not ctx.binfmt else "through qemu-user", BRANCH, ROOT_ARCH))
            note(chroot_selftest(ctx, ch))
            req, opt, dropped = simulate_packages(ctx, ch)
            note("apk add --simulate: OK for %d required + %d optional packages" % (len(req), len(opt)))
            if dropped:
                ctx.warnings.append("optional packages not in the index, skipped: " + " ".join(dropped))
                note("not in the index, skipped: " + " ".join(dropped))
            if a.preflight_only:
                ch.down()
                print("\nPREFLIGHT PASSED -- the %s chroot works%s, apk reaches the index and all required packages resolve." % (ROOT_ARCH, " through qemu-user" if ctx.binfmt else " natively (no emulator needed on this host)"))
                print("Nothing was installed, no image was written, nothing was flashed.")
                if not a.keep_work:
                    safe_rmtree(ctx.work_dir)
                return 0
            say("[4/%d] installing packages (%s; expect several minutes)" % (total, "apk runs under qemu-user" if ctx.binfmt else "apk runs natively"))
            done_opt = install_packages(ctx, ch, req, opt)
            db = read_apk_db(root)
            miss = [p for p in REQUIRED_PKGS if p not in db]
            if miss:
                raise Fail("after apk add these packages are still not installed: " + " ".join(miss))
            note("%d packages installed (all %d required ones present)" % (len(db), len(REQUIRED_PKGS)))
            ch.down()
        else:
            say("[3/%d] chroot/apk skipped (TEST MODE --no-apk: the image will NOT be bootable)" % total)
            say("[4/%d] packages skipped (test mode)" % total)

        say("[5/%d] z380term" % total)
        term = build_term(ctx, ctx.work_dir)
        os.makedirs(os.path.join(root, "usr/local/bin"), exist_ok=True)
        dst = os.path.join(root, "usr/local/bin/z380term")
        if os.path.lexists(dst):
            os.unlink(dst)
        shutil.copy2(term, dst)
        os.chmod(dst, 0o755)
        os.chown(dst, 0, 0)
        zh = sha256_file(dst)
        if TERM_MACHINE == 183:
            note("z380term: static aarch64 ELF, sha256 %s" % zh)
        else:
            note("z380term (TEST MODE, cpu type %d): sha256 %s" % (TERM_MACHINE, zh))

        say("[6/%d] configuration" % total)
        rep = write_config(root, hostname=a.hostname, dns=[d for d in a.dns.split(",") if d], ssh_pubkey=ctx.ssh_pubkey,
                           marker=ctx.marker_first)
        for lvl, svcs in rep["enabled"].items():
            note("runlevel %-8s: %s" % (lvl, " ".join(svcs)))
        if rep["missing"] and not a.no_apk:
            ctx.warnings.append("OpenRC services without an init script (not enabled): " + " ".join(rep["missing"]))
        # clean-up of build leftovers
        for rel_dir in ("var/cache/apk", "tmp", "root"):
            p = os.path.join(root, rel_dir)
            if os.path.isdir(p):
                for n in os.listdir(p):
                    if rel_dir == "root" and n not in (".ash_history", ".cache"):
                        continue
                    run(["rm", "-rf", "--one-file-system", "--", os.path.join(p, n)])

        say("[7/%d] checking the finished tree" % total)
        bad = verify_tree(root, need_packages=not a.no_apk)
        if bad:
            raise Fail("tree check failed:\n  " + "\n  ".join(bad))
        note("tree OK (files, modes, shebangs, root ownership, locked root account, no emulator, empty /proc /sys /dev /tmp)")
        pk = read_apk_db(root) if not a.no_apk else {}
        tree_bytes = sum(st.st_size for _, st in walk_tree(root) if stat.S_ISREG(st.st_mode))
        note("tree holds %.1f MiB of file data" % (tree_bytes / 1048576.0))
        if tree_bytes * 1.3 + 64 * 1048576 > ctx.size_bytes:
            raise Fail("the tree (%.0f MiB) does not fit comfortably into an image of %d MiB" % (tree_bytes / 1048576.0, ctx.size_bytes // 1048576))

        say("[8/%d] building the ext4 image (%d bytes, sparse file)" % (total, ctx.size_bytes))
        base = "system_alpine" + (".selftest" if a.no_apk else "") + ".ext4"
        final = os.path.join(ctx.out_dir, base)
        part = final + ".partial"
        make_image(ctx, root, part)

        say("[9/%d] verifying the image, writing checksum" % total)
        for line in verify_image(ctx, part, ctx.work_dir):
            note("OK  " + line)
        digest = sha256_file(part)
        os.replace(part, final)
        with open(final + ".sha256", "w") as f:
            f.write("%s  %s\n" % (digest, base))
        with open(os.path.join(ctx.out_dir, "system_alpine.packages.txt"), "w") as f:
            f.write("\n".join("%s-%s" % (k, v) for k, v in sorted(pk.items())) + ("\n" if pk else ""))
        for p in (final, final + ".sha256", os.path.join(ctx.out_dir, "system_alpine.packages.txt"), LOGF.name):
            give_to_user(p, uid, gid)
        if not a.keep_work:
            safe_rmtree(ctx.work_dir)
        else:
            note("work tree kept in " + ctx.work_dir + " (root-owned; remove with: sudo rm -rf --one-file-system '%s')" % ctx.work_dir)

        print("")
        print("DONE.")
        print("  image   : %s" % final)
        print("  size    : %d bytes (limit %d)%s" % (os.path.getsize(final), MAX_IMAGE, "  TEST IMAGE, marker z380m-selftest: the ramdisk will refuse to boot it" if a.no_apk else ""))
        print("  sha256  : %s" % digest)
        print("  packages: %d (list in %s)" % (len(pk), os.path.join(ctx.out_dir, "system_alpine.packages.txt")))
        for w in ctx.warnings:
            print("  WARNING : " + w)
        print("  Checked here: the image is a clean ext4 with only 3.18-safe features and the expected files.")
        print("  NOT checked here (cannot be, on the PC): that the tablet's 3.18.35 kernel mounts it and that Alpine's aarch64 userland runs on that kernel.")
        print("  Nothing was flashed.  Next, still PC-only: python3 build_boot_v3.py z380term.c %s" % ctx.out_dir)
        return 0
    except Fail as e:
        print("\nERROR: %s" % e)
        log("ERROR: %s" % e)
        print("The log is %s.  Mounts made by this script live in a private namespace and are gone now." % (LOGF.name if LOGF else "-"))
        if os.path.lexists(ctx.work_dir):
            print("Work tree left in %s (root-owned; the next run replaces it)." % ctx.work_dir)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130
    finally:
        if LOGF:
            LOGF.flush()
            give_to_user(LOGF.name, uid, gid)


if __name__ == "__main__":
    sys.exit(main())
