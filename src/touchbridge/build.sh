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

# Build the aarch64 touch bridge (a static, libc-free program) from z380m-touchbridge.c.
#
# usage: sh build.sh [output-file]        default output: z380m-touchbridge.arm64 next to this script
#
# Needs: clang and lld (Ubuntu: sudo apt install clang lld). No aarch64 libc or cross gcc is needed
# because the program makes its own system calls.
# The program that was tested on the tablet (and is stored in installer/touchfix/) came from this exact command;
# build.sh followed by "cmp" against installer/touchfix/z380m-touchbridge.arm64 shows whether your toolchain
# reproduces it byte for byte (it did with Ubuntu clang 18.1.3 / LLD 18.1.3).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${1:-$HERE/z380m-touchbridge.arm64}
exec clang --target=aarch64-linux-gnu -Wall -Wextra -Os \
  -ffreestanding -fno-builtin -fno-stack-protector -fno-pic -fno-pie \
  -fno-asynchronous-unwind-tables -fno-unwind-tables \
  -nostdlib -static -fuse-ld=lld \
  -Wl,-e,_start -Wl,--build-id=none -Wl,-z,max-page-size=4096 -Wl,-z,norelro -Wl,-z,noseparate-code \
  -Wl,--gc-sections -Wl,-s \
  -o "$OUT" "$HERE/z380m-touchbridge.c"
