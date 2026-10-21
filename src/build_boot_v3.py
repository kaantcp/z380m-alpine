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
# Z380M Alpine boot image v3: official kernel (byte-identical) + static BusyBox + z380term + a switch_root /init.
# Derived from build_console_boot_v2.py (md5 9d884201cb108264817863c4355a7500).  This script only reads files on the
# PC and writes new files in the output directory.  It never talks to the tablet; flashing is a separate step.
#
# Usage:
#   python3 build_boot_v3.py [z380term.c] [out_dir] [--window N]     build ~/linux_alpine_v3/boot_alpine_full.bin
#   python3 build_boot_v3.py --dump-scripts DIR [--window N]          only write the ramdisk scripts to DIR (for review/tests)
#
# Env overrides (same names as v2):
#   Z380_SRC_BOOT     official boot image (default ~/official_ref/boot.bin)
#   Z380_BUSYBOX      static aarch64 BusyBox (default ~/bbx/usr/bin/busybox)
#   Z380_CC           compiler (default aarch64-linux-gnu-gcc)
#   Z380_ELF_MACHINE  expected ELF e_machine (default 183 = AArch64)
import argparse, gzip, hashlib, os, re, shutil, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
SRC = os.environ.get("Z380_SRC_BOOT", HOME + "/official_ref/boot.bin")
BB = os.environ.get("Z380_BUSYBOX", HOME + "/bbx/usr/bin/busybox")
CC = os.environ.get("Z380_CC", "aarch64-linux-gnu-gcc")
MACHINE = int(os.environ.get("Z380_ELF_MACHINE", "183"))   # 183 = AArch64
PART = 0xFF7000                                            # boot partition size (GPT)
MAGIC = bytes.fromhex("88168858")                          # MTK wrapper magic
V2_IMAGE = HOME + "/linux_console_v2/boot_linux_console_full.bin"   # known-good console image, compared if present

# GPT numbers from the printgpt log (evidence/01), converted to 512-byte sectors; the init uses them as a cross-check.
SYS_START = 0x20ba5000 // 512     # system
SYS_SECT = 0xdfc00000 // 512
EXP_START = 0x76a5000 // 512      # expdb
EXP_SECT = 0xa00000 // 512

