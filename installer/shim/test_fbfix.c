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

const char z380m_credit_fbfix_test[] = "z380m-alpine by kaantcp - https://github.com/kaantcp";

/* host test for fbfix.c: a fake kernel (syscall) behind the shim */
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
extern int ioctl(int, int, void *);
#if defined(__x86_64__)
#define NR 16
#else
#define NR 29
#endif
static unsigned kvar[40];          /* "the kernel's" fb_var_screeninfo */
static unsigned last_put[40];
static int npass;
long syscall(long n, ...)
{
    va_list ap; int fd, req; void *arg;
    va_start(ap, n); fd = va_arg(ap, int); req = va_arg(ap, int); arg = va_arg(ap, void *); va_end(ap);
    (void)fd;
    if (n != NR) return -1;
    if (!arg && req != 0x1234) return -1;
    if (req == 0x4600) { memcpy(arg, kvar, sizeof kvar); return 0; }
    if (req == 0x4601) { memcpy(last_put, arg, sizeof kvar); ((unsigned *)arg)[3] = 1280;   /* kernel adjusts yres_virtual */ memcpy(kvar, arg, sizeof kvar); return 0; }
    if (req == 0x4606) { memcpy(last_put, arg, sizeof kvar); return 0; }
    if (req == 0x1234) { npass++; return 42; }
    return -1;
}
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); bad++; } } while (0)
int main(void)
{
    unsigned v[40]; int bad = 0, r;
    memset(kvar, 0, sizeof kvar);
    kvar[0] = 800; kvar[1] = 1280; kvar[3] = 3840; kvar[6] = 32;
    kvar[8] = 0;  kvar[9] = 8;  kvar[11] = 8; kvar[12] = 8; kvar[14] = 16; kvar[15] = 8; kvar[17] = 24; kvar[18] = 8;   /* rgba 8/0,8/8,8/16,8/24 */
    /* GET: X sees red at 16 and blue at 0, everything else unchanged */
    memset(v, 0xee, sizeof v);
    r = ioctl(3, 0x4600, v);
    CHECK(r == 0); CHECK(v[8] == 16 && v[14] == 0); CHECK(v[9] == 8 && v[15] == 8 && v[11] == 8 && v[17] == 24); CHECK(v[0] == 800 && v[3] == 3840);
    CHECK(kvar[8] == 0 && kvar[14] == 16);                     /* the kernel's own data is untouched */
    /* PUT with X's view: the kernel must receive the original layout; the answer comes back in X's view */
    v[2] = 800; v[3] = 1280;
    r = ioctl(3, 0x4601, v);
    CHECK(r == 0); CHECK(last_put[8] == 0 && last_put[14] == 16); CHECK(last_put[3] == 1280);
    CHECK(v[8] == 16 && v[14] == 0);                           /* caller still sees swapped offsets */
    CHECK(kvar[8] == 0 && kvar[14] == 16);
    /* PAN: swapped back for the kernel, caller's struct left alone */
    v[8] = 16; v[14] = 0; v[5] = 0;
    r = ioctl(3, 0x4606, v);
    CHECK(r == 0); CHECK(last_put[8] == 0 && last_put[14] == 16); CHECK(v[8] == 16 && v[14] == 0);
    /* other requests and a NULL argument pass straight through */
    r = ioctl(3, 0x1234, (void *)0); CHECK(r == 42 && npass == 1);
    r = ioctl(3, 0x4600, (void *)0); CHECK(r == -1);
    printf(bad ? "TEST FAILED (%d)\n" : "fbfix host test: all checks passed\n", bad);
    return bad ? 1 : 0;
}
