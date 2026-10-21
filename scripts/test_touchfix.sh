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

# Test of z380m_touchfix.sh (the one-file installer for the touch bridge) with stand-ins, in the sandbox.
#   bash scripts/test_touchfix.sh <pack-root> <work-dir> [shell]       (run as root; shell defaults to dash)
# Scenarios S1..S17 use a fake root (Z380M_ROOT) and fixed corner results; scenario I runs the real z380m-gui v2 supervisor with
# stand-ins (it installs files under /etc/z380m, /usr/local and /run of the sandbox and removes them again).
PACK=${1:?repository root}
WORK=${2:?work dir}
SH=${3:-dash}
PASS=0; FAIL=0
ok() { if ( eval "$2" ) > /dev/null 2>&1; then PASS=$((PASS+1)); echo "PASS  $1"; else FAIL=$((FAIL+1)); echo "FAIL  $1   [$2]"; fi; }
mkdir -p "$WORK"; WORK=$(cd "$WORK" && pwd)
BIN=$WORK/bin; STUB=$WORK/stubbin; W=$WORK/w; OUT=$WORK/out
rm -rf "$BIN" "$STUB" "$W" "$OUT"; mkdir -p "$BIN" "$STUB" "$OUT"
TF=$PACK/installer/touchfix
GUI=$PACK/scripts/gui/z380m-gui

# ---- stand-in programs for the bridge
cat > $BIN/bridge_ok <<'EOB'
#!/bin/sh
case "$1" in
  version) echo "z380m-touchbridge 1 (stand-in)" ;;
  check) echo "uinput ok: a virtual touch screen was created and removed (stand-in)" ;;
  probe)
    n=0; [ -r /tmp/zt/probe.n ] && n=$(cat /tmp/zt/probe.n); n=$((n+1)); echo $n > /tmp/zt/probe.n
    echo "probe: stand-in call $n"
    cat /tmp/zt/probe.$n 2>/dev/null || echo "probe: no finger seen" ;;
  run)
    echo "fake bridge: $*" >> /tmp/zt/bridge.log
    trap 'rm -rf $Z380M_SYS_INPUT/event12; exit 0' TERM
    sleep 0.5
    mkdir -p $Z380M_SYS_INPUT/event12/device
    echo z380m-virtual-touch > $Z380M_SYS_INPUT/event12/device/name
    echo 1:3 > $Z380M_SYS_INPUT/event12/dev
    while :; do sleep 0.2; done ;;
esac
EOB
cat > $BIN/bridge_nocheck <<'EOB'
#!/bin/sh
case "$1" in
  version) echo "z380m-touchbridge 1 (stand-in)" ;;
  check) echo "z380m-touchbridge: cannot open /dev/uinput (stand-in)" >&2; exit 1 ;;