# ------------------------------------------------------------------------------------------------------------------
# /init  (PID 1 of the ramdisk)
# ------------------------------------------------------------------------------------------------------------------
INIT = r'''#!/bin/busybox sh
# Z380M Alpine boot init v3 -- ramdisk stage.  PID 1: this script must never exit.
# Stock 3.18.35 kernel + static BusyBox + z380term.
#   normal : /dev -> USB serial gadget -> live boot log on screen + serial -> short rescue window (tap VOL or touch)
#            -> find + mount "system" (ext4) -> marker file -> userland smoke test -> move /sys /dev /proc -> switch_root
#   failure: rescue console (screen + USB serial) that shows this log; "retry-boot" tries again.
# The only raw write to any partition is a text log dump into "expdb" (as v2 did), and only when that partition's start
# and size in sysfs match the GPT numbers.  It never writes boot, lk, nvram, system or anything else.
export PATH=/bin:/sbin:/usr/bin:/usr/sbin HOME=/root TERM=linux PS1='z380m# '

# Z380_* are test hooks (the kernel never sets them); build_boot_v3.py --window N rewrites the WIN default.
SYS=${Z380_SYSFS:-/sys}
FSLIST=${Z380_FSLIST:-/proc/filesystems}
WIN=${Z380_WINDOW:-5}
TTYWAIT=${Z380_TTYWAIT:-10}
BLKWAIT=${Z380_BLKWAIT:-30}
EVOVR=${Z380_EVDEVS:-}
SYSNAME=${Z380_SYSPART:-system}
CONSDEV=${Z380_CONSOLE:-/dev/console}
NEWROOT=/newroot
BL=$SYS/class/leds/lcd-backlight/brightness
G=$SYS/class/android_usb/android0
LOG=/tmp/initlog
SYS_START=@SYS_START@
SYS_SECT=@SYS_SECT@
EXP_START=@EXP_START@
EXP_SECT=@EXP_SECT@
TTY=
VIEWPID=
LAUNCHPID=
BOOTFAIL=
MOVEOPT=
CONSOPT=
EXPNOTE=

/bin/busybox mount -t proc proc /proc
/bin/busybox --install -s /bin
mount -t sysfs sysfs /sys
mount -t tmpfs tmpfs /tmp

log() {
  up=; [ -r /proc/uptime ] && read up _ < /proc/uptime
  echo "${up:-?} $*" >> $LOG
  [ -w /dev/kmsg ] && echo "z380m-init: $*" > /dev/kmsg
  return 0
}
bl() { [ -w $BL ] && echo "$1" > $BL; return 0; }
hasfs() { grep -q "[[:space:]]$1\$" "$FSLIST" 2>/dev/null; }

# ---- device nodes ------------------------------------------------------------------------------------------------
mkdev() { [ -e "$1" ] || mknod -m "$2" "$1" "$3" "$4" "$5" 2>/dev/null; return 0; }
sysnode() {   # sysnode <sysfs dir> <node path> <b|c> [mode] : create a node from the "dev" file in sysfs
  [ -e "$2" ] && return 0
  [ -r "$1/dev" ] || return 1
  mm=$(cat "$1/dev") || return 1
  mkdir -p "${2%/*}"
  mknod -m "${4:-660}" "$2" "$3" "${mm%%:*}" "${mm##*:}"
}
mk_input_nodes() {
  for d in $SYS/class/input/event*; do
    [ -d "$d" ] && sysnode "$d" "/dev/input/${d##*/}" c
  done
  return 0
}

if hasfs devtmpfs && mount -t devtmpfs devtmpfs /dev 2>/dev/null; then
  DEVMODE=devtmpfs
else
  mount -t tmpfs -o mode=0755 tmpfs /dev
  DEVMODE=tmpfs
fi
mkdev /dev/console 600 c 5 1
mkdev /dev/null 666 c 1 3
mkdev /dev/zero 666 c 1 5
mkdev /dev/full 666 c 1 7
mkdev /dev/random 666 c 1 8
mkdev /dev/urandom 666 c 1 9
mkdev /dev/kmsg 600 c 1 11
mkdev /dev/tty 666 c 5 0
mkdir -p /dev/pts
mount -t devpts devpts /dev/pts 2>/dev/null
mkdev /dev/ptmx 666 c 5 2
mdev -s 2>/dev/null
sysnode $SYS/class/graphics/fb0 /dev/fb0 c
mk_input_nodes
hostname z380m

log "init v3 start: kernel $(uname -r) $(uname -m), /dev=$DEVMODE"
log "z380m-alpine by kaantcp - https://github.com/kaantcp"
log "cmdline: $(cat /proc/cmdline)"
log "fs support: ext4=$(hasfs ext4 && echo yes || echo NO) tmpfs=$(hasfs tmpfs && echo yes || echo NO) devtmpfs=$(hasfs devtmpfs && echo yes || echo NO) devpts=$(hasfs devpts && echo yes || echo NO)"
log "nodes: fb0=$([ -c /dev/fb0 ] && echo yes || echo NO) ptmx=$([ -c /dev/ptmx ] && echo yes || echo NO) input=$(ls /dev/input 2>/dev/null | tr '\n' ' ')"

# ---- partitions --------------------------------------------------------------------------------------------------
find_part() {   # find_part <PARTNAME> <start> <sectors> : print the sysfs dir; by name first, else by exact geometry
  for u in $SYS/class/block/*/uevent; do
    [ -r "$u" ] || continue
    if grep -q "^PARTNAME=$1\$" "$u" 2>/dev/null; then echo "${u%/uevent}"; return 0; fi
  done
  for fd in $SYS/class/block/*; do
    [ -r "$fd/start" ] || continue
    if [ "$(cat $fd/start 2>/dev/null)" = "$2" ] && [ "$(cat $fd/size 2>/dev/null)" = "$3" ]; then echo "$fd"; return 0; fi
  done
  return 1
}
sys_node() {   # find the system partition, create /dev/part_system, leave the sysfs dir in $SD
  SD=$(find_part "$SYSNAME" $SYS_START $SYS_SECT) || return 1
  sysnode "$SD" /dev/part_system b 660
}
log_parts() {
  for pu in $SYS/class/block/*/uevent; do
    [ -r "$pu" ] || continue
    pd=${pu%/uevent}
    [ -r "$pd/start" ] || continue
    pn=?
    while IFS== read pk pv; do
      [ "$pk" = PARTNAME ] && pn=$pv
    done < "$pu"
    log "part ${pd##*/} name=$pn start=$(cat $pd/start 2>/dev/null) sectors=$(cat $pd/size 2>/dev/null) dev=$(cat $pd/dev 2>/dev/null)"
  done
  return 0
}
expdb_node() {   # /dev/part_expdb only if the geometry equals the GPT numbers
  [ -b /dev/part_expdb ] && return 0
  ed=$(find_part expdb $EXP_START $EXP_SECT) || return 1
  if [ "$(cat $ed/start 2>/dev/null)" != "$EXP_START" ] || [ "$(cat $ed/size 2>/dev/null)" != "$EXP_SECT" ]; then
    [ -z "$EXPNOTE" ] && log "expdb: ${ed##*/} geometry differs from the GPT (start=$(cat $ed/start 2>/dev/null) size=$(cat $ed/size 2>/dev/null)); log dumps disabled"
    EXPNOTE=1
    return 1
  fi
  sysnode "$ed" /dev/part_expdb b 600 && log "expdb node ok (${ed##*/}); log dumps enabled"
}
savelog() {   # savelog light|full : raw text dump into expdb (v2 mechanism)
  expdb_node || return 0
  [ -b /dev/part_expdb ] || return 0
  {
    echo "=== z380m init v3 log ($1) ==="; cat $LOG
    echo "=== z380term log ==="; cat /tmp/z380term.log 2>&1
    if [ "$1" = full ]; then echo "=== probe ==="; /bin/z380m-probe 2>&1; else echo "=== dmesg tail ==="; dmesg | tail -n 40; fi
    echo "=== END ==="
  } 2>&1 | head -c 1000000 > /tmp/full.log
  dd if=/tmp/full.log of=/dev/part_expdb bs=4096 2>/dev/null
  sync
}

# ---- USB serial gadget (same sequence as v2) -----------------------------------------------------------------------
gadget_acm() {
  if [ ! -d $G ]; then log "NO android_usb sysfs at $G"; return 1; fi
  echo 0 > $G/enable
  echo 0E8D > $G/idVendor
  echo 2007 > $G/idProduct
  echo MediaTek > $G/iManufacturer
  echo Z380M-Alpine > $G/iProduct
  echo z380m0001 > $G/iSerial
  echo 1 > $G/f_acm/instances
  echo acm > $G/functions
  echo 02 > $G/bDeviceClass
  echo 1 > $G/enable
  log "gadget: functions=$(cat $G/functions 2>&1) enable=$(cat $G/enable 2>&1) state=$(cat $G/state 2>&1)"
}
find_tty() {  # find_tty <max seconds> : sets TTY and creates /dev/<tty>
  ft=0; TTY=
  while [ $ft -lt $1 ] && [ -z "$TTY" ]; do
    for t in $SYS/class/tty/ttyGS*; do
      [ -e "$t/dev" ] && TTY=${t##*/} && break
    done
    if [ -z "$TTY" ]; then sleep 1; ft=$((ft+1)); fi
  done
  [ -n "$TTY" ] || return 1
  sysnode $SYS/class/tty/$TTY /dev/$TTY c
}

# ---- consoles ------------------------------------------------------------------------------------------------------
start_view() {   # live boot log on screen + serial while the ramdisk stage runs
  [ -x /bin/z380term ] || return 0
  if [ -n "$TTY" ]; then
    /bin/z380term -s /dev/$TTY -- /bin/sh -c 'exec tail -n 60 -f /tmp/initlog' 2>>/tmp/z380term.log &
  else
    /bin/z380term -- /bin/sh -c 'exec tail -n 60 -f /tmp/initlog' 2>>/tmp/z380term.log &
  fi
  VIEWPID=$!
}
alive() {   # alive <pid> : true if the process exists and is not a zombie (children of PID 1 are reaped lazily)
  [ -r /proc/$1/stat ] || return 1
  read -r _ _ as _ < /proc/$1/stat 2>/dev/null || return 1
  [ "$as" != Z ]
}
killwait() {   # killwait <pid> : TERM, then KILL if it is still there after ~1 s
  [ -n "$1" ] || return 0
  kill $1 2>/dev/null || return 0
  kw=0
  while alive $1 && [ $kw -lt 30 ]; do kw=$((kw+1)); done
  alive $1 || return 0
  sleep 1
  alive $1 && kill -9 $1 2>/dev/null
  return 0
}
stop_view() { killwait "$VIEWPID"; VIEWPID=; return 0; }

launch() {   # rescue console: z380term (screen + serial) running shell-start, respawned (v2 logic)
  while true; do
    t0=$(cut -d. -f1 /proc/uptime)
    if [ -n "$TTY" ]; then
      /bin/z380term -s /dev/$TTY -- /bin/shell-start 2>>/tmp/z380term.log &
    else
      /bin/z380term -- /bin/shell-start 2>>/tmp/z380term.log &
    fi
    echo $! > /tmp/console.pid
    wait $!
    t1=$(cut -d. -f1 /proc/uptime)
    if [ $((t1-t0)) -lt 5 ] && [ -n "$TTY" ]; then
      log "z380term exited fast, plain shell fallback on $TTY"
      setsid cttyhack sh </dev/$TTY >/dev/$TTY 2>&1
    fi
    sleep 1
  done
}
stop_console() {
  [ -n "$LAUNCHPID" ] && kill $LAUNCHPID 2>/dev/null
  LAUNCHPID=
  if [ -r /tmp/console.pid ]; then killwait "$(cat /tmp/console.pid)"; fi
  rm -f /tmp/console.pid
  return 0
}

# ---- rescue window: a key press (mtk-kpd) or a touch (elan-touchscreen) -----------------------------------------------
evdevs() {
  if [ -n "$EVOVR" ]; then echo "$EVOVR"; return; fi
  for d in $SYS/class/input/event*; do
    [ -d "$d" ] || continue
    n=$(cat "$d/device/name" 2>/dev/null)
    case "$n" in
      *kpd*|*keypad*|*touch*|*Touch*) echo "/dev/input/${d##*/}";;
    esac
  done
}
window() {   # window <seconds> : 0 if a key/touch event arrived within that time
  mk_input_nodes
  list=$(evdevs)
  if [ -z "$list" ]; then log "rescue window: no keypad/touch input device found"; return 1; fi
  rm -f /tmp/ev.*
  pids=; k=0
  for e in $list; do
    [ -r "$e" ] || continue
    dd if="$e" of=/tmp/ev.$k bs=24 count=1 2>/dev/null &
    pids="$pids $!"
    k=$((k+1))
  done
  wt=0; hit=1
  while [ $wt -lt $1 ] && [ $hit -ne 0 ]; do
    sleep 1; wt=$((wt+1))
    for f in /tmp/ev.*; do
      [ -s "$f" ] && hit=0
    done
  done
  kill $pids 2>/dev/null
  return $hit
}

# ---- hand-over to the new root -------------------------------------------------------------------------------------
# Every command after /proc has moved is run as "/bin/busybox <applet>" with an explicit path, because applet links or
# ash's own applet shortcut may rely on /proc/self/exe.  /proc is moved last for the same reason.
pick_move() {   # find the spelling of "move mount" this BusyBox accepts, using throwaway tmpfs mounts
  [ -n "$MOVEOPT" ] && return 0
  mkdir -p /tmp/mv1 /tmp/mv2
  /bin/busybox mount -t tmpfs mvtest /tmp/mv1 2>/dev/null || return 1
  for how in "-o move" "--move" "-M"; do
    if /bin/busybox mount $how /tmp/mv1 /tmp/mv2 2>/dev/null; then
      MOVEOPT=$how
      umount /tmp/mv2 2>/dev/null
      return 0
    fi
  done
  umount /tmp/mv1 2>/dev/null
  return 1
}
move_all() {   # move /sys, /dev, /proc into $NEWROOT; on failure put back what was moved
  MV=; MVFAIL=
  for mn in sys dev proc; do
    mkdir -p $NEWROOT/$mn
    if /bin/busybox mount $MOVEOPT /$mn $NEWROOT/$mn 2>/tmp/mv.err; then
      MV="$MV $mn"
    else
      MVFAIL="$mn: $(cat /tmp/mv.err 2>/dev/null)"
      break
    fi
  done
  [ -z "$MVFAIL" ] && return 0
  for mn in $MV; do /bin/busybox mount $MOVEOPT $NEWROOT/$mn /$mn 2>/dev/null; done
  return 1
}
cons_opt() {   # "switch_root -c /dev/console" only if that node can really be opened (a failed open after the point of no return would kill PID 1)
  CONSOPT=
  if [ -c "$CONSDEV" ] && ( : <> "$CONSDEV" ) 2>/dev/null; then
    CONSOPT="-c $CONSDEV"
  else
    log "WARNING: $CONSDEV cannot be opened; the new init keeps the stdio it has now"
  fi
}

boot_alpine() {   # returns 1 (with BOOTFAIL set) on any problem; on success it never returns
  BOOTFAIL=
  umount $NEWROOT 2>/dev/null
  log "looking for the '$SYSNAME' partition (up to ${BLKWAIT}s)"
  bt=0
  until sys_node; do
    bt=$((bt+1))
    if [ $bt -ge $BLKWAIT ]; then
      log_parts
      BOOTFAIL="no partition named '$SYSNAME' (and none with the GPT geometry) in sysfs"
      return 1
    fi
    sleep 1
  done
  pstart=$(cat $SD/start 2>/dev/null); psize=$(cat $SD/size 2>/dev/null)
  log "system: ${SD##*/} start=$pstart sectors=$psize dev=$(cat $SD/dev 2>/dev/null)"
  if [ "$pstart" != "$SYS_START" ] || [ "$psize" != "$SYS_SECT" ]; then
    log "WARNING: geometry differs from the GPT numbers ($SYS_START/$SYS_SECT); the marker file decides"
  fi
  mkdir -p $NEWROOT
  if ! mount -t ext4 -o rw,noatime /dev/part_system $NEWROOT 2>/tmp/mount.err; then
    log "mount ext4 failed: $(cat /tmp/mount.err)"
    dmesg | tail -n 6 >> $LOG
    log_parts
    BOOTFAIL="cannot mount ext4 from the system partition (expected until the Alpine image is written there)"
    return 1
  fi
  log "mounted ext4 on $NEWROOT"
  l1=; l2=; l3=
  if [ -f $NEWROOT/etc/z380m-release ]; then { read l1; read l2; read l3; } < $NEWROOT/etc/z380m-release; fi
  if [ "$l1" != "z380m-alpine" ]; then
    umount $NEWROOT 2>/dev/null
    BOOTFAIL="marker /etc/z380m-release missing or wrong (not an image made by build_alpine_rootfs.py)"
    return 1
  fi
  log "marker ok: $l2 $l3"
  sm=$(chroot $NEWROOT /bin/busybox sh -c 'test -x /sbin/init && echo smoke-ok' 2>&1)
  log "userland smoke test (runs the Alpine busybox): $sm"
  if [ "$sm" != "smoke-ok" ]; then
    umount $NEWROOT 2>/dev/null
    BOOTFAIL="Alpine userland smoke test failed: $sm"
    return 1
  fi
  if touch $NEWROOT/.z380m-rw 2>/dev/null; then rm -f $NEWROOT/.z380m-rw; log "root is writable"; else log "WARNING: root is NOT writable"; fi
  if ! /bin/busybox switch_root --help 2>&1 | grep -qi usage; then
    umount $NEWROOT 2>/dev/null
    BOOTFAIL="this BusyBox has no usable switch_root applet"
    return 1
  fi
  if ! pick_move; then
    umount $NEWROOT 2>/dev/null
    BOOTFAIL="this BusyBox cannot 'mount --move' (tried -o move, --move, -M); see z380m-probe"
    return 1
  fi
  log "mount --move spelling: $MOVEOPT"
  cons_opt
  log "handing over: switch_root $CONSOPT $NEWROOT /sbin/init"
  mkdir -p $NEWROOT/var/log
  savelog light
  cp $LOG $NEWROOT/var/log/z380m-ramdisk.log 2>/dev/null
  stop_view; stop_console
  if ! move_all; then
    BOOTFAIL="could not move $MVFAIL (mounts put back)"
    log "$BOOTFAIL"
    umount $NEWROOT 2>/dev/null
    return 1
  fi
  # /proc has moved: from here only shell builtins and the explicit /bin/busybox are used
  echo "moved:$MV" >> $NEWROOT/var/log/z380m-ramdisk.log
  exec /bin/busybox switch_root $CONSOPT $NEWROOT /sbin/init
}

switch_test() {   # same hand-over, but into a throwaway tmpfs root (proves mount --move + switch_root; mounts nothing)
  if ! pick_move; then log "switch-test: this BusyBox cannot mount --move"; return 1; fi
  stop_view; stop_console
  umount $NEWROOT 2>/dev/null
  mkdir -p $NEWROOT
  if ! mount -t tmpfs tmpfs $NEWROOT; then log "switch-test: cannot mount a tmpfs on $NEWROOT"; return 1; fi
  mkdir -p $NEWROOT/bin $NEWROOT/sbin $NEWROOT/dev $NEWROOT/proc $NEWROOT/sys $NEWROOT/tmp $NEWROOT/root $NEWROOT/etc
  cp /bin/busybox /bin/z380term $NEWROOT/bin/
  cp /etc/switchtest-init $NEWROOT/sbin/init
  cp /etc/switchtest-shell $NEWROOT/bin/st-shell
  chmod 755 $NEWROOT/sbin/init $NEWROOT/bin/st-shell
  ln -s busybox $NEWROOT/bin/sh
  cons_opt
  log "switch-test: moving /sys /dev /proc and switching into a tmpfs root (mount --move spelling: $MOVEOPT)"
  if ! move_all; then
    log "switch-test: could not move $MVFAIL (mounts put back)"
    umount $NEWROOT 2>/dev/null
    return 1
  fi
  exec /bin/busybox switch_root $CONSOPT $NEWROOT /sbin/init
}

rescue() {   # never returns: serves the rescue console and watches for retry-boot / switch-test requests
  log "RESCUE: $*"
  echo "$*" > /tmp/rescue_reason
  stop_view; stop_console
  bl 255
  sys_node
  savelog full
  launch &
  LAUNCHPID=$!
  rn=0
  while true; do
    if [ -f /tmp/retry-boot ]; then
      rm -f /tmp/retry-boot /tmp/retry-result
      log "retry-boot requested"
      if ! boot_alpine; then
        log "retry failed: ${BOOTFAIL:-no reason given}"
        echo "${BOOTFAIL:-no reason given}" > /tmp/rescue_reason
        echo "${BOOTFAIL:-no reason given}" > /tmp/retry-result
        savelog full
      fi
      if [ -z "$LAUNCHPID" ]; then launch & LAUNCHPID=$!; fi
    fi
    if [ -f /tmp/switch-test ]; then
      rm -f /tmp/switch-test /tmp/switch-result
      log "switch-test requested"
      switch_test
      echo "switch-test could not start, see the init log" > /tmp/switch-result
      echo "switch-test could not start, see the init log" > /tmp/rescue_reason
      if [ -z "$LAUNCHPID" ]; then launch & LAUNCHPID=$!; fi
    fi
    rn=$((rn+1))
    if [ $((rn % 30)) -eq 0 ] && [ $rn -le 90 ]; then savelog full; fi
    sleep 2
  done
}

# ---- main ----------------------------------------------------------------------------------------------------------
bl 24
gadget_acm
if find_tty $TTYWAIT; then log "serial console: /dev/$TTY"; else log "no ttyGS device after ${TTYWAIT}s (screen-only)"; fi
start_view
if [ "$WIN" -gt 0 ] 2>/dev/null; then
  log "== tap VOL+/VOL- or touch the screen within ${WIN}s for RESCUE =="
  if window "$WIN"; then rescue "requested with a key press or touch"; fi
fi
bl 255
boot_alpine
rescue "${BOOTFAIL:-boot sequence ended without a reason}"
while true; do sleep 60; done
'''

