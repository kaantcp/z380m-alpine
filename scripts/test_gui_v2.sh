#!/bin/bash
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

# Test of z380m-gui v2 (touch bridge start/stop, no-VT stand-in, display-format flag) with stand-ins, in the sandbox.
# Run as root in a throw-away VM:  bash scripts/test_gui_v2.sh <pack-root>      (it installs stand-ins into /usr/local/bin and cleans up)
PACK=${1:?repository root}
Z=/tmp/zt
PASS=0; FAIL=0
ok() { if eval "$2"; then PASS=$((PASS+1)); echo "PASS  $1"; else FAIL=$((FAIL+1)); echo "FAIL  $1   [$2]"; fi; }
cleanup() {
  [ -s /run/z380m-gui ] && kill "$(cat /run/z380m-gui)" 2>/dev/null; sleep 0.5
  pkill -x z380m-touchbrid 2>/dev/null; pkill -x Xorg 2>/dev/null; pkill -x jwm 2>/dev/null
  rm -rf $Z /etc/z380m /run/z380m-* /tmp/.X11-unix/X0 /tmp/.X0-lock /tmp/stub.log /var/log/z380m-gui.log /var/log/Xorg.0.log
  rm -f /usr/local/sbin/z380m-gui /usr/local/bin/z380m-touchbridge /usr/local/bin/Xorg /usr/local/bin/jwm /usr/local/bin/xsetroot /usr/local/bin/xset /usr/local/bin/setxkbmap /usr/local/bin/xrdb
}
trap cleanup EXIT
cleanup
mkdir -p $Z/dev/input $Z/sys/class/input/event11/device $Z/sys/class/input/event3/device /etc/z380m/gui /usr/local/sbin /usr/local/bin /var/log
echo elan-touchscreen > $Z/sys/class/input/event11/device/name; echo 1:3 > $Z/sys/class/input/event11/dev
echo mtk-kpd > $Z/sys/class/input/event3/device/name; echo 1:5 > $Z/sys/class/input/event3/dev
mknod $Z/dev/uinput c 1 3
printf 'tty             /dev/tty        5       0 system:/dev/tty\nserial          /dev/ttyS       4 64-67 serial\n' > $Z/drivers-novt
printf '/dev/vc/0   /dev/vc/0   4   0 system:vtmaster\nserial   /dev/ttyS   4 64-67 serial\n' > $Z/drivers-vt
cp $PACK/scripts/gui/z380m-gui /usr/local/sbin/z380m-gui; chmod 755 /usr/local/sbin/z380m-gui
cp $PACK/scripts/gui/xorg.conf $PACK/scripts/gui/jwmrc $PACK/scripts/gui/Xresources $PACK/scripts/gui/session.sh /etc/z380m/gui/
gcc -O1 -o /usr/local/bin/Xorg $PACK/scripts/stubs/xorg_stub.c || exit 1
cp $PACK/scripts/stubs/jwm_stub.sh /usr/local/bin/jwm; chmod 755 /usr/local/bin/jwm
for c in xsetroot xset setxkbmap xrdb; do printf '#!/bin/sh\nexit 0\n' > /usr/local/bin/$c; chmod 755 /usr/local/bin/$c; done
cat > /usr/local/bin/z380m-touchbridge <<'EOB'
#!/bin/sh
# test double of z380m-touchbridge
echo "fake bridge: $*" >> /tmp/zt/bridge.log
case "$1" in
  run)
    [ -e /tmp/zt/bridge-fail ] && { echo "z380m-touchbridge: fake failure" >&2; exit 1; }
    trap 'rm -rf $Z380M_SYS_INPUT/event12; echo "fake bridge: TERM" >> /tmp/zt/bridge.log; exit 0' TERM
    if [ ! -e /tmp/zt/bridge-nodev ]; then
      sleep 0.5
      mkdir -p $Z380M_SYS_INPUT/event12/device
      echo z380m-virtual-touch > $Z380M_SYS_INPUT/event12/device/name
      echo 1:3 > $Z380M_SYS_INPUT/event12/dev
    fi
    while :; do sleep 0.2; done ;;
  probe) echo "RESULT frames=0"; ;;
