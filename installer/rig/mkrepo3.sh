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

# test rig only (runs INSIDE the x86 rootfs): builds /repo3 with fake packages that carry the files the installer looks for
set -e
rm -rf /tmp/pk3 /repo3; mkdir -p /tmp/pk3 /repo3
mkpk() { # mkpk <name> <version> [depends...]
  n=$1; v=$2; shift 2; deps="$*"
  if [ -n "$deps" ]; then
    apk mkpkg -I "name:$n" -I "version:$v" -I "arch:x86_64" -I "description:test $n" -I "license:MIT" -I "depends:$deps" -F "/tmp/pk3/$n" -o "/repo3/$n-$v.apk"
  else
    apk mkpkg -I "name:$n" -I "version:$v" -I "arch:x86_64" -I "description:test $n" -I "license:MIT" -F "/tmp/pk3/$n" -o "/repo3/$n-$v.apk"
  fi
}
fill() { mkdir -p "/tmp/pk3/$1/usr/lib"; truncate -s "${2}M" "/tmp/pk3/$1/usr/lib/$1.bin"; }
script() { # script <pkg> <path> <body>
  mkdir -p "/tmp/pk3/$1$(dirname "$2")"; printf '%s\n' '#!/bin/sh' "$3" > "/tmp/pk3/$1$2"; chmod 755 "/tmp/pk3/$1$2"
}
empty() { mkdir -p "/tmp/pk3/$1/usr/share/$1"; echo "$1" > "/tmp/pk3/$1/usr/share/$1/README"; }

fill libxfake 6;            mkpk libxfake 1.0-r0
fill librsvgfake 20;        mkpk librsvgfake 2.0-r0
fill xorg-server 35
script xorg-server /usr/bin/Xorg 'case "$1" in -version) echo "X.Org X Server 21.1.99 (rig fake)" >&2 ;; esac'
mkpk xorg-server 21.1.25-r0 libxfake
mkdir -p /tmp/pk3/xf86-video-fbdev/usr/lib/xorg/modules/drivers; echo x > /tmp/pk3/xf86-video-fbdev/usr/lib/xorg/modules/drivers/fbdev_drv.so
mkpk xf86-video-fbdev 0.5.0-r0 xorg-server
mkdir -p /tmp/pk3/xf86-input-evdev/usr/lib/xorg/modules/input; echo x > /tmp/pk3/xf86-input-evdev/usr/lib/xorg/modules/input/evdev_drv.so
mkpk xf86-input-evdev 2.11.0-r0 xorg-server
script xkbcomp /usr/bin/xkbcomp 'exit 0';       mkpk xkbcomp 1.5.0-r0
fill xkeyboard-config 4;                        mkpk xkeyboard-config 2.46-r0
script xsetroot /usr/bin/xsetroot 'exit 0';     mkpk xsetroot 1.1.3-r1 libxfake
script xset /usr/bin/xset 'exit 0';             mkpk xset 1.2.5-r1 libxfake
script xrdb /usr/bin/xrdb 'exit 0';             mkpk xrdb 1.2.2-r1 libxfake
script setxkbmap /usr/bin/setxkbmap 'exit 0';   mkpk setxkbmap 1.3.4-r1 libxfake
fill font-dejavu 8;                             mkpk font-dejavu 2.37-r0
empty font-misc-misc;                           mkpk font-misc-misc 1.1.3-r0
empty font-cursor-misc;                         mkpk font-cursor-misc 1.0.4-r0
script xterm /usr/bin/xterm 'exit 0';           mkpk xterm 410-r0 libxfake
script jwm /usr/bin/jwm 'exit 0';               mkpk jwm 2.4.6-r2 libxfake librsvgfake
script svkbd /usr/bin/svkbd-mobile-intl 'exit 0'; script svkbd /usr/bin/svkbd-mobile 'exit 0'; mkpk svkbd 0.4.2-r0 libxfake
script matchbox-keyboard /usr/bin/matchbox-keyboard 'exit 0'; mkpk matchbox-keyboard 0.1.1-r0 libxfake
script xinput /usr/bin/xinput 'exit 0';         mkpk xinput 1.6.4-r1 libxfake
# a fake tcc: "tcc -shared -nostdlib -o OUT SRC" copies the prebuilt x86 shim
script tcc /usr/bin/tcc '[ -e /tmp/tcc-fail ] && { echo "tcc: broken" >&2; exit 1; }; out=; while [ $# -gt 0 ]; do [ "$1" = -o ] && { out=$2; shift; }; shift; done; [ -n "$out" ] && cp /opt/z380m-fbfix-test.so "$out"'
mkpk tcc 0.9.27_git20250619-r1
apk --allow-untrusted mkndx -o /repo3/packages.adb /repo3/*.apk
echo "repo3 built: $(ls /repo3 | wc -l) files"
