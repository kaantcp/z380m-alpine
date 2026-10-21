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

# rig only: one install run in a fresh copy, output shown as the user would see it
SCR=$1; B=$SCR/rootfs_inst_base; R=$SCR/rootfs_inst_show
rm -rf $R; cp -a $B $R; mkdir -p $R/tmp/zgui
grep -v '^#' $SCR/installer/payload.list | while read src name; do [ -n "$src" ] && cp $SCR/$src $R/tmp/zgui/$name; done
printf 'HOSTNAME=z380m\nMODE=%s\nTTY0=1\nDRIVERS=/tmp/drivers-vt\nINPUTS=/tmp/inputs-touch\n' "${2:-install}" > $R/tmp/scn.env
cp $SCR/installer/rig/inst_inner.sh $R/tmp/inst_inner.sh
unshare --mount --uts --pid --fork bash $SCR/installer/rig/inst_outer.sh $R /tmp/scn.env 2>&1
