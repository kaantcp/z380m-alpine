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

# z380m_touchfix.sh  (version 1) - touch for the desktop, and the right console colours after the desktop.
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
BRIDGE_SHA=936d15cab2b5383de849113c193df03f9f797ab1015644aa5ef36c3a1f252028
GUI_SHA=fd7caa39c6bae863a60e9c5ff3dbb2d5dd78540860fab23ef5b317ebdbba65f9
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
  echo "z380m touch fix 1   $(date '+%F %T') (the tablet clock may be wrong)   mode: $MODE"
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
#@@ BEGIN bridge
#H4sIAAAAAAAC/606fVRTd5b35RF4L3wYEBTRnjzQrklQkRatXwwBZA6IbacYO9XWQoBUMMhHCFbb
#MoTS9lBxOvOqM7OV7ort7hmSfmlPW0zHPYBtd23dmcXacedj9xTQnuJHqzCtJk7Z7L3vIyZR2/7R
#nBN+73fv/d17f/d3v36PdJSs/7GGYUD9aGAAaJaQLUhziwLvywqRIGwFaPFvLP6NxXlMGJ0FhIgx
#XWGtjpxCxyjrrn+EiJGJhYgR9NfXaWmtAo+ZJUSMxnkQMYavoyVLlX0sLRIixtDeEiLX3feZqzYW
#foDPy2PJNATxEw6OBTdb08lIcNLxsTtXLN2+2NXUVlNX7ayv3WoXcoXqXYLDZmt01TQLi4U6l6u5
#dVVOztZ6V11b9ZKapu05ClLi93SMvJ9PtfLYpMyF7badO/Ohrb6xuc0lNDlWCTZhR73T1WZrECRp
#QmuN025vFB61tQr4ZHPZawVbY63gtG9v2mGv1YGwS4BFQuuuRgGanU3V9lXCTkFiuysfcfkyEJqa
#7Y1g0sFqoch6T6X13o3FpYJ9h73R1YrExGK10GBrdQmoi7C9vhHXbSyr3FBirSwv2VRUZr2+ShVS
#a99RX2MXbjTMKgFyEJkj7ShHkpGbS9zWltxfWVxRUmgtIX0bmlzXFdiJ6uarnB+pb9xqdwq1TY82
#CvW4K+ERp227vXU1IpyyhjeRWWNrbESOtE0B0Ey10NzU0KCyVAWhXHtNU2MtybTt2IqsFtfDkiXw
#qLPehVIFV51d3VitHQ1f3+yqb2oEZ1sj7LA7W+lZ19ZqI4E3OgRSCQ8urhdwn1vwYSf92UV/dmwR
#nhAkTcLxLmFDSfG996zdQNiaOnuNA0dFig5o93gUdBy7JOMox1FYtIGOA4fKB24C2yTtC09v8U5Q
#do3PO1TKkvuJEM8BTxUqSjZsXG+FxS7QySe2vb61Jkf2RKizNzTLUAUgGG3VrSEXa2xSj6kVnVNH
#PuN0NjlJ6iO2+gb0UaPd6UQqkA4PfUJY/KObOvYictdo9XAr6JCuXc12oXCVsGHTPZV3WysrSn5y
#b4U1pEKzrdHeIDhtqAWxkCwY0mPX9SNtkk5VFS2fLqBCkquE71A+UYVQPllVlqRJEQaV04EHhHOn
#rcaB3BfX14Z8C2UuEhz2XTcNibZGRyP5c5PkUBERotpX9nI5/PC8KScVa0+eZ8E7/fgMz/R7rFj6
#tOXIN016z7WtyR4DDy3+yhTPlZ/O9Hx1b6qnnAErz1kCBD9YAdYrrMH8NX4Hu+Yd+VsweLn1ik7E
#HJ+qwlWYQWD/6GkO6onuE3BXmBnLSq8Z8hZpQbyANI5lSeIEqzNvR7iBSXQcBLB2p1lWOBBfFwwu
#U+HD2WCtSnA/z8W5K8bYmd5x1uA9g9+z+MX8+ck53EdVvX8gr92yd7D4Nv/B17srXnoPTvaz7gqG
#PeQcZVMj6N0Ab/vOPGYysHMcDSgzgDqnH3FX0NphXEv06trodb+78Jipkp0rrfs7rsswdiL9HPMY
#m24eZ+eaz7AZ5rPsLPNnbJo5XQv7onF3IGzI5R+4ijpb0CZjaIfMf0H7ce6Kao27IlzeBI712+pW
#cGiPD9EeGi2cpDVES3YIp83qsOyVeK2dKRLNmyhHgzDpLF5PlGC05lWEV6u0/ZwE/y3CihCm0ryM
#8+UM5IX0O5oi6ZfFROq3LJzmf1JvSkMwolFhEu1byWIWwqQ9/syyl+x4DnFpAJffzkoUZ+F4+thy
#cTaOV1MSxHQcM/C7uStB7Gfn+bkhd4WG4U/QOR3U8D0TcZEyDYvgcEz62nexwFrH0M7uh/0Dww/D
#WxN/Y95cA3wPpy38+EANTHZ3lPby00V7V06X9vi65vqzU8E6E+W0OhPFqmOVO23jlTurNRZfI51j
#CuT1oU8dLIaTg+xtRwZZw5FrCDf8NtFniYG8slcKTf3sliOvsJVH1r9XZLp7sNi0hOHK/8Do4gcZ
#aPk5E1/OMc9lvMbo47HotziYn2cYGN7BDT+Lo87BH96d0cEkONaxFl/d8B6E6R3c4V9mfKSBPB3q
#tO72Yl8B0nXGYCzi3GQq9tH60USwnkf7GTH+MAYvc5nFvtJEyDNSvOH305+Bp9TU5zyugwDhDZms
#byHSliMOzkLTNhzjcQ8OHLOhz/nRP2hMJ7K0pgssvFlu6psa0rjzT2RBIBvxQ092rhlKcueXLwRT
#aTz48LxSsXW6vEdMEGn9bq3FR/JOIA/aE8l/lgFfFeUPjCeiKdvk6SU567SQrEO5Be3gyc7UmGhP
#RhPr41ii6e8tRTyn4At4CHi6HjriQTt3vBHT0oA2CMUB+dOCmeI4RPqABAe9WMS6fUT7ZQz6eJz8
#LOHS9eI5gsWHw3jxLMIieCu+Gs778TjS7W4fh2dD++pjH/KPsbO8mnZTL62L8P9v3LvJR/rBv3wU
#+UFMmtgJ7uc/Y2FfMAV8QQ0EVsbBZGs1iLaLQWt/14N+Tsv1PDuDO1GghclXJoJWbrL91Hk2zVte
#X7fixTg4aWDmXShPgxWd6N/5weDsCeTLlSSJ8ZgvBdSV8q5tcVAv5ZSo2Khk4h3McrAKcH1/UtxG
#7fEwC6mhPG3iv1ee7lwemac10BnB8xrGIpT5Bx7suFWenntDnvb89THTpxpeyreYI8yzIvL03Fvm
#6Zd+8ZipAzTSOqwXZlbK0zzm4lmYnw2Ynw3mMwtZz/hsCLyOZzEYXOMhm9T3PvNxsCPWo9aYYEec
#h/geRD2DHTEeY5K74sMr704NsnP8ZSN/nTpa+8LHg8HVnvqaiamLgX/G51WeNfy/TjVsOzqF3b3n
#aM77U6+6Tk0FO7SepNLuCqw13sHgSg/F04svXp0a7LrNn97urtiTfnaKdE/EOHgtM1Hs79ri/5Lp
#c3LtZb0edov/Lia1RzddsXcj5qrBjnxJV9KJ9Imuh9757R6u/SHMbRV7jUh/TqM7wTFpPcbM9F4D
#+pSjEONxuvjUuzk/MvVhPstEXnQOxMPU/p+9MZjDTdNrTxkPpvdy7Um9nvn5HiMv52vKp6PJ/oHC
#AniL7D8hnXWiVzN0Yw4euibnX4MeDlfhc2G+f6AzH94qqILJM4GglfLxlc/BI+V7zLl1G381ZXzi
#eO8clB1gITCEOdjCQp4hBlpGMYcYEqBlmAXrMObliTstgYKj0IK1MXniTgggnbXgLLTYcJyYbwlI
#8PkQwBqSOnGXJUBrCFZg1LZM3AWBfnaTn0vrzujHc0wimtUyDU/rCpA3h7wRf25+nAfvgqmEiyG6
#hQrvhRA4hrXhc/SdqrjrtaEN84eghTwv1gIP1oJXuh7yZzOwjOKn/+XVngn0wf6XV3loPjEDAjSf
#mIn6YNxfZHmvB3PJ+WwIYGwlVzKc42IOBEoPd2dUYq5/pWuevx/rVCn2OWVYN7xdm/0erIfP4vwA
#5tvdWEO8XRl+L/ugX5oP45yd6/d2bfKvY7iefnazn2P4Hu/LKz3kq+SP5Ifkq+h3I+R35KuS3+Gc
#S04QyS8NyYC1BgJYh1K/ax3RUz47jfmMmQpar3xuwb1aAnOYOT0VmKsK0BfgfNCKuXAEuERxKwOp
#1DNekfvGEeobMeeMOA4mihUo4yI+7/Eki9Q/foHPr+Umi/egf17C50tMsqif4a6YxOfcj2aJ1GcW
#/tnpF8CyEmtO3oIYEM+wgL1XvLcEYR2gdYxhPuhKtawoQlwN5i4W94R+K9EUIU0J9iOUN4aR7iWk
#qQTOsQ2fN+yq9t+PtJF8E7w/lvjGfgvfBIkv8WTY6zwxOVqLkecoy3pTcF3lO9BSpXfvPzv7QAaD
#9MIQ3GdYAC2lsWCtgZieUYyrGly7IAFSQJ/Ua8M1C5DmgBFaUJ7VhPIA61Em0oyjbmfZGZgTGO8z
#yKsS9aOcXY1rnkJ8Neqnwm0YV8vRthiDqeMYx4UINwDjyEyXa8Q4m2LuQ7vOlvbDeGXeyd/Jdwz5
#LlPW092A9Kc9pqS6/1IZC5MV/35gf+U4M2m945f7K2LQ1zWcIxv95eo3wdmkR7GkB+vo/HvQKih2
#rUL+f6J6h7zO45mvsyeJVBOpPz6BONKXemSsayOZtUlidC02Yp3iEiDPjPRUIz+MD+qzpdoV7+iM
#B2sp1jSTUtMegFD9G3F8kPq96h+jAyvu09yZIOVkcxeOyzXYT6T5B84hnwnMhZQnhE1D+TzG7Bjq
#FZ67+9h/WtOfIOdZqmuFfbupZt1w3zFiziV49HrCKXV9JPNonLT/oqj6/zuMN4tK40qQaMbZG+8d
#25R7x0e4P/VeoNKQjWmd0meNZD6RJqo9U1FUHyHFuYUXx1DfrWhTsjsPQb1JshnvmIg7kMG3d5z6
#NeqVjfKwlxmhXiYB8ZXYD9t8Qes2tDXpsg11+Y/p4GyJ51cJ4j4G9lG+VG0Vbguyj2qrMWV+czum
#3tSOLeF2ujxLtmXMjXYq3GX3m+qu39HC7zrhdgrxukW/VYbzjd/zbMLvhD/M2WR4C9GWJsTnoQ6q
#fdcwdH+de4N9yG4h/nU6UVD4H2O+XVc1Pm92f5V4PZAoyjkn1avBuLmGsM0DySH+pGfWjX3+SOY8
#dd0c71eoM/UGEnxtigTXYKx9SfC7FPgns0LwCYKvVuBHuBB8HOFCmCzlPjCSaeXFIgjb/7xZIf2K
#tFH7xz6EcAzyK8H9UO8grdkZH5JznOQXKHAuNQQ/hnDqUSR4FR+CH1X0+lZ7NGC+Msiyac0buOYU
#1rUriDv9umwruq+M4xn0k/zZivxD1+W8RPC5Mg+iTSWb4Lm8+B3yj1563DOAPc+jPORd+Zn0nmEk
#cyReOZ9Z3j3Ed4Yib1FCSN4zBJ9pCVxF+NUMXtFxtpdwHYTLVta8z4sEI/wugueoOsq0LoSRbhKf
#d2TfCb17QJrQewd2nln2BS7Ez0782LlmP8LT30gMwcfYdO/DiHsX+61wO02wGWai+Sni3saeS6Wd
#YNMk+H0RtprtJbtE2ysec2IoZ1fJ71mORb0Hwt7I++5/P+YJ0e2Rc8ixm539+7NDts5F+ahbXn+X
#4kdPyWevSTy93yz512Y/PcehDuF4ivUsxI/L72tGMs/qJfhtCHuyQznTCVlOOhN6nzSS2RcnwWYy
#8vskCXZRtlUSwl5S/eEbOc54hMk5UfWPmd4YFWbUh3JBEBRYQnIozq+BbNtvy6nnpDOPzF1UB47H
#yz4wjb3EKAviv10L/gZA+OS88k7uHPY5Et9veS8X3ndMPz7okfOw7tZ5+GxKKA+PR+VJrI0nCDeN
#uqxm5PcPaq65Wd6efny4f4itPE3vb6hPp30acjU+qq39b4Jehz2+qRDEAoaZtBQ+tcZS2L3Ghj3i
#6OdxTUQbiXevofcIxItqL4/8TCfjRWbLUH7BHAgI2jhTJgOvCbw7PyuRMy1I400km/Z8nmXNF1mN
#+QLLmL/AvvAS8v4Sv5eRj74oTswF9/O0J3onwGxr8tN7gayodwLSu1vG/86nDExeygRRSL7v2pLk
#5/YHbTBZ+H/KPaE7DWtUkncn+ukSjKvOV3dXUM3vhH6neuajiFd59un8Awdfpd4pyavSFZkibQhI
#0xlFUx1l5yrePzAWRRPdJwxxN9JE+6GANIQffm13CB5OSzSXZNqRTOF28Sd4p5H6oN+nicnMjJ4p
#9LOldTkrlsZiT3QP2olN8RbimRFNwXpYSbxh2DK9+CHGR/6yqIrxPdkj6yAYYZrkZffHm6R7eXPy
#JN4RrKq+mVF9k2SbGP870j1f6g/ixQzKD+p8TTK9n70+53RiSvj8yEwxKXy+Vi/qwuf79CLdpw0A
#k93oH8yh7v3yOsw9weBveIRRjKo+fo7VeDEuzRRz2XXXY86CfqDGWERPg3069Zr1KMON9yF6Z8Bo
#wVrwCbRQb34R907vDdy8DCvEOcXNxD+CnvA84/bxPN+TVQI+6oc0/ws+/o/gI10O4j2f3gv0EQ/k
#W4h3OIop0k26T/wa9Ga8Z3MYW4aw2Br9DHKIt3SnxtgyZOJ9mocAMDBNfAlHY8GfoEWIld9j0Dri
#adyHPKVc6fZVgrwH3e9B0rG078Bmo1bWTeLNJIgSrdbi0zHgexZzP8dbfKU0Ip5PK/Z5AJbheRxa
#l5sgWhjLtGUYvsE7TzKfxvoUHQ/RvZ/u+8SXciyNlWugZYKhftlgLj3UnWFS3jOafwF6rr1fV4Y6
#oRxJF4LXPRdlz6cVe46h7n+W6YJdcLIA/eD855o3z2GOPY7fRdbOv3hfeGGqHGV9MR/EYAesfK79
#o149njvqeZ8hCSb/MF186r8Ox8+9pJ13xxv1RvKJk114JztwO0xeRL/uxrxhA/8A+YoW/eAc8vFi
#b2ZG2nMsZz6PcuAJy17ymzKGLz+PePKfLPSpQjo/JW+jfqJi20McU6za8RCHdjRooQXvf1ZpbksQ
#+RLLEcydvhkoj+xLNih7BvTlXxf5HBr/XUY+vofDc6lj8Lksu4crsfhwrc/4gdtn5FFmskbkGIvP
#SDC0E71bx/g+BB9YpiUZ6DfkL1IcoI4O5BXP+JdzybKvUX5H+YcQby4IaHxa+f8Bh7hAka8bII/g
#o7h32s8F6uEVfY6DfzndYwnfUYg5F/lgnzi7/GuN7zSO0g8JNla3NbrahJoGW+NW9d/IQu6KJblL
#7hSMuW0SNtcE6+sbHXbnKkEhX79+rUIEsMTZVGtz2WCJy77TBUuqW1uBfsaw3d6Is9a6VpfTZauG
#H+jDKN87lHkVIyijPD8Y+SMU9WcfoQ8f9tuRiN+bxEb9zkTFR62fofzmhYWo351kRf3e5BbyUxX5
#S6Pg6vqim+w3fLwtTHb4x6msX3iL9ern/wFH93DmICQAAA==
#@@ END bridge
#@@ BEGIN gui
#H4sIAAAAAAAC/61c61fbSLL/vP4rOorvYGfwi2Qea49zDwlOhr0EONgEstmcHNlq27rIkkct8VjM
#/37r0S21JAOze3c+TEDqru6qrvrVo0u8fNGZ+mFHLWsvxfj04LJ15M9kqGTr0JNh4s99GffFx9Oj
#1ut2txWFwR2Mex+t72J/sUxE431T7HX3fhZXrhsms7VoLJNkrfqdzsJPlum0PYtWHf2uWXsJc0/d
#OBHRXPzz9a/dVcsN1n4o+2Kf/hVHfpjeiigUyVKK/fH5WPxdhqeuJ35td0Xj7zDl0674NPm19/Pr
#ZpvITZa+Eus4WsTuSsCP81hKoaJ5cuPGQPcuSsXMDUUsPV8lsT9NEyn8RLih14lisYo8f34HD4BS
#GnoypoUTGa8U7hF/+Xh8Lj7KUMZuIE7TaeDPhJaQcGFlfKKW0hPTOxwOdD7gDsZ6B+JDBHTdxI/C
#XXEtYwU/iNeGtia0nZN8w57wWSLLaA27W7oJsnDjB4GYSpEqOU+DXQEjgcrF4eT3k/OJ2D/+Ii72
#z872jydfBjA2WUZpIuS1ZEr+ah34QBj2GMPh3OGOPo3O3v8O4/ffHR4dTr4AMZDQh8PJ8Wg8Fh9O
#zsS+ON0/mxy+Pz/aPxOn52enJ+NRW4ylfEZQQGlOwgZ5eDJx/UC1xRc4GQWbCjyxdK8lnNBM+tew
#JVfMQL22iB+Vp3QAQRQuiDkYa0mvMfcDkO7h+9HxeNRsi8O5CKNkVyiJe/nNqOjNzU17EabtKF50
#AiapOm/btRop2vf3Z6ODw8nQsTUVj9moeks8rutODRbiiYvUh6EqQb0HtYOfojWxBltdL/0ZiMuT
#6gqfNi5hK6j+HU9ed+bTrvhR/O3iU9NYBO1LJO40kAkrjbAW4SW+jkfvT44Pxt/gXSJVIuI0bINy
#yWwV2KZUIl0bqkxPqBkoLgw9DwOpFFtOFM79eEUSpsWe+s/Jd3Il5doRDTjzTzJMxVvxP6PRKR+R
#2URh7SatAEqu9y4anpy7aZCIvTfd5u6zS4M1LCLgaerOrkQSaSO+TZABFQV0an6iZDBvl2SGOy3S
#0jz3iYjZLYj2DkQGeBjYfOJRMp8u6O80ipJm5UyiEv1H9xhGN6XJsaQjbd1mk/UTcUmaZO/QWPjC
#v/bBJvAVHygv2HDngGpkW8DeQsyWbriQld3euOtZFESxMgsqoDtbEjmA0M40SKWY+wTRwHU0n4uG
#tRTY843CgbQ9Gowk19Jr7iKNMGegqrtJqmw53RDMKVTfEDiqiGYdARnrP4C2+A6VaCFCKT3YAwjZ
#891FGCFSIDaAqq0GABoqEsq95hGdGE6tAyRbTLKd3CaltfBcWzJETTVSIR5s8btpEq0A5sGagzvh
#JrwdmioaJ2sZnr0H9ImvAWUsBXKa25YC4M/X8iKELr0iOq6EibrhHQHqNgIgZJnJZhZIl90azVuk
#buyJBiAh+I4guinvIInS2ZJwwwISPFc+ENJaHCLWbigD4Cn0lGjE0vUoOABXE8VXijEZNMSopSUr
#DgMulgjRtgjhoNUu7QT9L+tVwUA0ZLCuNVE3UP+MIZyP36GEfYDTAIEaDAEQAc49cAFY8JSBDRkE
#iADHESvKUoJHuol94Bd1YR64atkGN8e2DP8kaRyqrdaaMkraunED8QA4Yw9XeJfJup8dmc0sbh7E
#xeeKDp693TqW134EhpDpkz55pI16EMh5AmvP/ZCjjoYr0JIFQdA6upExLD4DgXtpbHAA4AyOcwWh
#VSKb5ArAwchk1qFTR93vEBusGvIW4g6VibXAtM8MGiDMlc1Bnn+PoivVL5O+BZfWBskuQE2AVuwK
#cnJuvEhXEGAqQIbSDBBCELnEW+BPYxfsCMOHo4Pvp2ejo5P9A4wNkIjtGUo0wJNjqNUOIvSvemFw
#fCsX9RXJkSrxqCfokK6b7UdrjON4OlsMvZ7GvreAWBNwuiNaYJZ+HON5hMIFWT5BPIxaPFc06Pwx
#fEWr4CPYBZQHaauKzXk+xEpJcLdbsC6mhFGx+KzjzL2+NdesRGpGdFgB19K94jVW4HB9vVAcJRF4
#AlgCIpQlSXtHAahBXCK8GEwrxrAaNRK2yOCeswkqG3otsLprP05SkD8atB/CDyi5KxnD6irb/OeJ
#UOma4LzRUksImq9JK4wGovA56E3AfFVVK+ndJdiByrfA/k27SF8BCJASgUmJRgYxqxTsgtAVnFTu
#3wy0gixP9ye/DzupijukSB0FqVLf+j37NX9BP/Cv8L+avCXOkFBtPDr6UKbWyaC3BmgLrwsqUjs6
#+TjsXLs4Y5EPBbVe1C4L7/CE2l168eFoH14AnFq0MQArPWth7FMbT04qLzBoqZ2NxhOI9svvtAOv
#jX8/PTywXzL2thhj175X+3i+f3YwrCNXFr7UDg7Hp8N+t/Z5dDY+PDke7tXenR0efBwNi2LtVAwM
#xpWWtF7SihPkfKyXtCwXjvH4eFSYOp+2wAhC6YHKkLdbIniJBvggcJ3F4LQPRoCOgvKmcJ2izgCO
#7zKE3Km50o9n4D/04wRSKhqVqXGaTwVYu5a1g9Hnw+Nh/Z6TDfjt++Hx6fmk36Lgn0Y/1MZfxtYg
#+C0bBAt3aEEzdDL5cnB4lo3lX5naQ+2cpmUvz+2lUk2glq4bTXEv0uFAfBWtWAASR7NOCqi3kuKb
#+OEHgX4e36Tiu/it8H4g5GwZCad+n/Zb//3gDMRDDZSRCPKbr/VGum5+E/VXjnj7VtRBfXGQi8Kg
#YbCmAgI9h9e6wvy21YUnjRmYLb5oOmLvLe05TIMAZ78EqPJDCIcE5DTKXUjGDY7xMGqBkAmAyBVq
#BZEZYE7oUSij02DLHUM+1EB4ypyEcc3zOFoxPkIu06wBXvjzO9xwTWjOMuvoI3PwGNAcmBmLTrJa
#d9qXvV4rDf3bzmWXOdNLiNa1uCUgeisypoDBH3oDCpZrCGRoLkf7X4Z1/EEPby0kpHAJ+MU3v97+
#LFqA2oEJKx3RAqVcitZM7ODuzLkIAfIbCBVgwvPrDg5x6CRKS4sfYNm5X3vABJbDfgTw3P30rZiC
#VRrmY1hLIZ9DIx2UOSRcInRBcxohBsM0zTiECAK0letJXTUxzquGi30nElrAcTLE/cC5xFQFqZNB
#dLCOkbwaQHRMQiJtdeqx1+G9dHBdVKPNBr1EAqGPpIFxODTaVB5sKVaTxs5cyBtgXEjc8Bm/amb0
#xABEq9zZlrGvvk6Sb8gEDAcG6vex9/Llq87DAPgEb2vN9EAQNdp/iNMTvWeYRBz2epmO4cvsUGIK
#xcIIRQ8qBgCEz/og0isp6gQsLKJj1l4GKdL6FXrwpY4mcXksfuG873SY3xGftOy/ohI5mlxmlhwU
#iy4MWOXS5GOp91CGFVlq9lahYY9JIHOrK4hmRGtt1inMpfewocImcEv3q/C/+q8eHP7x5av+Q3le
#de8oPHRs31nXNI/TNYOdEnVyL8wjPGXG+CHygGY317/nLE3XRZZQKoRb/MraU2lQOOwOMLYCu81x
#rjwFdvJV1EPRChLRA+xAfdcW3G3vDQSKvxH+2Gs2B0aTniTGL/9afYn8mb2Rjk3+80Ei16B0FMp5
#FWEzJFcuFhM8CBAB0Yg07EBXFCAHMJjB1tokfNcHa4UBkPwALSUoR3XRhcvBlvgY17RHGjZNdQgS
#K68AQAksC2LOgan5Z7S2aE8wLCG7AB0An6hBUq9MA4yi4jA07ZUPiUm4QF9SntAvDMYRllZrDUBX
#VwmRSntkH3WLKo3hFyv+V/EC/QdHUHl68s1ySDTvBZsXhxFO4b0Q6UpbjxWjAEMzHWjgJqpom5lU
#utJAY0zfLEKGn64yw09X2wyfnBf+k8wDE8fUOTBksvhcGzc/5vWNGCBEFC0/hw4+uDrMMkFL7iYR
#PnxvWH9BPxNO1/EJONUMKIRAcxiisXZrXNdCo8/s+rW2ay0E9HTXT3g6y9tdP+vteHAWP10/4fEc
#MdQao81NWxWJ7J55qN9fF/wYxl+mSBXK4ilek9gYTHGsfmvgicVUgkd74FaUqxXWYgUuLVa1PHpZ
#0M8AJK/m+RHzdKeKKY6ZkJugNggMFpED4qOZmyRBH2Wsql+/B6Xpt8DAQ/lgSFkuINPUKnkPSCNs
#YqUe1hoAfppiTrEEwGSLAAC5tczpQpBQIO2HENcGgfSeJkpbKwsqeVxQ5DWosIPFV6y7lXN/xn/Y
#6uxK32NwIUAHIyHGiZGAcMZVWKkGC+D0AjKpDjsTZYpXtI6fR+j6eiIrHoiGj7GNpBAJywtUxEZm
#wQ6AefYhQLiHVNy8XkGeA68Lp1JEaxlKXYQKqWKfWwsWWS4w3KXguMyp0qkFRcU6CYx1vPtoDEaF
#me1xHSwnQ5XG8vs1a7XSvun45PNkyFC+iMFcWn/k8nOsPPD7wdkhptuQ75VF+lDKqHKYL8OVD3Al
#xS8FtKIoq86ZJlKFQYRC9xq8i69m4g2SKQUlpKUkm8JoJ0cXHwHArwKAZUukriSOnnFtDjltjw7P
#otwrwd6LoZUA2X5MB3zWzFoGHtaU6gBtdVWt0Je4rPb94qaKetioqtwua/1Cgnpniu5kuRpBwG0e
#uCMsjsED2bm0ebItDsDxlzzekoGedrll2iMhbGVoIYj9uRDD9rZGsMIKU7ctTEeNjIBPxffDSgTE
#J1fNvfWTbisADEKhxZiXJlpodG6LCFHisSu6LNi6ZblR6QIcNZbCWGrW3jnEoHflsgWxoPWLBog6
#XZDWsRgn6rrylo+hSlo5XudXGMGYzaMANRITMipdadcFKF3sHmTXGj3k4dIAZeZtajQ5U6Y/J008
#FxM5ow8q4hU8ueTanInIKMC0rgZIS/UYLbrSEDT+l2Ak2muY0L5iZn1B1kEsN4xFNcEN7CKwZq6g
#oPmIHEXN54Re1HlLgtN6x3IxDuT2kMfD//WuHTM2t04r0acjPz0bZdkmcWduOoh7fGuzrl8y3+jG
#k7suNnmADBAy+lQO5yPm/KtSbQcVTikWyGN2C3S6JuQvPu4ZOVQYu06wgpRFFUBhV8cQ/IZ4xP4X
#XS/jGtEas7u5XYjfFavkaj7NLzfW/q0MTHleV/NddUUXLSa59FlHcTg6THOfiRICb4fXYm1afVK+
#HcjK/U0q85eup81NUE5rR+md7AoFqSldm1+igy7eFjQ0/baiKMBT+v4GVLWJO+Ggq86VZ2OhZFko
#MDo1Lulp6dbv4fz7P0JYqXWiDr83KW7ML76G+HDLZNDiKPDB74OHwcYUd4ZP+Bq4pW/8LXvCJ4DH
#0YJum+p4kUC/AhpO8bL852qqQ0hLiQ7nMU9lMU+VPvMY/ymfUUgGtjiLvHIGmv2CS8ePLvnEQhBj
#WDZPR0TCLcXffF1OcmpyxP2SGgr4oMwdJSkuugfAXV12M8edqQ5iZaHwDBAGhoxlO7zbv3HvalYS
#BYftmAxM472NDNoWY7mKsJmhCCkYAt+4gIakR1k0ZZXeOMTPeOYSOOt7/T58oODipe05RONvF5/6
#4B3BKLEWvqvL6QTNxTo1GAVvx9zDwoOKTo0znWLj0KuYqJ4TrDH5z1KBSqVr7KVQpop3AXTue/3W
#3psusvnu5ASvOvb6rQdTP63XMSnX3lLLcovP1f7YKPyA95jtUC8LmAH0sn3euOBSPBhQv784eFD1
#e1y//+Mu3/rTsAdiIYkBOHbKpBbYzSGUvwDIdtA7Y1AywEvgRPR2xO/np+LweCImo7NPeWyHS2jd
#0EiD3NToyHrt6h0pder4oY9NDWrt3oD7zwHMYOyNizV7Nm2SFdXvMTKlQCffc7NUZ6JbiWJ8YkWH
#cI6633PrZcdTZc7tISIY/TM0rWjM5YBs2zYH+SpgDCS7vfaWlpGs8yRvLyHngM8m5k5Jt4hR6w4q
#9+gM1IculCiXxTXBZX4cd62fe8Qqe+CZsXScWZ/lNRabbRPZj86K4QoAvQJrATq6mZfufxTeQirI
#7YtM5wbxxPUtKqC0yAU74jeBC6Md4T9WFYw0moWWyYv2WKlGXOyfHR8ef+xTKGY168yxS3ZQamgL
#Au4MxbFENkSNhqDGT3TigzZluaN+5oJeitdtq0lOQ0st6936fstpatHYECT19Ddtsoa+bnXhvsxC
#04jAzqdd9OnYAwjvnKxdz6G+NflHCg+kt2smZjiBnU6I/DrBvhsCKSvZ7lsZdqagCZpBkiXBz/rP
#ewvakTvpOZWyXU5i/ASJjN9HqHylijHBqNZgHetgT5cRwmPTDO7aM02PoD1ZQ7YePiCpuQvQuApd
#E+tKDfA6yK0neG0KrF7kOS4vZ46FlHIHmyJ2TDsqA3q+d12ws03RAmJeRP4hfu5mK9gZnPbXuVeA
#37HpQFGfwa5uzaN+PeJZr5blxVjTAL6xVEusc63FCpRMapqpTR4nsaKjPaKmsxPldsTvGARqP4rJ
#x2+/7YxOPuzUXr7g/hSsg8WzFuhsDUxzFvvUBDV0JuR2ip3LxW7lQl+xA7OBkkcr/YXDDJQEXgwI
#6vpYAQYksDESDQ+TU7kAPp2xCaSQLOGVWdip/eXRhhqiD0RgVeIY5VOmG63X/zpd6o/J6YK4UJ76
#DhjjEO5mfcCssaYRp5kdYQOBOqWKe9eUyyp9BHgN4SryQY4NT9yhnLUPkNQrDnU7SRPlYRyaVYEr
#xMvpOeUKJlGMq1HdYwyUSQAGWrOsK67yBvK6CkYg2owq5N0Ak6470x2sg0XOnnFes2kIdzNDoihx
#L4sSt3RvKFvPtCa0xRFYqbktLPbKOxYZqxX5EBtO5hJiAgm8m9RQxwn66pPuPYXlNPuYUCglRiGa
#RhTO5GPkJxG3rVub3IWNrf9ksz37o7u13NYIb4Dv4kCowSPrR1ipvoHouxpm8qcFVD/LW+6ZTMME
#KRi+HH1wRKuVhfEaln+zFLkaJQo2ocEAr+2p1Z5d9YwU2XSSlHqtde/tv2A3GUY/YzHd/6fFWOvQ
#EFzID2GPazgjWVmFPY40xcCCB2Mq7D70e9NC+mhDsUlxuZN4QOErar5RFbvsWbGk7TZaHKPTEu35
#1F04e14Nupwy/Xk9sCY3ha1Oe3hP9drhUajbPMna9SO4hTLRoFKBJivTGhQScqp0oYvULp6MSX9I
#AhqzHWyiq93qNyZt8c4qPusD6IvyJyfElqJm+n+HLat4XNYzzSOGc49hJPvMwZPW75cg0ClfGbAy
#046/FTLAvWczQOY+i7b/DRGIRqpKUkUX/diBZ1GnHZ62bq0Adbuo9Egq+JU/2DFnmH1xw2wcHb6z
#G2EDf5o1rM7927aKLDCoVJELt9xbC0YrtRg672G9NKbPeE4+fGiLM7nV72mmAl4MgAz2VlqDM0l8
#/vbZlY7xK5Hqh0GkLs1nN6FMfwG3XwpnQuaRkS+jtGjQtnSQQaE9QitoXkzfUrjXrh+gO6SlqUUb
#72Cf+Hi1nWmHfXdvtlMHfp3HsXGrIuVnDy4A5w+IUa1HDawKKiHnczlLTPhBGXCmrHPfAAGGm81t
#Sph9c1rX/dZO1qhrf+ToPBd65bWf/jMxV86BPaeIP7kb+WolaoUFM/TkvlJE1L64k6q4xNZRYZQv
#wcPQkYOMG1w1IrdeynVpnLXJZtmksXaUk9hWTXqWDCuBbmzDytAlEswvqas9bY9RBxe6hbL5DsXe
#5KMdYFt3W2+UWsLMoB1szrDMq7mj16/2V9k74kYYUWy3yiZKcz1iTyx9rGG+44Do7lKAKc/4qoZU
#YcsnYqRA+vKTNCI7qFaYL7z1+i3XFFPZzzZeuI5zCqpLn2tgXbXtWQliUZX1p7+J3jleyvCdAoeo
#2bSy+RSn2VpdiATzzU+tj85OAWtGxxO+/qp8GwjxBdUZmo5xpgiBjCD3Nrg7w+Gw8tnlUxhi5rVa
#LY1LMNrEevygMo6uBRqBqxIsnWBBUKEs8ENxLLLAs+zioDoXb2X6QuInVxDv3rgxanL+2QVRE+6U
#74o9Ge3qrnUcUL4xNSxwN81I7PyjMRr9o7n5R+PiAv758A5MdDOfgg1tqMt183myuU6+dlt//bZZ
#ueqqv/ngXsHym/d058af4LlqQ38EQGzQJjaf9ZrK/6fceHKdLDfT9Xqzijy5IUFvzulOVffWU5vO
#xm6033zdd7/d6n98tXHpAgqLMjv6Lo+TGbGkjzVC0et1K2IrfhNGt1V1ut4aaOZ94p+GbXjYhts3
#N/PYXcn+jnWZs8mOaq+6kr11lZF/1xOt/V+KyxD3O7rta5rqD1t0z6Iqc/WmutQlKLWP3xTCMuts
#QnaYaNub/71ZbdT11dTb0LcUtOhONuqa/q0QJpanKbjiGI1wSveq82n+mX5Z4nuPiIG6IfASXUGs
#axC/PHvvTfW4zOdE+Vz7Ir/U34T3HxnXpiNsozFyp9pXt92yikj8JN/ZYvFi6u5kW9Tovp06pAoL
#bfS9n3Kj5+clter9VMEkLL6Bj9OARK8fsmlSbv2um7Eu+8LZlOTKHm9bNUu/f7Z8Vm0XHzzWDW75
#b66lWh/Sh9ENRLBYrPr1QSiKUV0PUaHQKN5u6/jY0ftz6Ct3uaWBuYUNwEzPyUso+svl/2Bt0i4q
#Y+6+1T3iJ1BLADzxy08/bR/Cd9WzVrr23EQK1/MsJ5T9bQijV5UdVu6RMl+af5aPf+jCi/qPfHxv
#C0k/+g9KKefMk8FTnOnmq61SZP//JwWQ/w2B8h8QsDml4KBZurSoELf+joC5rGAar5p6cIpf4vWf
#+NMkG643bvjvY2ysv3Sxsf8Ixcb8XYiN+YMPm61/oGBT+A5/U/wzChuLt0ciF30+e8gGNWzpW5L/
#A9FKlEkcSQAA
#@@ END gui