# ------------------------------------------------------------------------------------------------------------------
# helpers that live in the ramdisk
# ------------------------------------------------------------------------------------------------------------------
SHELL_START = r'''#!/bin/sh
# first thing the rescue console runs (z380term -> this -> sh)
echo "== Z380M RESCUE console (init v3) =="
echo "z380m-alpine by kaantcp - https://github.com/kaantcp"
[ -f /tmp/rescue_reason ] && echo "reason: $(cat /tmp/rescue_reason)"
uname -a
echo
echo "-- init log --"
cat /tmp/initlog
echo
echo "-- last kernel messages --"
dmesg | tail -n 12
echo
echo "commands:  z380m-probe        facts about this kernel/tablet/BusyBox (read-only)"
echo "           z380m-switch-test  try mount --move + switch_root into a throwaway tmpfs root"
echo "           retry-boot         try the Alpine boot again (after the system image was written)"
echo "           sync; reboot -f    reboot"
[ -b /dev/part_system ] && echo "system partition node: /dev/part_system   (look inside: mount -t ext4 -o ro /dev/part_system /mnt)"
echo
exec /bin/sh
'''

RETRY_BOOT = r'''#!/bin/sh
# ask PID 1 to run the Alpine boot sequence again; if it fails, PID 1 leaves the reason in /tmp/retry-result
rm -f /tmp/retry-result
touch /tmp/retry-boot
echo "retry requested; PID 1 checks every 2 seconds (the system partition is searched for up to 30 s)..."
i=0
while [ $i -lt 90 ]; do
  if [ -f /tmp/retry-result ]; then
    echo "RETRY FAILED: $(cat /tmp/retry-result)"
    echo "-- last log lines --"; tail -n 8 /tmp/initlog
    exit 1
  fi
  sleep 1; i=$((i+1))
done
echo "no result after 90 s; PID 1 is probably still working, check the screen and /tmp/initlog"
'''

