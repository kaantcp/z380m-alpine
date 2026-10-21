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

# z380m_touchfix.sh  (version @VERSION@) - touch for the desktop, and the right console colours after the desktop.
#
# It flashes nothing and writes only inside Alpine's own root filesystem (/usr/local, /etc/z380m, /root, /tmp).
#   1. unpacks and checks two files that are inside this script: z380m-touchbridge (a small program, source:
#      z380m-touchbridge.c) and z380m-gui version 2 (the desktop starter, now with the touch bridge);
#   2. keeps your present files as z380m-gui.v1 and console.sh.v1, then installs the new ones;
#   3. asks for two taps (top-left and bottom-right corner) to learn which way the touch panel counts, and saves that;
#   4. starts the desktop. It falls back to the text console by itself after 15 minutes unless you KEEP it.
#
#   sh z380m_touchfix.sh          do all of it
#   sh z380m_touchfix.sh undo     put the two old files back and remove the bridge
#
# The two files are stored below the code as base64 (lines starting with #), each with its sha256 checked before anything is installed.
PATH=${Z380M_PATHPRE:+$Z380M_PATHPRE:}/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
SELF=$0
SELFABS=$(cd "$(dirname "$SELF")" 2> /dev/null && pwd)/$(basename "$SELF")
MODE=${1:-install}
# test hooks (unset on the tablet): extra PATH, a path prefix for the files, the test mode, no prompts, no desktop start, fixed corner results
R=${Z380M_ROOT:-}
TESTMODE=${Z380M_TESTMODE:-}
FAST=${Z380M_FAST:-}
NOSTART=${Z380M_NOSTART:-}
HOOK1=${Z380M_TEST_P1:-}
HOOK2=${Z380M_TEST_P2:-}
G=$R/usr/local/sbin/z380m-gui
B=$R/usr/local/bin/z380m-touchbridge
CONF=$R/etc/z380m/gui
C=$R/etc/z380m/console.sh
TFL=$CONF/touch.flags
RUNF=$R/run/z380m-gui
PANNED=$R/run/z380m-fb-panned
LOGF=$R/root/z380m_touchfix.log
UIN=${Z380M_UINPUT:-/dev/uinput}
PSEC=10
BRIDGE_SHA=@BRIDGE_SHA@
GUI_SHA=@GUI_SHA@
TMPB=${TMPDIR:-/tmp}
RCF=$TMPB/z380m-touchfix.rc
T=$TMPB/z380m-touchfix.$$
rm -f "$RCF"
NOTE="(nothing was changed)"

finish() { echo "$1" > "$RCF"; rm -rf "$T"; exit "$1"; }
stop() { echo; echo "STOPPED: $*"; echo "$NOTE"; finish 1; }
ok() { echo "  ok    $*"; }
hdr() { echo; echo "[$1] $2"; }
# the value of KEY=NUMBER in a RESULT line
rget() { echo "$2" | sed -n "s/.* $1=\([-0-9]*\).*/\1/p"; }
sha_of() { set -- $(sha256sum "$1" 2>/dev/null); echo "$1"; }
running() { [ -s "$RUNF" ] && kill -0 "$(cat "$RUNF")" 2>/dev/null; }
# a file inside this script (base64 of a gzip file, one line each starting with #) -> the file on stdout
payload() {
  awk -v n="$1" '$0 == ("#@@ BEGIN " n) { on = 1; next } $0 == ("#@@ END " n) { on = 0 } on { print substr($0, 2) }' "$SELF" | tr -d ' \t\r\n' | base64 -d | gzip -dc
}
# put SRC at DEST with mode MODE; the old file is replaced by a rename, so a program that is running keeps its old copy
put() { cp "$1" "$2.new" && chmod "$3" "$2.new" && mv -f "$2.new" "$2"; }

# the new line(s) for console.sh (z380term gets -n once X has changed the display format)
write_zopt() {
  cat > "$1" <<'ZEOF'
  # after the desktop has run, mtkfb uses the pixel format that X asked for, so z380term must not swap red and blue any more
  # (/run/z380m-fb-panned is made by z380m-gui when it starts X; it is gone after a reboot, when the bootloader's format is back)
  ZOPT=; [ -e /run/z380m-fb-panned ] && ZOPT=-n
  if [ -n "$SER" ]; then "$Z" $ZOPT -s "$SER" -- /bin/sh -l 2>> $LOG; else "$Z" $ZOPT -- /bin/sh -l 2>> $LOG; fi
ZEOF
}

patch_console() {
  if [ ! -f "$C" ]; then echo "  --    $C is missing: the console colours after the desktop are not changed"; return 0; fi
  if grep -q 'ZOPT=' "$C"; then ok "console.sh has the colour flag already"; return 0; fi
  needle='if [ -n "$SER" ]; then "$Z" -s "$SER" -- /bin/sh -l 2>> $LOG; else "$Z" -- /bin/sh -l 2>> $LOG; fi'
  write_zopt "$T/zopt.txt"
  if awk -v needle="$needle" -v blk="$T/zopt.txt" 'index($0, needle) && !done { while ((getline l < blk) > 0) print l; close(blk); done = 1; next } { print } END { if (!done) exit 3 }' "$C" > "$C.new" 2>/dev/null \
     && sh -n "$C.new" 2>/dev/null && grep -q 'ZOPT=' "$C.new"; then
    chmod 755 "$C.new" && mv -f "$C.new" "$C" && ok "console.sh: z380term now starts without the red/blue swap once the desktop has run"
  else
    rm -f "$C.new"
    echo "  --    console.sh has a different z380term line than expected: the console colours after the desktop are not changed (touch is not affected)"
  fi
}

