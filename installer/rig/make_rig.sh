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

# Builds the two x86 test rigs used by scripts/test_gui.py, installer/test_install.py and installer/test_paste.py.
# They run the REAL scripts of this pack with Alpine 3.24.2's own BusyBox, apk-tools and OpenRC-less userland (x86_64) in
# throw-away chroots, against stand-ins for the tablet (fake Xorg, fake z380term, fake packages, fake /proc files, a mock fbset).
# Nothing here proves anything about the tablet; it catches script bugs before the user has to find them.
#
# usage (as root):  bash installer/rig/make_rig.sh <pack root> <alpine-minirootfs-3.24.2-x86_64.tar.gz>
#
# The tarball: git clone https://github.com/alpinelinux/docker-alpine.git  ->  x86_64/alpine-minirootfs-3.24.2-x86_64.tar.gz
# (branch v3.24; check it against checksums.sha512 in that repository). Needs: root, gcc, unshare, chroot, tar.
# This script deletes nothing: if a rig folder already exists it stops and tells you.
set -e
SCR=$(cd "$1" && pwd)
TAR=$(readlink -f "$2")
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
[ -f "$TAR" ] || { echo "cannot read the tarball: $2"; exit 1; }
command -v gcc > /dev/null || { echo "gcc is needed (two stand-in programs and the colour-fix test library)"; exit 1; }
for d in rootfs_x86 rootfs_inst_base; do
  [ -e "$SCR/$d" ] && { echo "$SCR/$d already exists: move it away first (this script deletes nothing)"; exit 1; }
done

logstub() { # logstub <rootfs> <name>: a program that only logs its arguments to /tmp/stub.log
  printf '#!/bin/sh\necho "%s $*" >> /tmp/stub.log\n' "$2" > "$1/usr/local/bin/$2"
  chmod 755 "$1/usr/local/bin/$2"
}

# ------------------------------------------------------------------ 1. GUI rig (test_gui.py)
G=$SCR/rootfs_x86
mkdir -p "$G"
tar xzf "$TAR" -C "$G"
mkdir -p "$G/usr/local/bin" "$G/usr/local/sbin" "$G/etc/z380m/gui" "$G/var/log" "$G/run" "$G/tmp" "$G/dev/input"
gcc -static -O1 -o "$G/usr/local/bin/Xorg" "$SCR/scripts/stubs/xorg_stub.c"
gcc -static -O1 -o "$G/usr/local/bin/z380term" "$SCR/scripts/stubs/z380term_stub.c"
install -m 755 "$SCR/scripts/stubs/jwm_stub.sh" "$G/usr/local/bin/jwm"
for n in setxkbmap xrdb xset xsetroot rc-update xterm; do logstub "$G" "$n"; done
install -m 755 "$SCR/scripts/gui_inner.sh" "$G/tmp/gui_inner.sh"     # plays BusyBox init for console.sh (started by gui_outer.sh)
# fake sysfs bits that z380m-gui reads. The touch screen is event7 here ON PURPOSE (on the tablet it is event11), so that
# scripts/test_gui.py proves that z380m-gui finds it by NAME and does not just fall back to its default.
while read -r n name; do
  mkdir -p "$G/sys/class/input/event$n/device"
  echo "$name" > "$G/sys/class/input/event$n/device/name"
done <<'EOF'
2 mtk-kpd
7 elan-touchscreen
9 m_batch_input
EOF
mkdir -p "$G/sys/class/leds/lcd-backlight" "$G/sys/class/graphics/fb0"
echo 102 > "$G/sys/class/leds/lcd-backlight/brightness"
echo 255 > "$G/sys/class/leds/lcd-backlight/max_brightness"
echo mtkfb > "$G/sys/class/graphics/fb0/name"
echo 32 > "$G/sys/class/graphics/fb0/bits_per_pixel"
echo 3200 > "$G/sys/class/graphics/fb0/stride"
echo 800,3840 > "$G/sys/class/graphics/fb0/virtual_size"
echo U:800x1280p-0 > "$G/sys/class/graphics/fb0/modes"
# (the scripts under test are copied into this rig by test_gui.py itself, every run)
echo "rig 1 ready: $G"

# ------------------------------------------------------------------ 2. installer rig (test_install.py, test_paste.py)
I=$SCR/rootfs_inst_base
mkdir -p "$I"
tar xzf "$TAR" -C "$I"
mkdir -p "$I/usr/local/bin" "$I/etc/z380m" "$I/opt" "$I/tmp" "$I/dev" "$I/sys/class/leds/lcd-backlight" "$I/sys/class/graphics/fb0"
echo /repo3/packages.adb > "$I/etc/apk/repositories"
install -m 755 "$SCR/scripts/gui/console.sh.orig" "$I/etc/z380m/console.sh"
install -m 755 "$SCR/installer/rig/inst_inner.sh" "$I/tmp/inst_inner.sh"
install -m 755 "$SCR/installer/rig/mkrepo3.sh" "$I/tmp/mkrepo3.sh"
# a library that the fake tcc "compiles"; it must load into a musl process
gcc -shared -fPIC -O1 -o "$I/opt/z380m-fbfix-test.so" "$SCR/installer/shim/fbfix.c"

