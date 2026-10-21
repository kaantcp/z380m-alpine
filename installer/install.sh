#!/bin/sh
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

Z380M_CREDIT="z380m-alpine by kaantcp - https://github.com/kaantcp"

# z380m GUI installer v1. Survey, safety gates, then installs Xorg + JWM + an on-screen keyboard INTO Alpine's own ext4.
# It flashes nothing and writes nothing outside the root filesystem. Undo everything with:  sh /root/gui-uninstall.sh
# usage: sh install.sh          install (stops by itself, before changing anything, if a gate fails)
#        sh install.sh check    survey and gates only, installs nothing
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
[ "$(hostname)" = z380m ] || { echo "This is not the tablet (hostname: $(hostname)). Stopping."; exit 1; }
[ "$(id -u)" = 0 ] || { echo "Run this as root. Stopping."; exit 1; }
HERE=$(cd "$(dirname "$0")" && pwd)
MODE=${1:-install}
LOGF=/root/gui-install.txt
RCF=/tmp/z380m-install.rc
rm -f $RCF

main() {
  hdr() { echo; echo "=== $* ==="; }
  # leave with a status; nothing has been changed yet unless stated
  finish() { echo "$1" > $RCF; exit "$1"; }
  stop() { echo; echo "STOPPED: $*"; echo "(nothing was installed or changed)"; finish 1; }
  mibof() { echo "$1" | awk '{v=$2; u=$3; if (u=="KiB") v/=1024; else if (u=="GiB") v*=1024; else if (u=="B") v/=1048576; printf "%.1f", v}'; }
  have() { for q in $*; do case " $FOUND " in *" $q "*) printf '%s ' "$q" ;; esac; done; }

  echo "$Z380M_CREDIT"
  echo "z380m GUI installer v1  $(date '+%F %T') (the tablet clock may be wrong)  mode: $MODE"

  hdr "1 tablet"
  uname -srm
  free -m | sed -n 2p
  FREE=$(df -k / | awk 'NR==2{printf "%.0f", $4/1024}')
  echo "free on /: ${FREE:-?} MiB"
  [ -n "$FREE" ] || stop "cannot read the free space of /"

  hdr "2 screen, virtual terminals, touch"
  [ -c /dev/fb0 ] || stop "/dev/fb0 is missing: there is no framebuffer"
  fbset -fb /dev/fb0 2>&1 | sed -n 2,4p
  VT=0
  [ -c /dev/tty0 ] && VT=1
  grep -q vtmaster "${Z380M_TTY_DRIVERS:-/proc/tty/drivers}" 2>/dev/null && VT=1
  echo "virtual terminals in the kernel: $VT (1 = yes);  device files now: $(ls /dev/tty0 /dev/tty1 2>/dev/null | tr '\n' ' ')('z380m-gui start' creates missing ones)"
  echo "vtconsole: $(for f in /sys/class/vtconsole/vtcon*; do [ -e "$f/name" ] && printf '%s bind=%s; ' "$(cat $f/name)" "$(cat $f/bind)"; done)"
  if [ "$VT" != 1 ]; then
    echo "tty drivers: $(cut -c1-60 "${Z380M_TTY_DRIVERS:-/proc/tty/drivers}" 2>&1 | tr '\n' '|')"
    stop "the kernel shows no virtual terminals (no vtmaster in /proc/tty/drivers, no /dev/tty0). Standard Xorg needs one. Report this whole output (https://github.com/kaantcp)."
  fi
  TEV=$(awk '/^N: Name=/{n=$0} /^H: Handlers=/{ if (n ~ /[Tt]ouch/) { for(i=1;i<=NF;i++) if (match($i, /event[0-9]+$/)) { print substr($i, RSTART, RLENGTH); exit } } }' "${Z380M_INPUT_DEVICES:-/proc/bus/input/devices}" 2>/dev/null)
  [ -n "$TEV" ] || stop "no touch screen found in /proc/bus/input/devices"
  echo "touch screen: /dev/input/$TEV ($(cat /sys/class/input/$TEV/device/name 2>/dev/null))"
  EV=$(timeout 5 evtest --info /dev/input/$TEV 2>&1)
  case "$EV" in *ABS_MT_POSITION*) ;; *) EV=$(timeout -s INT 3 evtest /dev/input/$TEV 2>&1 < /dev/null) ;; esac
  echo "$EV" | grep -E -A3 'ABS_MT_POSITION_[XY]' | grep -E 'ABS_MT|Min|Max' | head -n 8 | cut -c1-90
  echo "uinput: node $(ls /dev/uinput 2>/dev/null | head -n 1), in /proc/misc: $(grep -c uinput /proc/misc 2>/dev/null);  drm: $(ls /sys/class/drm 2>/dev/null | tr '\n' ' ')"
  echo "sysvipc: $(ls /proc/sysvipc 2>/dev/null | tr '\n' ' ')"
  echo "wifi hints: $(ls /sys/class/net 2>/dev/null | tr '\n' ' ')| $(dmesg 2>/dev/null | grep -iE 'wmt|mt66|mt76|mt79|consys|combo' | head -n 4 | cut -c1-100 | tr '\n' '|')"

  hdr "3 network and package list"
  ping -c 1 -W 3 1.1.1.1 > /dev/null 2>&1 || stop "no internet through the USB link. Bring it up first: on the PC (P window) 'sudo bash ~/linux_alpine_v3/pc_usbnet.sh up', then in T 'ip route add default via 192.168.7.1' (after 'z380m-usb rndis-acm' if the tablet was rebooted), then run this again."
  timeout 180 apk update > /tmp/z380m-upd.txt 2>&1; rc=$?
  tail -n 3 /tmp/z380m-upd.txt | cut -c1-120
  [ $rc -eq 0 ] || stop "apk update failed (exit $rc)"

  REQ="xorg-server xf86-video-fbdev xf86-input-evdev xkbcomp xkeyboard-config xsetroot xset xrdb setxkbmap font-dejavu font-misc-misc font-cursor-misc xterm jwm"
  OPT="svkbd matchbox-keyboard xinput tcc"
  FOUND=; MISS=
  for p in $REQ $OPT; do
    if [ -n "$(apk search -e "$p" 2> /dev/null | head -n 1)" ]; then FOUND="$FOUND $p"; else MISS="$MISS $p"; fi
  done
  echo "not in the package index:${MISS:- none}"
  for p in $REQ; do case " $FOUND " in *" $p "*) ;; *) stop "required package '$p' is not in the package index. Report this output (https://github.com/kaantcp)." ;; esac; done
  KBD=; for p in svkbd matchbox-keyboard; do case " $FOUND " in *" $p "*) KBD=$p; break ;; esac; done
  [ -n "$KBD" ] || echo "WARNING: no on-screen keyboard package exists in the index; the desktop will have no keyboard yet"
  LIST="$(have $REQ) $KBD $(have xinput tcc)"
  echo "to install: $LIST"

  hdr "4 does it fit"
  BASEL=$(apk add --simulate busybox 2>&1 | grep '^OK:' | tail -n 1)
  BASE=$(mibof "$BASEL")
  out=$(apk add --simulate $LIST 2>&1); rc=$?
  [ $rc -eq 0 ] || { echo "$out" | head -n 8 | cut -c1-150; stop "the dry run failed (exit $rc)"; }
  N=$(echo "$out" | grep -c 'Installing')
  AFTER=$(mibof "$(echo "$out" | grep '^OK:' | tail -n 1)")
  ADD=$(awk -v a="$AFTER" -v b="$BASE" 'BEGIN{printf "%.1f", a-b}')
  NEED=$(awk -v d="$ADD" 'BEGIN{printf "%.0f", d*1.3+25}')
  echo "installed now: ${BASEL:-unknown}"
  echo "$N new packages, +$ADD MiB installed size; free $FREE MiB; need about $NEED MiB (size x 1.3 + 25)"
  echo "largest new packages (MiB):"
  apk query --recursive --fields name,installed-size $LIST 2> /dev/null | awk '/^Name:/{n=$2} /^Installed-Size:/{printf "%d %s\n", $2/104857.6, n}' | sort -rn | head -n 6 | awk '{printf "  %.1f %s\n", $1/10, $2}'
  awk -v n="$NEED" -v f="$FREE" 'BEGIN{if (f+0 >= n+0) exit 0; else exit 1}' || stop "it does not fit: need about $NEED MiB, free $FREE MiB. Report this output (https://github.com/kaantcp); nothing was changed."
  echo "-> it fits"
  if [ "$MODE" = check ]; then
    echo; echo "CHECK DONE: all gates passed. To install: sh $HERE/install.sh"
    finish 0
  fi

  hdr "5 uninstall script"
  cat > /root/gui-uninstall.sh <<'UNEOF'
