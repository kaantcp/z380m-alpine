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

# Integration test of z380m_touchfix.sh with the REAL z380m-gui version 2 supervisor (stand-ins for Xorg, jwm and the bridge program).
#   bash scripts/test_touchfix_int.sh <pack-root> <work-dir>        (run as root in a throw-away VM; it installs files under
#   /etc/z380m, /usr/local, /run and /var/log of the sandbox and removes them again)
PACK=${1:?repository root}
WORK=${2:?work dir}
Z=/tmp/zt
PASS=0; FAIL=0
ok() { if ( eval "$2" ) > /dev/null 2>&1; then PASS=$((PASS+1)); echo "PASS  $1"; else FAIL=$((FAIL+1)); echo "FAIL  $1   [$2]"; fi; }
mkdir -p "$WORK"; WORK=$(cd "$WORK" && pwd)
cleanup() {
  [ -s /run/z380m-gui ] && kill "$(cat /run/z380m-gui)" 2>/dev/null; sleep 0.5
  pkill -x z380m-touchbrid 2>/dev/null; pkill -x Xorg 2>/dev/null; pkill -x jwm 2>/dev/null
  rm -rf $Z /etc/z380m /run/z380m-* /tmp/.X11-unix/X0 /tmp/.X0-lock /tmp/stub.log /var/log/z380m-gui.log /var/log/z380m-console.log /var/log/Xorg.0.log /root/z380m_touchfix.log
  rm -f /usr/local/sbin/z380m-gui /usr/local/sbin/z380m-gui.v1 /usr/local/bin/z380m-touchbridge /usr/local/bin/Xorg /usr/local/bin/jwm /usr/local/bin/xsetroot /usr/local/bin/xset /usr/local/bin/setxkbmap /usr/local/bin/xrdb /usr/local/bin/z380term
}
trap cleanup EXIT
cleanup
OLDGUI=$PACK/scripts/obsolete/z380m-gui.v1
CON1=$PACK/scripts/gui/console.sh.v1patched
mkdir -p $Z/dev/input $Z/sys/class/input/event11/device $Z/sys/class/input/event3/device /etc/z380m/gui /usr/local/sbin /usr/local/bin /var/log /root
echo elan-touchscreen > $Z/sys/class/input/event11/device/name; echo 1:3 > $Z/sys/class/input/event11/dev
echo mtk-kpd > $Z/sys/class/input/event3/device/name; echo 1:5 > $Z/sys/class/input/event3/dev
mknod $Z/dev/uinput c 1 3
printf 'tty             /dev/tty        5       0 system:/dev/tty\nserial          /dev/ttyS       4 64-67 serial\n' > $Z/drivers-novt
cp -p $OLDGUI /usr/local/sbin/z380m-gui; chmod 755 /usr/local/sbin/z380m-gui
cp $CON1 /etc/z380m/console.sh; chmod 755 /etc/z380m/console.sh
cp $PACK/scripts/gui/xorg.conf $PACK/scripts/gui/jwmrc $PACK/scripts/gui/Xresources $PACK/scripts/gui/session.sh /etc/z380m/gui/
echo "-sharevts" > /etc/z380m/gui/xorg.flags
gcc -O1 -o /usr/local/bin/Xorg $PACK/scripts/stubs/xorg_stub.c || exit 1
cp $PACK/scripts/stubs/jwm_stub.sh /usr/local/bin/jwm; chmod 755 /usr/local/bin/jwm
for c in xsetroot xset setxkbmap xrdb; do printf '#!/bin/sh\nexit 0\n' > /usr/local/bin/$c; chmod 755 /usr/local/bin/$c; done
printf '#!/bin/sh\necho "z380term $*" >> /tmp/zt/z380term.args\nexit 0\n' > /usr/local/bin/z380term; chmod 755 /usr/local/bin/z380term
: > /tmp/stub.log

# the stand-in bridge program (embedded in the test script)
cat > $WORK/bridge_int <<'EOB'
#!/bin/sh
echo "fake bridge: $*" >> /tmp/zt/bridge.log
case "$1" in
  version) echo "z380m-touchbridge 1 (stand-in)" ;;
  check) echo "uinput ok: a virtual touch screen was created and removed (stand-in)" ;;
  probe)
    n=0; [ -r /tmp/zt/probe.n ] && n=$(cat /tmp/zt/probe.n); n=$((n+1)); echo $n > /tmp/zt/probe.n
    echo "probe: stand-in call $n"
    cat /tmp/zt/probe.$n 2>/dev/null || echo "probe: no finger seen" ;;
  run)
    trap 'rm -rf $Z380M_SYS_INPUT/event12; exit 0' TERM
    sleep 0.5
    mkdir -p $Z380M_SYS_INPUT/event12/device
    echo z380m-virtual-touch > $Z380M_SYS_INPUT/event12/device/name
    echo 1:3 > $Z380M_SYS_INPUT/event12/dev
    while :; do sleep 0.2; done ;;
