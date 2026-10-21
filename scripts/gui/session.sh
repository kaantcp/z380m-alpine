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

# /etc/z380m/gui/session.sh - runs inside X (started by z380m-gui): background, keyboard layout, X resources, window manager.
# Put your own additions into /etc/z380m/gui/session.local (sourced just before the window manager starts).
export DISPLAY=:0 HOME=/root XDG_RUNTIME_DIR=/run/z380m-xdg LANG=C.UTF-8
mkdir -p "$XDG_RUNTIME_DIR" 2> /dev/null; chmod 700 "$XDG_RUNTIME_DIR" 2> /dev/null
echo "$Z380M_CREDIT"
xsetroot -solid '#1b2838' -cursor_name left_ptr
xset s off s noblank -dpms
setxkbmap us
[ -r /etc/z380m/gui/Xresources ] && xrdb -merge /etc/z380m/gui/Xresources
[ -r /etc/z380m/gui/session.local ] && . /etc/z380m/gui/session.local
# until the first "KEEP this desktop": a window with three colour bars, to see at once whether red and blue are swapped
if [ -e /etc/z380m/gui/first-run ] && command -v z380m-colortest > /dev/null 2>&1; then
  ( sleep 2; xterm -class ColorTest -title "Colour check" -e z380m-colortest > /dev/null 2>&1 ) &
fi
exec jwm -f /etc/z380m/gui/jwmrc