# one corner test. Sets RES (the RESULT line) or returns 1 when the panel sent nothing twice.
corner() {
  cname=$1; hook=$2; tries=0
  while :; do
    tries=$((tries+1))
    echo
    echo "  >> $cname corner: $3"
    if [ -z "$FAST" ]; then
      echo "     Press Enter in this window, then tap that corner of the TABLET screen a few times (${PSEC} s)."
      read -r _ru
    fi
    echo "     TAP NOW ..."
    if [ -n "$hook" ]; then
      RES=$hook; hook=
    else
      "$G" touchtest "$PSEC" > "$T/probe.out" 2>&1
      sed 's/^/     /' "$T/probe.out"
      RES=$(grep '^RESULT' "$T/probe.out" | tail -n 1)
    fi
    fr=$(rget frames "$RES")
    [ "${fr:-0}" -ge 1 ] 2>/dev/null && { echo "     seen: $fr touch reports, average x=$(rget avgx "$RES") y=$(rget avgy "$RES")"; return 0; }
    [ $tries -ge 2 ] && return 1
    echo "     The panel sent nothing. Once more."
  done
}

do_undo() {
  running && stop "the desktop is running. Type  z380m-gui stop , wait for the text console, then run this again."
  [ -e "$G.v1" ] && { mv -f "$G.v1" "$G" && ok "z380m-gui is version 1 again"; }
  [ -e "$C.v1" ] && { mv -f "$C.v1" "$C" && ok "console.sh is as before"; }
  killall z380m-touchbridge 2>/dev/null
  rm -f "$B" "$TFL"
  ok "touch bridge and touch.flags removed"
  echo "Undone. The desktop starts with: z380m-gui start (touch will not work, as before)."
  finish 0
}