esac
EOB
chmod 755 /usr/local/bin/z380m-touchbridge
export Z380M_DEV_INPUT=$Z/dev/input Z380M_SYS_INPUT=$Z/sys/class/input Z380M_TTYDIR=$Z/dev Z380M_UINPUT=$Z/dev/uinput Z380M_TTY_DRIVERS=$Z/drivers-novt
: > /tmp/stub.log

echo "== A: kernel without virtual terminals, bridge works, touch.flags given"
echo "-x" > /etc/z380m/gui/touch.flags
z380m-gui start 9 > $Z/out.txt 2>&1
sleep 5
LOG=/var/log/z380m-gui.log
ok "A1 supervisor running"        '[ -s /run/z380m-gui ] && kill -0 "$(cat /run/z380m-gui)"'
ok "A2 tty1 stand-in is a link to /dev/null" '[ "$(readlink $Z/dev/tty1)" = /dev/null ]'
ok "A3 Xorg got -sharevts and vt1" 'grep -q "Xorg stub: start :0 -sharevts vt1 -nolisten tcp" /tmp/stub.log'
ok "A4 the bridge was started on the real panel with the flags" 'grep -q "fake bridge: run -i $Z/dev/input/event11 -x" $Z/bridge.log'
ok "A5 z380m-touch points at the virtual device" '[ "$(readlink $Z/dev/input/z380m-touch)" = "$Z/dev/input/event12" ]'
ok "A6 the virtual device node exists" '[ -c $Z/dev/input/event12 ]'
ok "A7 the real panel node was made too" '[ -c $Z/dev/input/event11 ]'
ok "A8 display-format flag made" '[ -e /run/z380m-fb-panned ]'
ok "A9 log says bridge up" 'grep -q "touch bridge up" $LOG'
st=$(z380m-gui status 2>&1)
ok "A10 status shows version, bridge and flags" 'echo "$st" | grep -q "version 2" && echo "$st" | grep -q "touch flags: -x" && echo "$st" | grep -q "display format changed"'
ok "A11 status shows the touch screen for X" 'echo "$st" | grep -q "touch screen for X: $Z/dev/input/event12"'
sleep 8
ok "A12 watchdog ended the desktop" '! [ -e /run/z380m-gui ]'
ok "A13 bridge stopped (virtual device gone)" '! [ -e $Z/sys/class/input/event12 ] && ! pgrep -x z380m-touchbrid >/dev/null'
ok "A14 Xorg gone" '! pgrep -x Xorg >/dev/null'
ok "A15 display-format flag stays after the desktop ended" '[ -e /run/z380m-fb-panned ]'

echo "== B: bridge exits at once -> the panel is used directly"
rm -rf /run/z380m-fb-panned $Z/sys/class/input/event12 $Z/dev/input/z380m-touch; : > $LOG; : > /tmp/stub.log
touch $Z/bridge-fail
z380m-gui start 6 > $Z/out.txt 2>&1; sleep 4
ok "B1 fell back to the panel" '[ "$(readlink $Z/dev/input/z380m-touch)" = "$Z/dev/input/event11" ]'
ok "B2 log says the bridge did not come up" 'grep -q "touch bridge did not come up" $LOG'
ok "B3 X still started" 'grep -q "Xorg stub: start" /tmp/stub.log'
z380m-gui stop > /dev/null 2>&1; sleep 2
rm -f $Z/bridge-fail

echo "== C: bridge runs but no virtual device appears -> fallback, and the bridge is stopped"
: > $LOG; : > $Z/bridge.log; touch $Z/bridge-nodev
z380m-gui start 6 > $Z/out.txt 2>&1; sleep 9
ok "C1 fell back to the panel" 'grep -q "touch bridge did not come up" $LOG'
ok "C2 no bridge process left over" '! pgrep -x z380m-touchbrid >/dev/null'
z380m-gui stop > /dev/null 2>&1; sleep 2
rm -f $Z/bridge-nodev

