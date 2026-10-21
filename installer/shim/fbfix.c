/*
 * SPDX-License-Identifier: GPL-3.0-only
 * Copyright (C) 2026 kaantcp (https://github.com/kaantcp)
 *
 * Part of z380m-alpine: Alpine Linux on the ASUS ZenPad 8.0 (Z380M, MT8163).
 *
 * This program is free software: you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation, version 3 of the License.
 *
 * This program is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
 * or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
 * for more details. You should have received a copy of the GNU General
 * Public License along with this program (file LICENSE). If not, see
 * <https://www.gnu.org/licenses/>.
 */

const char z380m_credit_fbfix[] = "z380m-alpine by kaantcp - https://github.com/kaantcp";

/* z380m-fbfix: an LD_PRELOAD shim for Xorg's fbdev driver on the Z380M (mtkfb).
 *
 * The panel shows red and blue swapped relative to what mtkfb reports in fb_var_screeninfo (red.offset 0, blue.offset 16),
 * and X takes its pixel format from that report. This library swaps the two offsets in what X sees (FBIOGET_VSCREENINFO) and
 * swaps them back before the kernel sees them (FBIOPUT_VSCREENINFO, FBIOPAN_DISPLAY), so the kernel is told exactly what it is
 * told without X, while X puts the red channel where the panel expects it.
 * It has no library dependencies except syscall() from libc, so it builds with tcc -shared -nostdlib.
 */
#if defined(__aarch64__)
#define NR_IOCTL 29
#elif defined(__x86_64__)
#define NR_IOCTL 16
#elif defined(__arm__)
#define NR_IOCTL 54
#else
#error "unknown architecture"
#endif

extern long syscall(long, ...);

#define FBIOGET_VSCREENINFO 0x4600
#define FBIOPUT_VSCREENINFO 0x4601
#define FBIOPAN_DISPLAY     0x4606

/* struct fb_var_screeninfo is 40 32-bit words; red.offset is word 8 and blue.offset is word 14 */
#define VAR_WORDS 40
#define RED_OFFSET 8
#define BLUE_OFFSET 14

static void swap_rb(unsigned *w)
{
    unsigned t = w[RED_OFFSET];
    w[RED_OFFSET] = w[BLUE_OFFSET];
    w[BLUE_OFFSET] = t;
}

int ioctl(int fd, int req, void *arg)
{
    unsigned w[VAR_WORDS];
    unsigned *p = (unsigned *)arg;
    long r;
    int i;

    if (p && req == FBIOGET_VSCREENINFO) {
        r = syscall(NR_IOCTL, fd, req, arg);
        if (r == 0)
            swap_rb(p);
        return (int)r;
    }
    if (p && (req == FBIOPUT_VSCREENINFO || req == FBIOPAN_DISPLAY)) {
        for (i = 0; i < VAR_WORDS; i++)
            w[i] = p[i];
        swap_rb(w);
        r = syscall(NR_IOCTL, fd, req, (void *)w);
        if (r == 0 && req == FBIOPUT_VSCREENINFO) {
            /* the kernel may have adjusted the values: give the caller the answer in its own (swapped) view */
            swap_rb(w);
            for (i = 0; i < VAR_WORDS; i++)
                p[i] = w[i];
        }
        return (int)r;
    }
    return (int)syscall(NR_IOCTL, fd, req, arg);
}