cat > "$I/usr/local/bin/apk" <<'EOF'
#!/bin/sh
# test rig only: the real tablet has trusted keys and no such wrapper
exec /sbin/apk --allow-untrusted "$@"
EOF
printf '#!/bin/sh\nexit 0\n' > "$I/usr/local/bin/ping"
cat > "$I/usr/local/bin/df" <<'EOF'
#!/bin/sh
echo "Filesystem           1K-blocks      Used Available Use% Mounted on"
echo "tmpfs                   499300     39836    443716   8% /tmp"
EOF
cat > "$I/usr/local/bin/evtest" <<'EOF'
#!/bin/sh
if [ "$1" = "--info" ]; then
  [ -e /tmp/evtest-noinfo ] && { echo "evtest: unrecognized option --info" >&2; exit 1; }
fi
echo 'Input driver version is 1.0.1'
echo 'Input device name: "elan-touchscreen"'
echo 'Supported events:'
echo '  Event type 3 (EV_ABS)'
echo '    Event code 53 (ABS_MT_POSITION_X)'
echo '      Min        0'
echo '      Max      799'
echo '    Event code 54 (ABS_MT_POSITION_Y)'
echo '      Min        0'
echo '      Max     1279'
[ "$1" = "--info" ] || echo 'Testing ... (interrupt to exit)'
exit 0
EOF
cat > "$I/usr/local/bin/fbset" <<'EOF'
#!/bin/sh
# rig only: stands in for BusyBox fbset on the mtkfb; shows the red/blue offsets swapped when the colour-fix library is preloaded
case "$LD_PRELOAD" in *z380m-fbfix*) R=16; B=0 ;; *) R=0; B=16 ;; esac
echo 'mode "800x1280-0"'
echo '    geometry 800 1280 800 3840 32'
echo '    timings 0 0 0 0 0 0 0'
echo "    rgba 8/$R,8/8,8/$B,8/24"
echo 'endmode'
EOF
chmod 755 "$I/usr/local/bin/apk" "$I/usr/local/bin/ping" "$I/usr/local/bin/df" "$I/usr/local/bin/evtest" "$I/usr/local/bin/fbset"

# fake /proc files (the installer reads them through Z380M_TTY_DRIVERS and Z380M_INPUT_DEVICES)
cat > "$I/tmp/drivers-vt" <<'EOF'
/dev/tty             /dev/tty        5       0 system:/dev/tty
/dev/console         /dev/console    5       1 system:console
/dev/vc/0            /dev/vc/0       4       0 system:vtmaster
unknown              /dev/tty        4    1-63 console
EOF
cat > "$I/tmp/drivers-novt" <<'EOF'
/dev/tty             /dev/tty        5       0 system:/dev/tty
/dev/console         /dev/console    5       1 system:console
EOF
cat > "$I/tmp/inputs-none" <<'EOF'
I: Bus=0019 Vendor=0001 Product=0001 Version=0001
N: Name="mtk-kpd"
P: Phys=
S: Sysfs=/devices/virtual/input/input1
U: Uniq=
H: Handlers=kbd event1
B: PROP=0
B: EV=3
EOF
{ cat "$I/tmp/inputs-none"; cat <<'EOF'

I: Bus=0000 Vendor=0000 Product=0000 Version=0000
N: Name="elan-touchscreen"
P: Phys=
S: Sysfs=/devices/virtual/input/input11
U: Uniq=
H: Handlers=event11
B: PROP=0
B: EV=b
B: KEY=400 0 0 0 0 0
B: ABS=661800000000000
EOF
} > "$I/tmp/inputs-touch"
# fake sysfs bits that the scripts read (z380m-bright, the survey)
echo mtkfb > "$I/sys/class/graphics/fb0/name"
echo 32 > "$I/sys/class/graphics/fb0/bits_per_pixel"
echo 3200 > "$I/sys/class/graphics/fb0/stride"
echo 800,3840 > "$I/sys/class/graphics/fb0/virtual_size"
echo U:800x1280p-0 > "$I/sys/class/graphics/fb0/modes"
echo 102 > "$I/sys/class/leds/lcd-backlight/brightness"
echo 255 > "$I/sys/class/leds/lcd-backlight/max_brightness"

# the fake package repository (real apk-tools 3 builds and indexes it), then apk update against it
unshare --mount --uts --pid --fork bash -c '
  set -e
  mount --bind /dev "$1/dev"
  mount -t proc proc "$1/proc"
  chroot "$1" /bin/sh -c "sh /tmp/mkrepo3.sh && /usr/local/bin/apk update"
' _ "$I"
echo "rig 2 ready: $I"
echo "next: python3 -I scripts/test_gui.py $SCR ; python3 -I installer/test_install.py $SCR ;"
echo "      python3 -I installer/mkpaste.py $SCR $SCR/out ; python3 -I installer/test_paste.py $SCR"