SWITCH_TEST = r'''#!/bin/sh
# ask PID 1 to switch_root into a throwaway tmpfs root (nothing is mounted from storage)
rm -f /tmp/switch-result
touch /tmp/switch-test
echo "switch-test requested. On success this console disappears and a new one ('switchtest#') appears within ~10 seconds."
echo "If it cannot start, the reason is printed here. If nothing appears after 30 seconds the switch itself failed:"
echo "power-cycle the tablet (hold power) and read the expdb log from the PC."
i=0
while [ $i -lt 60 ]; do
  if [ -f /tmp/switch-result ]; then
    echo "SWITCH-TEST FAILED TO START: $(cat /tmp/switch-result)"
    echo "-- last log lines --"; tail -n 8 /tmp/initlog
    exit 1
  fi
  sleep 1; i=$((i+1))
done
'''

PROBE = r'''#!/bin/sh
# z380m-probe: read-only facts about this kernel, tablet and BusyBox.  Writes only to stdout (plus two throwaway tmpfs mounts).
SYS=${Z380_SYSFS:-/sys}
FSLIST=${Z380_FSLIST:-/proc/filesystems}
echo "== z380m-probe =="
echo "-- kernel"
uname -a
echo "cmdline: $(cat /proc/cmdline 2>&1)"
echo "-- filesystems known to the kernel"
cat "$FSLIST" 2>&1 | tr '\n' ' '; echo
echo "-- selected kernel config (/proc/config.gz)"
if [ -r /proc/config.gz ]; then
  zcat /proc/config.gz 2>/dev/null | grep -E '^(# )?CONFIG_(EXT4_FS|DEVTMPFS|DEVTMPFS_MOUNT|TMPFS|MODULES|UEVENT_HELPER|UEVENT_HELPER_PATH|ANDROID|ANDROID_PARANOID_NETWORK|ANDROID_LOW_MEMORY_KILLER|ANDROID_BINDER_IPC|ASHMEM|USB_ANDROID|USB_G_ANDROID|USB_F_RNDIS|USB_.*RNDIS.*|INOTIFY_USER|SIGNALFD|TIMERFD|EVENTFD|EPOLL|MEMFD_CREATE|CGROUPS|NAMESPACES|SYSVIPC|IPV6|ARM64_4K_PAGES|ARM64_64K_PAGES|COMPAT|CFG80211|MAC80211|MTK_COMBO.*|MTK_WLAN.*|MTK_BT.*|HW_RANDOM.*|IKCONFIG.*|RTC_DRV_MT.*|FRAMEBUFFER_CONSOLE|VT|SECCOMP|AUDIT|SECURITY_SELINUX|DEFAULT_SECURITY.*)[= ]' | head -80
else
  echo "(no /proc/config.gz)"
fi
echo "-- GPT partitions seen by the kernel: sysfs-name PARTNAME start size (512-byte sectors)"
for u in $SYS/class/block/*/uevent; do
  [ -r "$u" ] || continue
  d=${u%/uevent}
  [ -r "$d/start" ] || continue
  pn=-
  while IFS== read k v; do
    [ "$k" = PARTNAME ] && pn=$v
  done < "$u"
  echo "${d##*/} $pn $(cat $d/start 2>/dev/null) $(cat $d/size 2>/dev/null)"
done
echo "-- input devices (event node: device name, major:minor)"
for d in $SYS/class/input/event*; do
  [ -d "$d" ] && echo "${d##*/}: $(cat $d/device/name 2>/dev/null) $(cat $d/dev 2>/dev/null)"
done
echo "-- framebuffer fb0"
for f in name bits_per_pixel virtual_size stride; do echo "$f: $(cat $SYS/class/graphics/fb0/$f 2>&1)"; done
echo "-- backlight: $(cat $SYS/class/leds/lcd-backlight/brightness 2>&1) (max $(cat $SYS/class/leds/lcd-backlight/max_brightness 2>&1))"
echo "-- usb gadget (android_usb)"
G=$SYS/class/android_usb/android0
if [ -d $G ]; then
  for f in enable state functions idVendor idProduct bDeviceClass iProduct; do echo "$f=$(cat $G/$f 2>&1)"; done
  echo "function dirs: $(ls $G | grep '^f_' | tr '\n' ' ')"
  if [ -d $G/f_rndis ]; then
    for f in $(ls $G/f_rndis); do echo "f_rndis/$f=$(cat $G/f_rndis/$f 2>&1 | head -n 1)"; done
  fi
else
  echo "no $G"
fi
echo "net devices: $(ls $SYS/class/net 2>&1 | tr '\n' ' ')   gadget ttys: $(ls $SYS/class/tty 2>&1 | grep -i gs | tr '\n' ' ')"
echo "-- rtc / rng / entropy / hotplug helper / low-memory killer"
echo "rtc: $(ls $SYS/class/rtc 2>&1 | tr '\n' ' ')  hw rng: $(ls /dev/hwrng /dev/hw_random 2>&1 | tr '\n' ' ')"
echo "entropy_avail=$(cat /proc/sys/kernel/random/entropy_avail 2>&1)  hotplug helper='$(cat /proc/sys/kernel/hotplug 2>&1)'"
for f in minfree adj; do echo "lowmemorykiller/$f=$(cat /sys/module/lowmemorykiller/parameters/$f 2>&1)"; done
echo "-- memory / cpus"
grep -E 'MemTotal|MemFree' /proc/meminfo 2>&1
echo "cpus: $(grep -c '^processor' /proc/cpuinfo 2>&1)"
echo "-- BusyBox"
busybox 2>&1 | head -n 1
echo "applets: $(busybox --list 2>&1 | tr '\n' ' ')"
echo "-- mount --move capability (throwaway tmpfs mounts under /tmp)"
mkdir -p /tmp/pm1 /tmp/pm2
if /bin/busybox mount -t tmpfs t /tmp/pm1 2>/dev/null; then
  for how in "-o move" "--move" "-M"; do
    if /bin/busybox mount $how /tmp/pm1 /tmp/pm2 2>/dev/null; then echo "mount $how: OK"; umount /tmp/pm2 2>/dev/null; break; else echo "mount $how: failed"; fi
  done
  umount /tmp/pm1 2>/dev/null
else
  echo "tmpfs mount failed"
fi
echo "-- dmesg (last 60 lines)"
dmesg | tail -n 60
echo "== end of z380m-probe =="
'''