esac
EOB
chmod 755 $WORK/bridge_int
python3 -I $PACK/installer/touchfix/build_touchfix.py $PACK/installer/touchfix/touchfix_template.sh $WORK/bridge_int $PACK/scripts/gui/z380m-gui $WORK/fix_int.sh > /dev/null || exit 1
echo "RESULT frames=12 avgx=1380 avgy=100 minx=1 maxx=1 miny=1 maxy=1 xmax=1472 ymax=2368 events=40" > $Z/probe.1
echo "RESULT frames=9 avgx=100 avgy=2250 minx=1 maxx=1 miny=1 maxy=1 xmax=1472 ymax=2368 events=30" > $Z/probe.2

export Z380M_DEV_INPUT=$Z/dev/input Z380M_SYS_INPUT=$Z/sys/class/input Z380M_TTYDIR=$Z/dev Z380M_UINPUT=$Z/dev/uinput Z380M_TTY_DRIVERS=$Z/drivers-novt

echo "== I1: the real run (probe through z380m-gui touchtest, then the supervisor starts the desktop)"
Z380M_TESTMODE=1 Z380M_FAST=1 TMPDIR=$WORK sh $WORK/fix_int.sh > $WORK/int1.txt 2>&1; echo $? > $WORK/int1.rc
sleep 5
ok "I1.1 script exit 0" '[ "$(cat $WORK/int1.rc)" = 0 ]'
ok "I1.2 the probe ran twice with -t 10 on the real panel node" '[ "$(grep -c "fake bridge: probe -i $Z/dev/input/event11 -t 10" $Z/bridge.log)" = 2 ]'
ok "I1.3 flags are -x (top-left had the large x) " '[ "$(cat /etc/z380m/gui/touch.flags)" = "-x" ]'
ok "I1.4 z380m-gui is version 2, the old one is kept" 'grep -q "^VERSION=2" /usr/local/sbin/z380m-gui && ! grep -q "^VERSION=2" /usr/local/sbin/z380m-gui.v1'
ok "I1.5 supervisor started by the script" '[ -s /run/z380m-gui ] && kill -0 "$(cat /run/z380m-gui)"'
ok "I1.6 the bridge was started with the saved flag" 'grep -q "fake bridge: run -i $Z/dev/input/event11 -x" $Z/bridge.log'
ok "I1.7 X got -sharevts once and vt1" 'grep -q "Xorg stub: start :0 -sharevts vt1 -nolisten tcp" /tmp/stub.log'
ok "I1.8 z380m-touch points at the virtual device" '[ "$(readlink $Z/dev/input/z380m-touch)" = "$Z/dev/input/event12" ]'
ok "I1.9 the display-format flag exists" '[ -e /run/z380m-fb-panned ]'
st=$(z380m-gui status 2>&1)
ok "I1.10 status shows version 2 and the flags" 'echo "$st" | grep -q "version 2" && echo "$st" | grep -q "touch flags: -x"'
ok "I1.11 the script's output has the final hints" 'grep -q "KEEP this desktop" $WORK/int1.txt && grep -q "In a few seconds this window turns into a plain shell" $WORK/int1.txt'

echo "== I2: back to the text console; console.sh starts z380term without the swap"
z380m-gui stop > /dev/null 2>&1; sleep 2
ok "I2.1 supervisor gone" '[ ! -e /run/z380m-gui ]'
: > $Z/z380term.args
sh /etc/z380m/console.sh > /dev/null 2>&1
ok "I2.2 z380term was started with -n (the flag file exists)" 'grep -q "^z380term -n " $Z/z380term.args || grep -q "^z380term -n$" $Z/z380term.args || grep -q "^z380term -n -- " $Z/z380term.args'
rm -f /run/z380m-fb-panned; : > $Z/z380term.args
sh /etc/z380m/console.sh > /dev/null 2>&1
ok "I2.3 without the flag file z380term gets no -n" 'grep -q "^z380term" $Z/z380term.args && ! grep -q -- " -n\|^z380term -n" $Z/z380term.args'

echo "== I3: undo through the real files"
Z380M_TESTMODE=1 TMPDIR=$WORK sh $WORK/fix_int.sh undo > $WORK/int3.txt 2>&1; echo $? > $WORK/int3.rc
ok "I3.1 undo exit 0, old z380m-gui and console.sh are back" '[ "$(cat $WORK/int3.rc)" = 0 ] && cmp -s /usr/local/sbin/z380m-gui $OLDGUI && cmp -s /etc/z380m/console.sh $CON1'
ok "I3.2 bridge gone, flags gone" '[ ! -e /usr/local/bin/z380m-touchbridge ] && [ ! -e /etc/z380m/gui/touch.flags ]'

echo
echo "RESULT: $PASS passed, $FAIL failed"
[ $FAIL = 0 ]