esac
EOB
cat > $BIN/bridge_noexec <<'EOB'
#!/nonexistent/interpreter
EOB
chmod 755 $BIN/*
printf '#!/bin/sh\nexit 0\n' > $STUB/Xorg; chmod 755 $STUB/Xorg

# ---- build the scripts
python3 -I $TF/build_touchfix.py $TF/touchfix_template.sh $BIN/bridge_ok $GUI $WORK/fix_ok.sh > $OUT/build_ok.txt || exit 1
python3 -I $TF/build_touchfix.py $TF/touchfix_template.sh $BIN/bridge_nocheck $GUI $WORK/fix_nocheck.sh > /dev/null || exit 1
python3 -I $TF/build_touchfix.py $TF/touchfix_template.sh $BIN/bridge_noexec $GUI $WORK/fix_noexec.sh > /dev/null || exit 1
cat $OUT/build_ok.txt
FIX=$WORK/fix_ok.sh
OLDGUI=$PACK/scripts/obsolete/z380m-gui.v1
CON1=$PACK/scripts/gui/console.sh.v1patched
CON2=$PACK/scripts/gui/console.sh.v2

R1="RESULT frames=12 avgx=100 avgy=100 minx=90 maxx=110 miny=90 maxy=110 xmax=1472 ymax=2368 events=40"
R2="RESULT frames=9 avgx=1380 avgy=2250 minx=1370 maxx=1390 miny=2240 maxy=2260 xmax=1472 ymax=2368 events=30"
R1f="RESULT frames=12 avgx=1380 avgy=2250 minx=1 maxx=1 miny=1 maxy=1 xmax=1472 ymax=2368 events=40"
R2f="RESULT frames=9 avgx=100 avgy=100 minx=1 maxx=1 miny=1 maxy=1 xmax=1472 ymax=2368 events=30"
R1x="RESULT frames=12 avgx=1380 avgy=100 minx=1 maxx=1 miny=1 maxy=1 xmax=1472 ymax=2368 events=40"
R2x="RESULT frames=9 avgx=100 avgy=2250 minx=1 maxx=1 miny=1 maxy=1 xmax=1472 ymax=2368 events=30"
R1y="RESULT frames=12 avgx=100 avgy=2250 minx=1 maxx=1 miny=1 maxy=1 xmax=1472 ymax=2368 events=40"
R2y="RESULT frames=9 avgx=1380 avgy=100 minx=1 maxx=1 miny=1 maxy=1 xmax=1472 ymax=2368 events=30"
RN="RESULT frames=0 avgx=0 avgy=0 minx=0 maxx=0 miny=0 maxy=0 xmax=1472 ymax=2368 events=0"
RU1="RESULT frames=5 avgx=700 avgy=1000 minx=1 maxx=1 miny=1 maxy=1 xmax=1472 ymax=2368 events=9"
RU2="RESULT frames=5 avgx=800 avgy=1100 minx=1 maxx=1 miny=1 maxy=1 xmax=1472 ymax=2368 events=9"

# a fresh fake root: version-1 desktop pack, patched console.sh, nothing else
mkworld() {
  rm -rf "$W"; mkdir -p $W/usr/local/sbin $W/usr/local/bin $W/etc/z380m/gui $W/run $W/root $W/dev
  cp -p $OLDGUI $W/usr/local/sbin/z380m-gui; chmod 755 $W/usr/local/sbin/z380m-gui
  cp $CON1 $W/etc/z380m/console.sh; chmod 755 $W/etc/z380m/console.sh
  cp $PACK/scripts/gui/xorg.conf $PACK/scripts/gui/session.sh $W/etc/z380m/gui/
  echo "-sharevts" > $W/etc/z380m/gui/xorg.flags
}
snap() { (cd $W && find . \( -type f -o -type l \) -not -path './root/*' | sort | while read -r f; do echo "$f $(sha256sum < "$f" 2>/dev/null || readlink "$f")"; done | sha256sum | cut -c1-64); }
# run the script: runfix SCRIPT OUTFILE [VAR=value ...] -- args
runfix() {
  s=$1; o=$2; shift 2
  env Z380M_PATHPRE=$STUB Z380M_ROOT=$W Z380M_TESTMODE=1 Z380M_FAST=1 Z380M_NOSTART=1 TMPDIR=$WORK "$@" > $o 2>&1
  echo $? > $o.rc
}
rc() { cat "$1.rc"; }
tmpleft() { ls $WORK | grep -c '^z380m-touchfix' ; }

echo "== S1: normal install, corners as expected -> no mirroring"
mkworld
env Z380M_PATHPRE=$STUB Z380M_ROOT=$W Z380M_TESTMODE=1 Z380M_FAST=1 Z380M_NOSTART=1 TMPDIR=$WORK Z380M_TEST_P1="$R1" Z380M_TEST_P2="$R2" $SH $FIX > $OUT/s1.txt 2>&1; echo $? > $OUT/s1.txt.rc
ok "S1.1 exit 0" '[ "$(rc $OUT/s1.txt)" = 0 ]'
ok "S1.2 bridge installed, identical to the payload" '[ "$(sha256sum < $W/usr/local/bin/z380m-touchbridge)" = "$(sha256sum < $BIN/bridge_ok)" ]'
ok "S1.3 z380m-gui v2 installed, identical to the pack file" 'cmp -s $W/usr/local/sbin/z380m-gui $GUI'
ok "S1.4 both are executable" '[ -x $W/usr/local/bin/z380m-touchbridge ] && [ -x $W/usr/local/sbin/z380m-gui ]'
ok "S1.5 z380m-gui.v1 is the old file" 'cmp -s $W/usr/local/sbin/z380m-gui.v1 $OLDGUI'
ok "S1.6 console.sh.v1 is the old console.sh" 'cmp -s $W/etc/z380m/console.sh.v1 $CON1'
ok "S1.7 console.sh is now exactly console.sh.v2" 'cmp -s $W/etc/z380m/console.sh $CON2'
ok "S1.8 console.sh is executable and parses" '[ -x $W/etc/z380m/console.sh ] && $SH -n $W/etc/z380m/console.sh'
ok "S1.9 touch.flags empty" '[ -f $W/etc/z380m/gui/touch.flags ] && [ -z "$(cat $W/etc/z380m/gui/touch.flags)" ]'
ok "S1.10 output says flags none" 'grep -q "mirror flags saved: none" $OUT/s1.txt'
ok "S1.11 output shows the six steps" 'for n in 1 2 3 4 5 6; do grep -q "^\[$n/6\]" $OUT/s1.txt || exit 1; done'
ok "S1.12 no .new files, no temp dir left" '[ -z "$(find $W -name "*.new")" ] && [ "$(tmpleft)" = 0 ]'
ok "S1.13 xorg.flags untouched" '[ "$(cat $W/etc/z380m/gui/xorg.flags)" = "-sharevts" ]'
ok "S1.14 log written" 'grep -q "mirror flags saved" $W/root/z380m_touchfix.log'
ok "S1.15 says desktop not started in test mode" 'grep -q "desktop not started" $OUT/s1.txt'

echo "== S2: both axes mirrored"
mkworld
runfix $FIX $OUT/s2.txt Z380M_TEST_P1="$R1f" Z380M_TEST_P2="$R2f" $SH $FIX
ok "S2.1 exit 0 and flags -x -y" '[ "$(rc $OUT/s2.txt)" = 0 ] && [ "$(cat $W/etc/z380m/gui/touch.flags)" = "-x -y" ]'
echo "== S3: only x, only y"
mkworld; runfix $FIX $OUT/s3.txt Z380M_TEST_P1="$R1x" Z380M_TEST_P2="$R2x" $SH $FIX
ok "S3.1 flags -x" '[ "$(cat $W/etc/z380m/gui/touch.flags)" = "-x" ]'
mkworld; runfix $FIX $OUT/s3b.txt Z380M_TEST_P1="$R1y" Z380M_TEST_P2="$R2y" $SH $FIX
ok "S3.2 flags -y" '[ "$(cat $W/etc/z380m/gui/touch.flags)" = "-y" ]'

echo "== S4: corners too close together"
mkworld; runfix $FIX $OUT/s4.txt Z380M_TEST_P1="$RU1" Z380M_TEST_P2="$RU2" $SH $FIX
ok "S4.1 exit 0, warns twice, no flags" '[ "$(rc $OUT/s4.txt)" = 0 ] && [ "$(grep -c unclear $OUT/s4.txt)" = 2 ] && [ -z "$(cat $W/etc/z380m/gui/touch.flags)" ]'

echo "== S5: second run changes nothing (idempotent), backups stay the originals"
mkworld; runfix $FIX $OUT/s5a.txt Z380M_TEST_P1="$R1x" Z380M_TEST_P2="$R2x" $SH $FIX
a=$(snap)
runfix $FIX $OUT/s5b.txt Z380M_TEST_P1="$R1" Z380M_TEST_P2="$R2" $SH $FIX
ok "S5.1 second run exit 0" '[ "$(rc $OUT/s5b.txt)" = 0 ]'
ok "S5.2 backups still the original files" 'cmp -s $W/usr/local/sbin/z380m-gui.v1 $OLDGUI && cmp -s $W/etc/z380m/console.sh.v1 $CON1'
ok "S5.3 console.sh still exactly v2 (not patched twice)" 'cmp -s $W/etc/z380m/console.sh $CON2 && [ "$(grep -c "ZOPT=;" $W/etc/z380m/console.sh)" = 1 ]'
ok "S5.4 said so" 'grep -q "has the colour flag already" $OUT/s5b.txt'
ok "S5.5 flags follow the newest test (none)" '[ -z "$(cat $W/etc/z380m/gui/touch.flags)" ]'

echo "== S6: damaged file -> nothing installed"
mkworld; a=$(snap)
python3 -I - "$FIX" "$WORK/fix_damaged.sh" <<'EOF'
import sys
t = open(sys.argv[1]).read().split("\n")
i = t.index("#@@ BEGIN gui") + 5
line = t[i]
t[i] = line[:10] + ("A" if line[10] != "A" else "B") + line[11:]
open(sys.argv[2], "w").write("\n".join(t))
EOF
runfix $FIX $OUT/s6.txt Z380M_TEST_P1="$R1" Z380M_TEST_P2="$R2" $SH $WORK/fix_damaged.sh
ok "S6.1 exit 1 and says damaged" '[ "$(rc $OUT/s6.txt)" = 1 ] && grep -q "is damaged" $OUT/s6.txt'
ok "S6.2 nothing changed" '[ "$(snap)" = "$a" ]'
ok "S6.3 told that nothing was changed" 'grep -q "nothing was changed" $OUT/s6.txt'

echo "== S7: desktop running -> refuses"
mkworld; sleep 60 & spid=$!; echo $spid > $W/run/z380m-gui; a=$(snap)
runfix $FIX $OUT/s7.txt Z380M_TEST_P1="$R1" Z380M_TEST_P2="$R2" $SH $FIX
kill $spid 2>/dev/null
ok "S7.1 exit 1, says the desktop is running" '[ "$(rc $OUT/s7.txt)" = 1 ] && grep -q "desktop is running" $OUT/s7.txt'
ok "S7.2 nothing changed" '[ "$(snap)" = "$a" ]'
echo "== S7b: stale pid file is not 'running'"
mkworld; echo 999999 > $W/run/z380m-gui
runfix $FIX $OUT/s7b.txt Z380M_TEST_P1="$R1" Z380M_TEST_P2="$R2" $SH $FIX
ok "S7b.1 proceeds" '[ "$(rc $OUT/s7b.txt)" = 0 ]'

echo "== S8: uinput check fails"
mkworld
runfix $FIX $OUT/s8.txt Z380M_TEST_P1="$R1" Z380M_TEST_P2="$R2" $SH $WORK/fix_nocheck.sh
ok "S8.1 exit 1 with the message" '[ "$(rc $OUT/s8.txt)" = 1 ] && grep -q "uinput does not work" $OUT/s8.txt'
ok "S8.2 no corner test was asked, no flags file" '! grep -q "^\[5/6\]" $OUT/s8.txt && [ ! -e $W/etc/z380m/gui/touch.flags ]'
ok "S8.3 says how to undo" 'grep -q "Undo: sh " $OUT/s8.txt'
echo "== S8b: the program does not run at all"
mkworld
runfix $FIX $OUT/s8b.txt Z380M_TEST_P1="$R1" Z380M_TEST_P2="$R2" $SH $WORK/fix_noexec.sh
ok "S8b.1 exit 1, says it does not run" '[ "$(rc $OUT/s8b.txt)" = 1 ] && grep -q "does not run" $OUT/s8b.txt'

echo "== S9: the panel sends nothing"
mkworld
runfix $FIX $OUT/s9.txt Z380M_TEST_P1="$RN" Z380M_TEST_P2="$R2" $SH $FIX
ok "S9.1 exit 1, no touch seen, diagnostics requested" '[ "$(rc $OUT/s9.txt)" = 1 ] && grep -q "no touch seen on the panel" $OUT/s9.txt && grep -q "Details for a bug report" $OUT/s9.txt'
ok "S9.2 no flags written, no desktop" '[ ! -e $W/etc/z380m/gui/touch.flags ] && ! grep -q "^\[6/6\]" $OUT/s9.txt'
mkworld
runfix $FIX $OUT/s9b.txt Z380M_TEST_P1="$R1" Z380M_TEST_P2="$RN" $SH $FIX
ok "S9.3 second corner silent -> same stop" '[ "$(rc $OUT/s9b.txt)" = 1 ] && grep -q "no touch seen on the panel" $OUT/s9b.txt'

echo "== S10: console.sh has a line we do not know -> warn, go on"
mkworld; sed 's/-s "\$SER" -- \/bin\/sh -l/-s "$SER" -- \/bin\/sh/' $CON1 > $W/etc/z380m/console.sh; chmod 755 $W/etc/z380m/console.sh; cp $W/etc/z380m/console.sh $WORK/odd_console.sh
runfix $FIX $OUT/s10.txt Z380M_TEST_P1="$R1" Z380M_TEST_P2="$R2" $SH $FIX
ok "S10.1 exit 0, warning, console.sh unchanged" '[ "$(rc $OUT/s10.txt)" = 0 ] && grep -q "different z380term line" $OUT/s10.txt && cmp -s $W/etc/z380m/console.sh $WORK/odd_console.sh && [ ! -e $W/etc/z380m/console.sh.new ]'

echo "== S11: undo"
mkworld; runfix $FIX $OUT/s11a.txt Z380M_TEST_P1="$R1x" Z380M_TEST_P2="$R2x" $SH $FIX
runfix $FIX $OUT/s11.txt $SH $FIX undo
ok "S11.1 exit 0" '[ "$(rc $OUT/s11.txt)" = 0 ]'
ok "S11.2 old z380m-gui and console.sh are back, byte for byte" 'cmp -s $W/usr/local/sbin/z380m-gui $OLDGUI && cmp -s $W/etc/z380m/console.sh $CON1'
ok "S11.3 bridge and flags gone, backups consumed" '[ ! -e $W/usr/local/bin/z380m-touchbridge ] && [ ! -e $W/etc/z380m/gui/touch.flags ] && [ ! -e $W/usr/local/sbin/z380m-gui.v1 ] && [ ! -e $W/etc/z380m/console.sh.v1 ]'
runfix $FIX $OUT/s11b.txt $SH $FIX undo
ok "S11.4 a second undo does no harm" '[ "$(rc $OUT/s11b.txt)" = 0 ] && cmp -s $W/usr/local/sbin/z380m-gui $OLDGUI'
runfix $FIX $OUT/s11c.txt Z380M_TEST_P1="$R1" Z380M_TEST_P2="$R2" $SH $FIX
ok "S11.5 install again after undo works" '[ "$(rc $OUT/s11c.txt)" = 0 ] && cmp -s $W/usr/local/sbin/z380m-gui $GUI && cmp -s $W/usr/local/sbin/z380m-gui.v1 $OLDGUI'
mkworld; sleep 60 & spid=$!; echo $spid > $W/run/z380m-gui
runfix $FIX $OUT/s11d.txt $SH $FIX undo
kill $spid 2>/dev/null
ok "S11.6 undo refuses while the desktop runs" '[ "$(rc $OUT/s11d.txt)" = 1 ] && grep -q "desktop is running" $OUT/s11d.txt'

echo "== S12: not the tablet (no test mode) -> wrong window, nothing done"
mkworld; a=$(snap)
env Z380M_PATHPRE=$STUB Z380M_ROOT=$W TMPDIR=$WORK $SH $FIX > $OUT/s12.txt 2>&1; echo $? > $OUT/s12.txt.rc
ok "S12.1 exit 1, WRONG WINDOW, nothing changed" '[ "$(rc $OUT/s12.txt)" = 1 ] && grep -q "WRONG WINDOW" $OUT/s12.txt && [ "$(snap)" = "$a" ]'

echo "== S13: preconditions"
mkworld; rm -f $W/usr/local/sbin/z380m-gui; a=$(snap)
runfix $FIX $OUT/s13.txt $SH $FIX
ok "S13.1 no z380m-gui -> stop" '[ "$(rc $OUT/s13.txt)" = 1 ] && grep -q "desktop pack is not installed" $OUT/s13.txt && [ "$(snap)" = "$a" ]'
mkworld; a=$(snap)
env Z380M_ROOT=$W Z380M_TESTMODE=1 Z380M_FAST=1 Z380M_NOSTART=1 TMPDIR=$WORK $SH $FIX > $OUT/s13b.txt 2>&1; echo $? > $OUT/s13b.txt.rc
ok "S13.2 no Xorg -> stop" '[ "$(rc $OUT/s13b.txt)" = 1 ] && grep -q "Xorg is not installed" $OUT/s13b.txt && [ "$(snap)" = "$a" ]'
mkworld; rm -f $W/etc/z380m/gui/xorg.conf; a=$(snap)
runfix $FIX $OUT/s13c.txt $SH $FIX
ok "S13.3 no xorg.conf -> stop" '[ "$(rc $OUT/s13c.txt)" = 1 ] && grep -q "xorg.conf or session.sh is missing" $OUT/s13c.txt && [ "$(snap)" = "$a" ]'
mkworld; a=$(snap)
runfix $FIX $OUT/s13d.txt $SH $FIX bogus
ok "S13.4 unknown argument -> stop" '[ "$(rc $OUT/s13d.txt)" = 1 ] && grep -q "unknown argument" $OUT/s13d.txt && [ "$(snap)" = "$a" ]'

echo "== S14: z380m-gui is version 2 already and no .v1 exists -> no .v1 made"
mkworld; cp $GUI $W/usr/local/sbin/z380m-gui
runfix $FIX $OUT/s14.txt Z380M_TEST_P1="$R1" Z380M_TEST_P2="$R2" $SH $FIX
ok "S14.1 no z380m-gui.v1 made, install ok" '[ "$(rc $OUT/s14.txt)" = 0 ] && [ ! -e $W/usr/local/sbin/z380m-gui.v1 ]'

echo "== S15: console.sh missing"
mkworld; rm -f $W/etc/z380m/console.sh
runfix $FIX $OUT/s15.txt Z380M_TEST_P1="$R1" Z380M_TEST_P2="$R2" $SH $FIX
ok "S15.1 warns and goes on" '[ "$(rc $OUT/s15.txt)" = 0 ] && grep -q "console.sh is missing" $OUT/s15.txt'

echo "== S16: a line count check on the output (short and readable)"
ok "S16.1 the normal run prints fewer than 60 lines" '[ "$(wc -l < $OUT/s1.txt)" -lt 60 ]'
ok "S16.2 the script is ASCII only, no TAB, no CR" '! LC_ALL=C grep -q -P "[^\x00-\x7F]|\t|\r" $FIX'
ok "S16.3 the code part parses with dash and with bash --posix" 'dash -n $FIX && bash --posix -n $FIX'

echo "== S17: a bash run of the same scenario S2 (second shell)"
mkworld
runfix $FIX $OUT/s17.txt Z380M_TEST_P1="$R1f" Z380M_TEST_P2="$R2f" bash --posix $FIX
ok "S17.1 same result in bash --posix" '[ "$(rc $OUT/s17.txt)" = 0 ] && [ "$(cat $W/etc/z380m/gui/touch.flags)" = "-x -y" ] && cmp -s $W/etc/z380m/console.sh $CON2'

echo
echo "RESULT: $PASS passed, $FAIL failed"
[ $FAIL = 0 ]