# the throwaway root used by z380m-switch-test (NOT Alpine)
SWITCHTEST_INIT = r'''#!/bin/busybox sh
# z380m switch-test root: proof that mount --move + switch_root work on this kernel. Not Alpine, nothing mounted.
export PATH=/bin:/sbin HOME=/root TERM=linux PS1='switchtest# '
/bin/busybox --install -s /bin
echo "SWITCH-ROOT TEST: new init is PID $$"
mount -t tmpfs tmpfs /tmp 2>/dev/null
T=
for t in /sys/class/tty/ttyGS*; do
  [ -e "$t/dev" ] && T=${t##*/} && break
done
while true; do
  if [ -n "$T" ]; then /bin/z380term -s /dev/$T -- /bin/st-shell; else /bin/z380term -- /bin/st-shell; fi
  sleep 1
done
'''

SWITCHTEST_SHELL = r'''#!/bin/sh
echo "== SWITCH-ROOT TEST OK =="
echo "You are in a throwaway tmpfs root, reached with mount --move + switch_root. Nothing was mounted from storage."
echo "PID 1 here: $(tr '\0' ' ' < /proc/1/cmdline)"
echo "mounts:"; head -n 8 /proc/mounts
echo
echo "Leave with: sync; reboot -f"
exec /bin/sh
'''