main() {
  echo "$Z380M_CREDIT"
  echo "z380m touch fix @VERSION@   $(date '+%F %T') (the tablet clock may be wrong)   mode: $MODE"
  trap 'rm -rf "$T"' EXIT
  mkdir -p "$T" || stop "cannot make $T"

  hdr 1/6 "checks"
  if [ -z "$TESTMODE" ]; then
    [ "$(hostname)" = z380m ] || { echo "WRONG WINDOW: this is not the tablet (hostname: $(hostname)). Run it in the T window. Nothing was done."; finish 1; }
    case "$(uname -m)" in aarch64|arm64) ;; *) stop "this is not an aarch64 machine ($(uname -m))" ;; esac
  fi
  [ "$(id -u)" = 0 ] || stop "run it as root"
  ok "tablet, root"
  for c in base64 gzip sha256sum awk sed tr cut cp mv tee; do
    command -v $c > /dev/null 2>&1 || stop "the tool $c is missing"
  done
  ok "tools: base64 gzip sha256sum awk sed tr cut"
  case "$MODE" in
    install) ;;
    undo) do_undo ;;
    *) stop "unknown argument $MODE (use: sh $SELFABS   or   sh $SELFABS undo)" ;;
  esac
  [ -x "$G" ] || stop "$G is missing: the desktop pack is not installed"
  command -v Xorg > /dev/null 2>&1 || stop "Xorg is not installed"
  [ -r "$CONF/xorg.conf" ] && [ -r "$CONF/session.sh" ] || stop "$CONF/xorg.conf or session.sh is missing"
  ok "desktop pack present (z380m-gui, Xorg, xorg.conf)"
  running && stop "the desktop is running. Type  z380m-gui stop , wait for the text console, press Enter, then run this again."
  ok "the desktop is not running"

  hdr 2/6 "unpack and check the two files inside this script"
  payload bridge > "$T/z380m-touchbridge" 2> /dev/null
  s=$(sha_of "$T/z380m-touchbridge")
  [ "$s" = "$BRIDGE_SHA" ] || stop "z380m-touchbridge is damaged (sha256 $s, expected $BRIDGE_SHA). Fetch the file again."
  ok "z380m-touchbridge  sha256 $(echo "$s" | cut -c1-16)..."
  payload gui > "$T/z380m-gui" 2> /dev/null
  s=$(sha_of "$T/z380m-gui")
  [ "$s" = "$GUI_SHA" ] || stop "z380m-gui is damaged (sha256 $s, expected $GUI_SHA). Fetch the file again."
  sh -n "$T/z380m-gui" || stop "z380m-gui does not parse"
  ok "z380m-gui 2        sha256 $(echo "$s" | cut -c1-16)..."

  hdr 3/6 "install (your present files are kept as .v1)"
  NOTE="(some files are installed, the desktop was not started. Undo: sh $SELFABS undo)"
  mkdir -p "$R/usr/local/bin" "$R/root" "$(dirname "$G")" "$CONF" 2> /dev/null
  if [ ! -e "$G.v1" ]; then
    if grep -q '^VERSION=2' "$G" 2> /dev/null; then echo "  --    z380m-gui is version 2 already: no .v1 copy made"; else cp -p "$G" "$G.v1" && ok "kept $G.v1"; fi
  else
    ok "$G.v1 exists already (kept)"
  fi
  if [ -f "$C" ] && [ ! -e "$C.v1" ]; then cp -p "$C" "$C.v1" && ok "kept $C.v1"; fi
  put "$T/z380m-touchbridge" "$B" 755 || stop "cannot install $B"
  put "$T/z380m-gui" "$G" 755 || stop "cannot install $G"
  ok "installed $B and $G"
  patch_console

  hdr 4/6 "does the program work on this kernel?"
  v=$("$B" version 2>&1) || stop "the touch bridge program does not run: $v"
  ok "$v"
  if [ -z "$TESTMODE" ] && [ ! -c "$UIN" ]; then
    um=$(cat /sys/class/misc/uinput/dev 2> /dev/null)
    [ -n "$um" ] && mknod "$UIN" c "${um%:*}" "${um#*:}" 2> /dev/null
  fi
  u=$("$B" check 2>&1) || {
    echo "$u"; ls -l "$UIN" 2>&1; grep -i uinput /proc/misc 2>&1
    stop "uinput does not work here, so the panel cannot be bridged. Report the lines above (https://github.com/kaantcp)."
  }
  ok "$u"

  hdr 5/6 "which way does the touch panel count? (two corner taps)"
  echo "  Hold the tablet the way the text console reads: first line of text at the top."
  corner "TOP-LEFT" "$HOOK1" "where the first character of the first line is" || NOP=1
  if [ -z "$NOP" ]; then
    r1=$RES
    corner "BOTTOM-RIGHT" "$HOOK2" "the opposite corner (bottom edge, right edge)" || NOP=1
    r2=$RES
  fi
  if [ -n "$NOP" ]; then
    echo
    echo "  The touch panel sent no touches at all. Details for a bug report (https://github.com/kaantcp):"
    grep -B1 -A7 -i -E 'touch|elan' /proc/bus/input/devices 2>&1 | head -n 16
    grep -i -E 'touch|elan|tpd|i2c' /proc/interrupts 2>&1 | head -n 6
    stop "no touch seen on the panel. Copy everything above and report it (https://github.com/kaantcp)."
  fi
  x1=$(rget avgx "$r1"); y1=$(rget avgy "$r1"); x2=$(rget avgx "$r2"); y2=$(rget avgy "$r2")
  xm=$(rget xmax "$r1"); ym=$(rget ymax "$r1")
  [ -n "$x1" ] && [ -n "$y1" ] && [ -n "$x2" ] && [ -n "$y2" ] || stop "could not read the corner results ($r1 / $r2)"
  [ -n "$xm" ] && [ "$xm" -gt 0 ] 2> /dev/null || xm=1472
  [ -n "$ym" ] && [ "$ym" -gt 0 ] 2> /dev/null || ym=2368
  dx=$((x2 - x1)); dy=$((y2 - y1))
  tx=$((xm * 35 / 100)); ty=$((ym * 35 / 100))
  echo
  echo "  top-left x=$x1 y=$y1   bottom-right x=$x2 y=$y2   panel range x 0..$xm y 0..$ym"
  fl=
  if [ $dx -gt $tx ]; then :
  elif [ $dx -lt $((0 - tx)) ]; then fl="$fl -x"
  else echo "  The left/right direction was unclear (the two taps were too close together): not mirrored."; fi
  if [ $dy -gt $ty ]; then :
  elif [ $dy -lt $((0 - ty)) ]; then fl="$fl -y"
  else echo "  The up/down direction was unclear (the two taps were too close together): not mirrored."; fi
  fl=${fl# }
  [ "$xm" -gt "$ym" ] && echo "  note: the panel is wider than tall; if taps land on the wrong axis, report it (https://github.com/kaantcp)."
  echo "$fl" > "$TFL"
  ok "mirror flags saved: ${fl:-none}   ($TFL)"

  hdr 6/6 "start the desktop"
  echo "  Look at the TABLET screen. Then:"
  echo "    1. tap anywhere: an arrow pointer must jump to your finger."
  echo "    2. tap 'Menu' (bottom left), then 'KEEP this desktop'  (or type here:  z380m-gui keep )."
  echo "    If touch does not work, do nothing: after 15 minutes the text console comes back (or type: z380m-gui stop)."
  echo "  This window turns into a plain shell in a few seconds: press Enter once."
  echo "  Undo everything: sh $SELFABS undo"
  NOTE="(everything is installed)"
  if [ -n "$NOSTART" ]; then echo "  (test: desktop not started)"; finish 0; fi
  "$G" start 900
  finish 0
}

main "$@" 2>&1 | tee -a "$LOGF" 2> /dev/null
rc=$(cat "$RCF" 2> /dev/null); rm -f "$RCF"
exit "${rc:-1}"
