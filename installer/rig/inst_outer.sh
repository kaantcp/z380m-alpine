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

# test rig only: runs inside throw-away mount/uts/pid namespaces (made with unshare).
# usage: inst_outer.sh <rootfs> <scenario-env-file-inside-rootfs>
R=$1
ENVF=$2
set -e
mkdir -p "$R/dev" "$R/proc" "$R/run" "$R/var/log"
touch "$R/dev/null" "$R/dev/fb0"
mount --bind /dev/null "$R/dev/null"
mount --bind /dev/null "$R/dev/fb0"
mount -t proc proc "$R/proc"
hostname "$(grep '^HOSTNAME=' "$R$ENVF" | cut -d= -f2)"
exec chroot "$R" /bin/sh /tmp/inst_inner.sh "$ENVF"