def fill_init(text, window):
    for k, v in (("@SYS_START@", SYS_START), ("@SYS_SECT@", SYS_SECT), ("@EXP_START@", EXP_START), ("@EXP_SECT@", EXP_SECT)):
        assert k in text
        text = text.replace(k, str(v))
    assert not re.search(r"@[A-Z_]+@", text), "unfilled placeholder in init"
    old = "WIN=${Z380_WINDOW:-5}"
    assert old in text
    return text.replace(old, "WIN=${Z380_WINDOW:-%d}" % window)


def scripts(window):
    return {
        "init": fill_init(INIT, window),
        "shell-start": SHELL_START,
        "retry-boot": RETRY_BOOT,
        "z380m-switch-test": SWITCH_TEST,
        "z380m-probe": PROBE,
        "switchtest-init": SWITCHTEST_INIT,
        "switchtest-shell": SWITCHTEST_SHELL,
    }


# applets the init relies on; the build stops if one of the REQUIRED ones is missing from the BusyBox binary
REQUIRED_APPLETS = ["sh", "mount", "umount", "mknod", "mkdir", "cat", "cut", "grep", "sleep", "dd", "kill", "tail", "head",
                    "dmesg", "uname", "hostname", "mdev", "chroot", "switch_root", "ls", "tr", "rm", "cp", "ln", "chmod",
                    "touch", "sync", "reboot"]
