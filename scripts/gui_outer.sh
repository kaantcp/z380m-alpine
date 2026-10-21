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

# test rig only: runs inside throw-away mount/uts/pid namespaces (made by test_gui.py with unshare).
# usage: gui_outer.sh <rootfs> <pty-slave-path>
R=$1
SLAVE=$2
set -e
mkdir -p "$R/dev" "$R/proc" "$R/run" "$R/var/log"
touch "$R/dev/ttyGS0"
mount --bind "$SLAVE" "$R/dev/ttyGS0"
# a real /dev/null inside the rig (it was a plain file, which also made the bind mounts below plain files)
touch "$R/dev/null"
mount --bind /dev/null "$R/dev/null"
# a /dev/tty1 (character device) but no /dev/tty0, like a kernel where only the numbered consoles exist
rm -f "$R/dev/tty0"
touch "$R/dev/tty1"
mount --bind /dev/null "$R/dev/tty1"
mount -t proc proc "$R/proc"
hostname z380m
exec chroot "$R" /bin/sh /tmp/gui_inner.sh