echo "== D: no-bridge file and a missing bridge program"
: > $LOG; touch /etc/z380m/gui/no-bridge
z380m-gui start 6 > $Z/out.txt 2>&1; sleep 3
ok "D1 log says no bridge, panel used" 'grep -q "no touch bridge installed" $LOG && [ "$(readlink $Z/dev/input/z380m-touch)" = "$Z/dev/input/event11" ]'
z380m-gui stop > /dev/null 2>&1; sleep 2
rm -f /etc/z380m/gui/no-bridge

echo "== E: restart-x gives a new bridge and X, keep keeps the desktop"
: > $LOG; : > /tmp/stub.log; : > $Z/bridge.log
z380m-gui start 7 > $Z/out.txt 2>&1; sleep 4
p1=$(cat /run/z380m-touchbridge.pid)
z380m-gui restart-x > /dev/null 2>&1; sleep 5
p2=$(cat /run/z380m-touchbridge.pid 2>/dev/null)
ok "E1 the bridge was restarted with X" '[ -n "$p2" ] && [ "$p1" != "$p2" ] && kill -0 $p2 2>/dev/null'
ok "E2 two Xorg starts" '[ "$(grep -c "Xorg stub: start" /tmp/stub.log)" = 2 ]'
z380m-gui keep > /dev/null 2>&1; sleep 6
ok "E3 still running after the watchdog time because of keep" '[ -s /run/z380m-gui ] && kill -0 "$(cat /run/z380m-gui)"'
z380m-gui stop > /dev/null 2>&1; sleep 3
ok "E4 stop ended everything" '! [ -e /run/z380m-gui ] && ! pgrep -x Xorg > /dev/null && ! pgrep -x z380m-touchbrid >/dev/null'

echo "== F: a kernel with virtual terminals -> nodes made, no -sharevts, no stand-in"
export Z380M_TTY_DRIVERS=$Z/drivers-vt
: > $LOG; : > /tmp/stub.log; rm -f $Z/dev/tty*
z380m-gui start 6 > $Z/out.txt 2>&1; sleep 3
ok "F1 tty0..7 nodes made" '[ -c $Z/dev/tty0 ] && [ -c $Z/dev/tty7 ]'
ok "F2 Xorg without -sharevts" 'grep -q "Xorg stub: start :0 -nolisten tcp" /tmp/stub.log && ! grep -q sharevts /tmp/stub.log'
z380m-gui stop > /dev/null 2>&1; sleep 2
export Z380M_TTY_DRIVERS=$Z/drivers-novt

echo "== G: user's old xorg.flags with -sharevts is not doubled"
: > /tmp/stub.log; echo "-sharevts" > /etc/z380m/gui/xorg.flags
z380m-gui start 6 > $Z/out.txt 2>&1; sleep 3
ok "G1 -sharevts once" '[ "$(grep -o sharevts /tmp/stub.log | wc -l)" = 1 ]'
z380m-gui stop > /dev/null 2>&1; sleep 2

echo "== H: other commands"
ok "H1 touchtest runs the probe on the real panel" 'z380m-gui touchtest 2 2>&1 | grep -q "RESULT frames=0" && grep -q "fake bridge: probe -i $Z/dev/input/event11 -t 2" $Z/bridge.log'
ok "H2 report runs" 'z380m-gui report > /dev/null 2>&1; [ -s /root/gui-report.txt ] && grep -q "touch bridge" /root/gui-report.txt'
ok "H3 usage on nonsense" 'z380m-gui nonsense 2>&1 | grep -q "touchtest"'
rm -f /root/gui-report.txt
echo; echo "$PASS passed, $FAIL failed"
[ $FAIL = 0 ]