OPTIONAL_APPLETS = ["setsid", "cttyhack", "zcat", "gunzip", "ps", "df", "free", "vi", "less", "find", "date", "insmod", "lsmod",
                    "ifconfig", "ip", "udhcpc", "ping", "fdisk", "blkid"]
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


def bb_has_applet(data, name):
    """BusyBox keeps its applet names as NUL-separated strings in one table; look the name up there."""
    return (b"\0" + name.encode() + b"\0") in data


def main():
    ap = argparse.ArgumentParser(description="Build the Z380M Alpine boot image (v3).")
    ap.add_argument("term_src", nargs="?", default=os.path.join(HERE, "z380term.c"), help="z380term.c (default: next to this script)")
    ap.add_argument("out_dir", nargs="?", default=HOME + "/linux_alpine_v3", help="output directory (default ~/linux_alpine_v3)")
    ap.add_argument("--window", type=int, default=5, metavar="N", help="seconds of the key/touch rescue window at boot (default 5, 0 = off)")
    ap.add_argument("--dump-scripts", metavar="DIR", help="write the ramdisk scripts to DIR and exit (nothing else is read or built)")
    a = ap.parse_args()
    print(CREDIT)
    if not 0 <= a.window <= 60:
        sys.exit("--window must be between 0 and 60")
    SC = scripts(a.window)

    if a.dump_scripts:
        os.makedirs(a.dump_scripts, exist_ok=True)
        for name, text in SC.items():
            p = os.path.join(a.dump_scripts, name)
            with open(p, "w") as f:
                f.write(text)
            os.chmod(p, 0o755)
        print("wrote %d scripts to %s" % (len(SC), a.dump_scripts))
        return

    CSRC, OUT = a.term_src, a.out_dir
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
    if r.stderr.strip():
        print("compiler warnings:\n" + r.stderr)
    check_elf(TERMBIN, MACHINE, "z380term")
    print("compiled z380term: %d bytes, static, correct CPU type, sha256 %s" % (
        os.path.getsize(TERMBIN), hashlib.sha256(open(TERMBIN, "rb").read()).hexdigest()))

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

    # ---- BusyBox: right CPU, static, and the applets the init needs ----
    check_elf(BB, MACHINE, "busybox")
    bb = open(BB, "rb").read()
    missing = [x for x in REQUIRED_APPLETS if not bb_has_applet(bb, x)]
    if missing:
        sys.exit("this BusyBox (%s) lacks required applets: %s\nUse a fuller static aarch64 BusyBox (e.g. the Debian busybox-static binary)." % (BB, " ".join(missing)))
    opt_missing = [x for x in OPTIONAL_APPLETS if not bb_has_applet(bb, x)]
    print("busybox: %d bytes, all %d required applets present%s" % (len(bb), len(REQUIRED_APPLETS),
          ("; optional ones missing: " + " ".join(opt_missing)) if opt_missing else ""))
    print("  (this reads BusyBox's applet name table; the real answer is 'busybox --list' in the rescue shell, z380m-probe prints it)")
    term = open(TERMBIN, "rb").read()

    dirs = ["bin", "sbin", "dev", "proc", "sys", "tmp", "etc", "root", "usr", "usr/bin", "mnt", "newroot"]
    ents = [(d, S_IFDIR | 0o755, b"", 0, 0, 2) for d in dirs]
    ents += [
        ("bin/busybox", S_IFREG | 0o755, bb, 0, 0, 1),
        ("bin/sh", S_IFLNK | 0o777, b"busybox", 0, 0, 1),
        ("bin/z380term", S_IFREG | 0o755, term, 0, 0, 1),
        ("bin/shell-start", S_IFREG | 0o755, SC["shell-start"].encode(), 0, 0, 1),
        ("bin/z380m-probe", S_IFREG | 0o755, SC["z380m-probe"].encode(), 0, 0, 1),
        ("bin/z380m-switch-test", S_IFREG | 0o755, SC["z380m-switch-test"].encode(), 0, 0, 1),
        ("bin/retry-boot", S_IFREG | 0o755, SC["retry-boot"].encode(), 0, 0, 1),
        ("etc/switchtest-init", S_IFREG | 0o755, SC["switchtest-init"].encode(), 0, 0, 1),
        ("etc/switchtest-shell", S_IFREG | 0o755, SC["switchtest-shell"].encode(), 0, 0, 1),
        ("init", S_IFREG | 0o755, SC["init"].encode(), 0, 0, 1),
        ("etc/passwd", S_IFREG | 0o644, b"root:x:0:0:root:/root:/bin/sh\n", 0, 0, 1),
        ("etc/group", S_IFREG | 0o644, b"root:x:0:\n", 0, 0, 1),
        ("dev/console", S_IFCHR | 0o600, b"", 5, 1, 1),
        ("dev/null", S_IFCHR | 0o666, b"", 1, 3, 1),
        ("dev/zero", S_IFCHR | 0o666, b"", 1, 5, 1),
        ("dev/tty", S_IFCHR | 0o666, b"", 5, 0, 1),
        ("dev/urandom", S_IFCHR | 0o666, b"", 1, 9, 1),
        ("dev/random", S_IFCHR | 0o666, b"", 1, 8, 1),
        ("dev/kmsg", S_IFCHR | 0o600, b"", 1, 11, 1),
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
    assert h[2] == rsz2 and rd[:4] == MAGIC and struct.unpack_from("<I", rd, 4)[0] == len(rd) - 512
    assert rd[8:14] == b"ROOTFS" and set(rd[40:512]) == {0xFF}
    raw = gzip.decompress(rd[512:])
    files = ls_newc(raw)
    names = {f[0] for f in files}
    for need in ("init", "bin/busybox", "bin/z380term", "bin/shell-start", "bin/z380m-probe", "bin/z380m-switch-test",
                 "bin/retry-boot", "etc/switchtest-init", "etc/switchtest-shell", "newroot", "dev/console"):
        assert need in names, "ramdisk is missing " + need
    assert img[0x40:0x40 + 512] == b[0x40:0x40 + 512], "cmdline changed"
    sha2 = hashlib.sha1()
    for part in (img[page:page + ksz], struct.pack("<I", ksz), rd, struct.pack("<I", rsz2), b"", struct.pack("<I", 0)):
        sha2.update(part)
    assert img[0x240:0x254] == sha2.digest(), "header SHA1 does not match"
    # only the ramdisk size and the SHA1 may differ from the official header
    diff = [i for i in range(page) if img[i] != b[i]]
    assert all(16 <= i < 20 or 0x240 <= i < 0x260 for i in diff), "unexpected header bytes changed: %s" % diff[:10]

    open(OUT + "/init.sh", "w").write(SC["init"])
    open(OUT + "/boot_alpine.img", "wb").write(img)
    full = img + b"\0" * (PART - len(img))
    open(OUT + "/boot_alpine_full.bin", "wb").write(full)
    sums = hashlib.sha256(full).hexdigest()
    open(OUT + "/boot_alpine_full.bin.sha256", "w").write("%s  boot_alpine_full.bin\n" % sums)
    print("kernel: %d bytes, byte-identical to source" % ksz)
    print("cmdline: %s" % b[0x40:0x240].split(b"\0")[0].decode())
    print("header: only the ramdisk size (offset 16) and the SHA1 (0x240) differ from the official boot image")
    print("rescue window: %d s" % a.window)
    print("old ramdisk: %d bytes -> new ramdisk: %d bytes (gz payload %d)" % (rsz, rsz2, len(gz)))
    print("image: %d bytes, padded file: %d bytes (partition %d)" % (len(img), len(full), PART))
    for f in files:
        print("  %-24s %-8s %d" % f)
    if os.path.exists(V2_IMAGE):
        v2 = open(V2_IMAGE, "rb").read()
        same_k = v2[page:page + ksz] == kernel
        same_h = all(v2[i] == b[i] for i in range(page) if not (16 <= i < 20 or 0x240 <= i < 0x260))
        print("vs your v2 console image: kernel %s, header fields %s" % ("identical" if same_k else "DIFFERENT", "identical" if same_h else "DIFFERENT"))
    print("sha256 full: " + sums)
    print("BUILD OK")


if __name__ == "__main__":
    main()