#!/bin/sh
# undo of the z380m GUI installer: the desktop, its packages, its files and the console.sh hook
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
z380m-gui boot-disable 2> /dev/null
z380m-gui stop 2> /dev/null
apk del .z380m-gui
if [ -f /etc/z380m/console.sh.orig ]; then cp /etc/z380m/console.sh.orig /etc/z380m/console.sh.back && mv /etc/z380m/console.sh.back /etc/z380m/console.sh; fi
rm -rf /etc/z380m/gui /usr/local/sbin/z380m-gui /usr/local/bin/z380m-kbd /usr/local/bin/z380m-bright /usr/local/bin/z380m-colortest
rm -f /etc/init.d/z380m-gui /usr/local/lib/z380m-fbfix.so
rm -rf /usr/local/src/z380m
echo "z380m GUI removed. (console.sh restored from console.sh.orig)"
UNEOF
  chmod 755 /root/gui-uninstall.sh
  echo "written: /root/gui-uninstall.sh"

  hdr "6 installing packages (a few minutes; apk prints one line per package)"
  rm -f /tmp/z380m-add.rc
  ( timeout 2400 apk add --virtual .z380m-gui $LIST 2>&1; echo $? > /tmp/z380m-add.rc ) | tee /tmp/z380m-add.txt | cut -c1-110
  rc=$(cat /tmp/z380m-add.rc 2> /dev/null || echo 99)
  if [ "$rc" != 0 ]; then
    echo; echo "STOPPED: apk add failed (exit $rc). Last lines:"; tail -n 15 /tmp/z380m-add.txt | cut -c1-150
    echo "Packages may be partly installed. Run this installer again (it continues), or: sh /root/gui-uninstall.sh"
    finish 2
  fi
  echo "free on / now: $(df -k / | awk 'NR==2{printf "%.0f", $4/1024}') MiB"

  hdr "7 check what was installed"
  MISSING=
  for b in Xorg jwm xterm xsetroot xset setxkbmap xrdb xkbcomp; do command -v $b > /dev/null 2>&1 || MISSING="$MISSING $b"; done
  FBD=$(find /usr/lib/xorg/modules -name fbdev_drv.so 2> /dev/null | head -n 1)
  EVD=$(find /usr/lib/xorg/modules -name evdev_drv.so 2> /dev/null | head -n 1)
  echo "programs missing:${MISSING:- none}"
  echo "fbdev driver: ${FBD:-MISSING}"
  echo "evdev driver: ${EVD:-MISSING}"
  XV=$(Xorg -version 2>&1 | grep -i 'X.Org X Server' | head -n 1)
  echo "Xorg runs: ${XV:-NO (Xorg -version printed nothing useful)}"
  if [ -n "$MISSING" ] || [ -z "$FBD" ] || [ -z "$EVD" ] || [ -z "$XV" ]; then
    echo; echo "STOPPED: something that should have been installed is not usable (see above)."
    echo "The packages stay installed. Report this output (https://github.com/kaantcp). Undo: sh /root/gui-uninstall.sh"
    finish 3
  fi

  hdr "8 files"
  FAIL=0
  inst() { # inst <mode> <source in the package> <destination>
    mkdir -p "$(dirname "$3")"
    if cp "$HERE/$2" "$3.new" && chmod "$1" "$3.new" && mv "$3.new" "$3"; then echo "  $3"; else echo "  FAILED: $3"; FAIL=1; fi
  }
  inst 755 z380m-gui /usr/local/sbin/z380m-gui
  inst 755 z380m-kbd /usr/local/bin/z380m-kbd
  inst 755 z380m-bright /usr/local/bin/z380m-bright
  inst 755 z380m-colortest /usr/local/bin/z380m-colortest
  inst 644 xorg.conf /etc/z380m/gui/xorg.conf
  inst 755 session.sh /etc/z380m/gui/session.sh
  inst 644 jwmrc /etc/z380m/gui/jwmrc
  inst 644 Xresources /etc/z380m/gui/Xresources
  inst 644 fbfix.c /usr/local/src/z380m/fbfix.c
  touch /etc/z380m/gui/first-run
  [ $FAIL = 0 ] || { echo "STOPPED: could not write some files (disk full?). Report this output (https://github.com/kaantcp)."; finish 4; }
  for f in /usr/local/sbin/z380m-gui /usr/local/bin/z380m-kbd /usr/local/bin/z380m-bright /usr/local/bin/z380m-colortest /etc/z380m/gui/session.sh; do
    sh -n $f || { echo "STOPPED: $f has a syntax error under this shell."; finish 4; }
  done
  jwm -p -f /etc/z380m/gui/jwmrc 2>&1 | head -n 5
  echo "jwm config checked"
  # the keyboard layout name that z380m-kbd will find
  echo "on-screen keyboard: ${KBD:-none} ($(ls /usr/bin/svkbd-* 2> /dev/null | tr '\n' ' '))"

  hdr "9 text console hook (the only existing file that is changed)"
  C=/etc/z380m/console.sh
  if [ ! -f $C ]; then
    echo "STOPPED: $C does not exist. The desktop files are installed but the console hook is not. Report this output (https://github.com/kaantcp)."; finish 5
  elif grep -q 'z380m GUI mode (added for z380m-gui)' $C; then
    echo "already patched"
  else
    [ -f $C.orig ] || cp -p $C $C.orig
    echo "original: $(sha256sum $C | cut -c1-16)... (expected 729fb25c... if nobody edited it)"
    if sh $HERE/patch_console.sh $C $C.new $HERE/console_block_a.txt $HERE/console_block_b.txt && sh -n $C.new; then
      chmod 755 $C.new
      mv $C.new $C
      echo "patched; backup: $C.orig   ($(( $(wc -l < $C) - $(wc -l < $C.orig) )) lines added)"
    else
      rm -f $C.new
      echo "STOPPED: could not patch $C safely (anchor lines not found?). The file is unchanged. Report this output (https://github.com/kaantcp)."; finish 5
    fi
  fi

  hdr "10 colour fix (a small library, built here)"
  rm -f /usr/local/lib/z380m-fbfix.so
  SHIM=no
  if command -v tcc > /dev/null 2>&1; then
    mkdir -p /usr/local/lib
    if tcc -shared -nostdlib -o /usr/local/lib/z380m-fbfix.so /usr/local/src/z380m/fbfix.c > /tmp/z380m-tcc.txt 2>&1; then
      PLAIN=$(fbset -fb /dev/fb0 2>&1 | grep rgba)
      FIXED=$(LD_PRELOAD=/usr/local/lib/z380m-fbfix.so fbset -fb /dev/fb0 2>&1 | grep rgba)
      echo "fbset without the fix: ${PLAIN:-?}"
      echo "fbset with the fix:    ${FIXED:-?}"
      if [ -n "$PLAIN" ] && [ -n "$FIXED" ] && [ "$PLAIN" != "$FIXED" ]; then SHIM=yes; echo "colour fix: built and it changes what X would see (off until you ask for it in Menu > Display)"
      else echo "colour fix: built but the self-test did not show a change"; fi
    else
      echo "colour fix: the compiler failed:"; head -n 5 /tmp/z380m-tcc.txt | cut -c1-120
    fi
    [ "$SHIM" = yes ] || rm -f /usr/local/lib/z380m-fbfix.so
  else
    echo "colour fix: skipped (tcc is not installed)"
  fi

  hdr "SUMMARY"
  echo "packages: $N new, +$ADD MiB; free on / now: $(df -k / | awk 'NR==2{printf "%.0f", $4/1024}') MiB"
  echo "$XV"
  echo "touch: /dev/input/$TEV; on-screen keyboard: ${KBD:-none}; colour fix library: $SHIM"
  echo "undo everything: sh /root/gui-uninstall.sh      log: $LOGF"
  echo
  echo "INSTALL OK. Next, in this window:   z380m-gui start"
  finish 0
}

main 2>&1 | tee -a $LOGF
rc=$(cat $RCF 2> /dev/null || echo 9)
exit "$rc"
