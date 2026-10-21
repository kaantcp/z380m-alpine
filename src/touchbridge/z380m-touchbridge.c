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

/*
 * z380m-touchbridge - the ZenPad's touch panel as an ordinary single-touch screen.
 *
 * Why: the panel (elan-touchscreen, /dev/input/event11) reports only the multitouch protocol (ABS_MT_*): no BTN_TOUCH, no
 * ABS_X/ABS_Y. Xorg's evdev driver does not turn such a device into pointer events and clicks. This program reads the real
 * panel and creates a virtual touch screen through /dev/uinput that reports the FIRST finger as ABS_X, ABS_Y and BTN_TOUCH.
 * Xorg then uses the virtual device like any old touch screen (z380m-gui makes /dev/input/z380m-touch point at it).
 *
 * usage:
 *   z380m-touchbridge run   [-i /dev/input/eventN] [-x] [-y] [-v]    the bridge; stays in the foreground
 *   z380m-touchbridge probe [-i /dev/input/eventN] [-t SECONDS]      show what the panel sends; writes nothing anywhere
 *   z380m-touchbridge check                                          make a virtual device and remove it again
 *   z380m-touchbridge version
 *     -x / -y   mirror the horizontal / vertical axis
 *
 * Details:
 *  - Kernel 3.18 has no UI_DEV_SETUP, so the old uinput interface is used (write a struct uinput_user_dev, then UI_DEV_CREATE).
 *  - Handles multitouch type B (slots, tracking ids) and type A (SYN_MT_REPORT). The first finger that touches is followed
 *    until it lifts; other fingers are ignored until every finger has lifted (no jumping pointer, no ghost clicks).
 *  - No libc: raw Linux syscalls, so it builds with "clang --target=aarch64-linux-gnu -ffreestanding -nostdlib -static".
 *    TESTBUILD (host libc, x86_64) exists only for the tests; it can also read a file instead of a device (-i) and write the
 *    generated events to a file instead of /dev/uinput (-o).
 * Nothing here writes to flash or touches any partition.
 */

#ifdef TESTBUILD
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>
#endif

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef int s32;
typedef long s64;

#define VERSION "z380m-touchbridge 1"
#define CREDIT_LINE VERSION " by kaantcp - https://github.com/kaantcp"
const char z380m_credit_touchbridge[] = CREDIT_LINE;

/* ---- linux/input.h and linux/uinput.h, as far as needed (values are the same on aarch64 and x86_64) ---- */
#define EV_SYN 0
#define EV_KEY 1
#define EV_ABS 3
#define SYN_REPORT 0
#define SYN_MT_REPORT 2
#define SYN_DROPPED 3
#define BTN_TOUCH 0x14a
#define ABS_X 0
#define ABS_Y 1
#define ABS_MT_SLOT 0x2f
#define ABS_MT_POSITION_X 0x35
#define ABS_MT_POSITION_Y 0x36
#define ABS_MT_TRACKING_ID 0x39
#define INPUT_PROP_DIRECT 1
#define BUS_VIRTUAL 6

#define EVIOCGABS(a) (0x80184540UL + (a))        /* _IOR('E', 0x40 + a, struct input_absinfo): 24 bytes */
#define UI_DEV_CREATE 0x5501UL                   /* _IO('U', 1) */
#define UI_DEV_DESTROY 0x5502UL                  /* _IO('U', 2) */
#define UI_SET_EVBIT 0x40045564UL                /* _IOW('U', 100, int) */
#define UI_SET_KEYBIT 0x40045565UL               /* _IOW('U', 101, int) */
#define UI_SET_ABSBIT 0x40045567UL               /* _IOW('U', 103, int) */
#define UI_SET_PROPBIT 0x4004556eUL              /* _IOW('U', 110, int) */

#define O_RDONLY_ 0
#define O_WRONLY_ 1
#define O_RDWR_ 2
#define O_NONBLOCK_ 04000

struct input_event {              /* 64-bit layout: 24 bytes */
    s64 sec;
    s64 usec;
    u16 type;
    u16 code;
    s32 value;
};

struct input_absinfo {
    s32 value, minimum, maximum, fuzz, flat, resolution;
};

#define ABS_CNT 64
struct uinput_user_dev {          /* 80 + 8 + 4 + 4 * 256 = 1116 bytes */
    char name[80];
    u16 bustype, vendor, product, version;
    u32 ff_effects_max;
    s32 absmax[ABS_CNT];
    s32 absmin[ABS_CNT];
    s32 absfuzz[ABS_CNT];
    s32 absflat[ABS_CNT];
};

_Static_assert(sizeof(struct input_event) == 24, "input_event must be 24 bytes (64-bit)");
_Static_assert(sizeof(struct input_absinfo) == 24, "input_absinfo must be 24 bytes");
_Static_assert(sizeof(struct uinput_user_dev) == 1116, "uinput_user_dev must be 1116 bytes");

/* ---- system calls ---- */
#ifdef TESTBUILD

static long sys_open(const char *p, int fl)
{
    /* test sink files are created; nothing below /dev/ ever is */
    int extra = ((fl & O_WRONLY) && strncmp(p, "/dev/", 5) != 0) ? (O_CREAT | O_TRUNC) : 0;
    int r = open(p, fl | extra, 0644);
    return r < 0 ? -errno : r;
}
static long sys_close(int fd) { int r = close(fd); return r < 0 ? -errno : r; }
static long sys_read(int fd, void *b, long n) { long r = read(fd, b, (size_t)n); return r < 0 ? -errno : r; }
static long sys_write(int fd, const void *b, long n) { long r = write(fd, b, (size_t)n); return r < 0 ? -errno : r; }
static long sys_ioctl(int fd, unsigned long rq, long arg) { int r = ioctl(fd, rq, arg); return r < 0 ? -errno : r; }
static long sys_wait_readable(int fd, long ms)   /* >0 readable (or error/hangup), 0 timeout, <0 error */
{
    struct pollfd p; int r;
    p.fd = fd; p.events = POLLIN; p.revents = 0;
    r = poll(&p, 1, (int)ms);
    return r < 0 ? -errno : r;
}
static long now_ms(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return (long)t.tv_sec * 1000 + t.tv_nsec / 1000000; }
static void sleep_ms(long ms) { struct timespec t; t.tv_sec = ms / 1000; t.tv_nsec = (ms % 1000) * 1000000L; nanosleep(&t, 0); }
static void sys_exit(int c) __attribute__((unused));
static void sys_exit(int c) { _exit(c); }

#else

#if !defined(__aarch64__)
#error "the freestanding build is for aarch64 (use -DTESTBUILD for the host test build)"
#endif
#define NR_ioctl 29
#define NR_openat 56
#define NR_close 57
#define NR_read 63
#define NR_write 64
#define NR_ppoll 73
#define NR_exit_group 94
#define NR_nanosleep 101
#define NR_clock_gettime 113

static inline long sc(long nr, long a, long b, long c, long d, long e)
{
    register long x8 __asm__("x8") = nr;
    register long x0 __asm__("x0") = a;
    register long x1 __asm__("x1") = b;
    register long x2 __asm__("x2") = c;
    register long x3 __asm__("x3") = d;
    register long x4 __asm__("x4") = e;
    __asm__ volatile("svc #0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2), "r"(x3), "r"(x4) : "memory", "cc");
    return x0;
}

struct ts_ { long s; long ns; };
struct pollfd_ { int fd; short events; short revents; };

static long sys_open(const char *p, int fl) { return sc(NR_openat, -100, (long)p, fl, 0, 0); }
static long sys_close(int fd) { return sc(NR_close, fd, 0, 0, 0, 0); }
static long sys_read(int fd, void *b, long n) { return sc(NR_read, fd, (long)b, n, 0, 0); }
static long sys_write(int fd, const void *b, long n) { return sc(NR_write, fd, (long)b, n, 0, 0); }
static long sys_ioctl(int fd, unsigned long rq, long arg) { return sc(NR_ioctl, fd, (long)rq, arg, 0, 0); }
static long sys_wait_readable(int fd, long ms)
{
    struct pollfd_ p;
    struct ts_ t;
    p.fd = fd; p.events = 1; p.revents = 0;
    t.s = ms / 1000; t.ns = (ms % 1000) * 1000000L;
    return sc(NR_ppoll, (long)&p, 1, (long)&t, 0, 8);
}
static long now_ms(void)
{
    struct ts_ t;
    t.s = 0; t.ns = 0;
    sc(NR_clock_gettime, 1, (long)&t, 0, 0, 0);
    return t.s * 1000 + t.ns / 1000000;
}
static void sleep_ms(long ms)
{
    struct ts_ t;
    t.s = ms / 1000; t.ns = (ms % 1000) * 1000000L;
    sc(NR_nanosleep, (long)&t, 0, 0, 0, 0);
}
static void sys_exit(int c) { for (;;) sc(NR_exit_group, c, 0, 0, 0, 0); }

#endif

/* ---- tiny output helpers ---- */
static long slen(const char *s) { long n = 0; while (s[n]) n++; return n; }
static void ps(int fd, const char *s) { sys_write(fd, s, slen(s)); }
static void pn(int fd, long v)
{
    char b[24];
    int i = 23;
    unsigned long u = v < 0 ? 0UL - (unsigned long)v : (unsigned long)v;
    b[i] = 0;
    do { b[--i] = (char)('0' + u % 10); u /= 10; } while (u && i > 1);
    if (v < 0) b[--i] = '-';
    sys_write(fd, b + i, 23 - i);
}
static void kv(int fd, const char *k, long v) { ps(fd, k); pn(fd, v); }
static int str_eq(const char *a, const char *b) { while (*a && *a == *b) { a++; b++; } return *a == *b; }
static long to_num(const char *s)
{
    long v = 0; int neg = 0;
    if (*s == '-') { neg = 1; s++; }
    while (*s >= '0' && *s <= '9') { v = v * 10 + (*s - '0'); s++; }
    return neg ? -v : v;
}

/* ---- the touch state machine ---- */
#define MAXSLOT 16
struct tstate {
    int slot;
    int tid[MAXSLOT];             /* tracking id of the finger in this slot, -1 = none */
    int px[MAXSLOT], py[MAXSLOT];
    int prim;                     /* slot followed as THE pointer, -1 = none */
    int blocked;                  /* the followed finger lifted while others are still down: wait until all are up */
    int typeB, typeA;
    int a_have_x, a_have_y, a_x, a_y;   /* type A: contact being collected */
    int a_n, a_fx, a_fy;                /* type A: contacts so far in this frame, position of the first */
    int down, ox, oy;                   /* what has been reported to the virtual device */
    int xmin, xmax, ymin, ymax, invx, invy;
};

static struct tstate S;

static void ts_reset_fingers(struct tstate *s)
{
    int i;
    for (i = 0; i < MAXSLOT; i++) s->tid[i] = -1;
    s->prim = -1;
    s->blocked = 0;
}

static void ts_init(struct tstate *s, int xmin, int xmax, int ymin, int ymax, int invx, int invy)
{
    int i;
    s->slot = 0;
    for (i = 0; i < MAXSLOT; i++) { s->px[i] = 0; s->py[i] = 0; }
    ts_reset_fingers(s);
    s->typeA = s->typeB = 0;
    s->a_have_x = s->a_have_y = s->a_x = s->a_y = 0;
    s->a_n = s->a_fx = s->a_fy = 0;
    s->down = s->ox = s->oy = 0;
    s->xmin = xmin; s->xmax = xmax; s->ymin = ymin; s->ymax = ymax;
    s->invx = invx; s->invy = invy;
}

/* one raw event in; returns 1 when it was a SYN_REPORT (the frame is complete) */
static int ts_event(struct tstate *s, int type, int code, int value)
{
    if (type == EV_ABS) {
        switch (code) {
        case ABS_MT_SLOT:
            s->typeB = 1;
            s->slot = (value < 0) ? 0 : (value >= MAXSLOT ? MAXSLOT - 1 : value);
            break;
        case ABS_MT_TRACKING_ID:
            s->typeB = 1;
            s->tid[s->slot] = (value < 0) ? -1 : value;
            break;
        case ABS_MT_POSITION_X:
            s->px[s->slot] = value; s->a_x = value; s->a_have_x = 1;
            break;
        case ABS_MT_POSITION_Y:
            s->py[s->slot] = value; s->a_y = value; s->a_have_y = 1;
            break;
        default:
            break;
        }
        return 0;
    }
    if (type == EV_SYN) {
        if (code == SYN_MT_REPORT) {
            s->typeA = 1;
            if (s->a_have_x && s->a_have_y) {
                if (s->a_n == 0) { s->a_fx = s->a_x; s->a_fy = s->a_y; }
                s->a_n++;
            }
            s->a_have_x = s->a_have_y = 0;
            return 0;
        }
        if (code == SYN_DROPPED) {            /* events were lost: forget the fingers, they are picked up again at the next touch */
            ts_reset_fingers(s);
            s->a_n = 0; s->a_have_x = s->a_have_y = 0;
            return 0;
        }
        if (code == SYN_REPORT) return 1;
    }
    return 0;
}

/* at a SYN_REPORT: is there a pointer finger, and where? */
static int ts_decide(struct tstate *s, int *x, int *y)
{
    int i, any;
    if (s->typeA) {
        if (s->a_n > 0) { *x = s->a_fx; *y = s->a_fy; return 1; }
        return 0;
    }
    if (s->prim >= 0 && s->tid[s->prim] < 0) { s->prim = -1; s->blocked = 1; }
    if (s->prim < 0) {
        any = 0;
        for (i = 0; i < MAXSLOT; i++) if (s->tid[i] >= 0) { any = 1; break; }
        if (!any) s->blocked = 0;
        if (any && !s->blocked) {
            for (i = 0; i < MAXSLOT; i++) if (s->tid[i] >= 0) { s->prim = i; break; }
        }
    }
    if (s->prim >= 0) { *x = s->px[s->prim]; *y = s->py[s->prim]; return 1; }
    return 0;
}

static void ts_end_frame(struct tstate *s)
{
    s->a_n = 0; s->a_have_x = s->a_have_y = 0;
}

/* ---- output: events for the virtual device ---- */
static struct input_event OB[8];
static int on;

static void ev_put(int type, int code, int value)
{
    struct input_event *e = &OB[on++];
    e->sec = 0; e->usec = 0;
    e->type = (u16)type; e->code = (u16)code; e->value = value;
}

static int out_flush(int ofd)
{
    long r;
    if (on == 0) return 0;
    r = sys_write(ofd, OB, (long)on * (long)sizeof(struct input_event));
    on = 0;
    return r < 0 ? (int)r : 0;
}

/* turn the finished frame into events; returns the number of events queued (0 = nothing changed) */
static int ts_emit(struct tstate *s)
{
    int x = 0, y = 0, act;
    act = ts_decide(s, &x, &y);
    on = 0;
    if (act) {
        if (s->invx) x = s->xmin + s->xmax - x;
        if (s->invy) y = s->ymin + s->ymax - y;
        if (x < s->xmin) x = s->xmin;
        if (x > s->xmax) x = s->xmax;
        if (y < s->ymin) y = s->ymin;
        if (y > s->ymax) y = s->ymax;
        if (!s->down) {
            ev_put(EV_ABS, ABS_X, x); ev_put(EV_ABS, ABS_Y, y); ev_put(EV_KEY, BTN_TOUCH, 1);
            s->down = 1; s->ox = x; s->oy = y;
        } else {
            if (x != s->ox) { ev_put(EV_ABS, ABS_X, x); s->ox = x; }
            if (y != s->oy) { ev_put(EV_ABS, ABS_Y, y); s->oy = y; }
        }
    } else if (s->down) {
        ev_put(EV_KEY, BTN_TOUCH, 0);
        s->down = 0;
    }
    if (on) ev_put(EV_SYN, SYN_REPORT, 0);
    return on;
}

/* ---- the virtual device ---- */
static struct uinput_user_dev UD;

static void name_copy(char *d, const char *s, int max) { int i = 0; while (s[i] && i < max - 1) { d[i] = s[i]; i++; } d[i] = 0; }

static void fail(const char *what, long err)
{
    ps(2, "z380m-touchbridge: "); ps(2, what); ps(2, " failed (errno "); pn(2, -err); ps(2, ")\n");
}

static long uinput_create(int xmin, int xmax, int ymin, int ymax)
{
    static const char *paths[3] = { "/dev/uinput", "/dev/input/uinput", "/dev/misc/uinput" };
    long fd = -2, r, err = 0;
    int i;
    for (i = 0; i < 3; i++) {
        fd = sys_open(paths[i], O_WRONLY_ | O_NONBLOCK_);
        if (fd >= 0) break;
        if (fd != -2 || err == 0) err = fd;          /* a real error beats "no such file" */
    }
    if (fd < 0) { fail("open /dev/uinput", err); return -1; }
    if ((r = sys_ioctl((int)fd, UI_SET_EVBIT, EV_KEY)) < 0) { fail("UI_SET_EVBIT EV_KEY", r); return -1; }
    if ((r = sys_ioctl((int)fd, UI_SET_KEYBIT, BTN_TOUCH)) < 0) { fail("UI_SET_KEYBIT BTN_TOUCH", r); return -1; }
    if ((r = sys_ioctl((int)fd, UI_SET_EVBIT, EV_ABS)) < 0) { fail("UI_SET_EVBIT EV_ABS", r); return -1; }
    if ((r = sys_ioctl((int)fd, UI_SET_ABSBIT, ABS_X)) < 0) { fail("UI_SET_ABSBIT ABS_X", r); return -1; }
    if ((r = sys_ioctl((int)fd, UI_SET_ABSBIT, ABS_Y)) < 0) { fail("UI_SET_ABSBIT ABS_Y", r); return -1; }
    sys_ioctl((int)fd, UI_SET_PROPBIT, INPUT_PROP_DIRECT);          /* nice to have, not essential */
    name_copy(UD.name, "z380m-virtual-touch", 80);
    UD.bustype = BUS_VIRTUAL; UD.vendor = 0x380; UD.product = 0x8163; UD.version = 1;
    UD.absmin[ABS_X] = xmin; UD.absmax[ABS_X] = xmax;
    UD.absmin[ABS_Y] = ymin; UD.absmax[ABS_Y] = ymax;
    r = sys_write((int)fd, &UD, (long)sizeof UD);
    if (r != (long)sizeof UD) { fail("writing the device description", r < 0 ? r : -5); return -1; }
    if ((r = sys_ioctl((int)fd, UI_DEV_CREATE, 0)) < 0) { fail("UI_DEV_CREATE", r); return -1; }
    return fd;
}

/* ---- commands ---- */
static void get_range(long rfd, int *lo, int *hi, int code, int dlo, int dhi)
{
    struct input_absinfo absinfo;
    absinfo.minimum = 0; absinfo.maximum = 0;
    if (sys_ioctl((int)rfd, EVIOCGABS(code), (long)&absinfo) == 0 && absinfo.maximum > absinfo.minimum) { *lo = absinfo.minimum; *hi = absinfo.maximum; }
    else { *lo = dlo; *hi = dhi; }
}

static struct input_event IB[64];

static int cmd_run(const char *dev, int invx, int invy, int verbose, const char *sink)
{
    long rfd, ofd, n, carry = 0;
    int xmin, xmax, ymin, ymax, nf = 0;
    char *bp;
    long i, cnt;

    rfd = sys_open(dev, O_RDONLY_);
    if (rfd < 0) { ps(2, "z380m-touchbridge: cannot open "); ps(2, dev); ps(2, ": "); fail("open", rfd); return 1; }
    get_range(rfd, &xmin, &xmax, ABS_MT_POSITION_X, 0, 1472);
    get_range(rfd, &ymin, &ymax, ABS_MT_POSITION_Y, 0, 2368);
    ts_init(&S, xmin, xmax, ymin, ymax, invx, invy);

    if (sink) {
        ofd = sys_open(sink, O_WRONLY_);
        if (ofd < 0) { fail("open sink", ofd); return 1; }
    } else {
        ofd = uinput_create(xmin, xmax, ymin, ymax);
        if (ofd < 0) return 1;
    }
    ps(2, "z380m-touchbridge: "); ps(2, dev); kv(2, " -> virtual touch screen, x ", xmin); kv(2, "..", xmax);
    kv(2, " y ", ymin); kv(2, "..", ymax); if (invx) ps(2, " mirror-x"); if (invy) ps(2, " mirror-y"); ps(2, "\n");

    bp = (char *)IB;
    for (;;) {
        n = sys_read((int)rfd, bp + carry, (long)sizeof IB - carry);
        if (n == -4 || n == -11) continue;                       /* EINTR, EAGAIN */
        if (n < 0) { fail("read", n); break; }
        if (n == 0) break;                                       /* end of file (tests only) */
        cnt = (carry + n) / (long)sizeof(struct input_event);
        for (i = 0; i < cnt; i++) {
            struct input_event *e = &IB[i];
            if (ts_event(&S, e->type, e->code, e->value)) {
                if (ts_emit(&S)) {
                    if (verbose && nf < 300) {
                        nf++;
                        ps(2, "frame: "); kv(2, "down=", S.down); kv(2, " x=", S.ox); kv(2, " y=", S.oy); ps(2, "\n");
                    }
                    if (out_flush((int)ofd) < 0) { fail("writing to the virtual device", -5); }
                }
                ts_end_frame(&S);
            }
        }
        /* keep an incomplete trailing record (cannot happen on a real device) */
        carry = (carry + n) - cnt * (long)sizeof(struct input_event);
        if (carry > 0) { long k; char *src = bp + cnt * (long)sizeof(struct input_event); for (k = 0; k < carry; k++) bp[k] = src[k]; }
    }
    if (!sink) sys_ioctl((int)ofd, UI_DEV_DESTROY, 0);
    sys_close((int)ofd);
    sys_close((int)rfd);
    return 0;
}

static int cmd_probe(const char *dev, long seconds)
{
    long rfd, deadline, rem, r, n, i, cnt;
    int xmin, xmax, ymin, ymax, frames = 0, nabs = 0, nkey = 0, nsyn = 0, ntid = 0, nslot = 0, nmt = 0, nbtn = 0;
    int minx = 0, maxx = 0, miny = 0, maxy = 0, firstx = 0, firsty = 0, lastx = 0, lasty = 0;
    long sumx = 0, sumy = 0;
    long total = 0;

    rfd = sys_open(dev, O_RDONLY_ | O_NONBLOCK_);
    if (rfd < 0) { ps(2, "z380m-touchbridge: cannot open "); ps(2, dev); ps(2, ": "); fail("open", rfd); return 1; }
    get_range(rfd, &xmin, &xmax, ABS_MT_POSITION_X, 0, 1472);
    get_range(rfd, &ymin, &ymax, ABS_MT_POSITION_Y, 0, 2368);
    ts_init(&S, xmin, xmax, ymin, ymax, 0, 0);
    deadline = now_ms() + seconds * 1000;
    for (;;) {
        rem = deadline - now_ms();
        if (rem <= 0) break;
        r = sys_wait_readable((int)rfd, rem);
        if (r < 0) { if (r == -4) continue; fail("poll", r); break; }
        if (r == 0) break;
        n = sys_read((int)rfd, IB, (long)sizeof IB);
        if (n == -11 || n == -4) continue;
        if (n < 0) { fail("read", n); break; }
        if (n == 0) break;                                       /* end of file (tests only) */
        cnt = n / (long)sizeof(struct input_event);
        for (i = 0; i < cnt; i++) {
            struct input_event *e = &IB[i];
            int x, y, act;
            total++;
            if (e->type == EV_ABS) {
                nabs++;
                if (e->code == ABS_MT_TRACKING_ID) ntid++;
                else if (e->code == ABS_MT_SLOT) nslot++;
            } else if (e->type == EV_KEY) { nkey++; if (e->code == BTN_TOUCH) nbtn++; }
            else if (e->type == EV_SYN) { nsyn++; if (e->code == SYN_MT_REPORT) nmt++; }
            if (ts_event(&S, e->type, e->code, e->value)) {
                act = ts_decide(&S, &x, &y);
                if (act) {
                    if (frames == 0) { firstx = x; firsty = y; minx = maxx = x; miny = maxy = y; }
                    if (x < minx) minx = x;
                    if (x > maxx) maxx = x;
                    if (y < miny) miny = y;
                    if (y > maxy) maxy = y;
                    lastx = x; lasty = y; sumx += x; sumy += y; frames++;
                }
                ts_end_frame(&S);
            }
        }
    }
    sys_close((int)rfd);

    ps(1, "probe: device "); ps(1, dev); kv(1, ", seconds ", seconds); ps(1, "\n");
    kv(1, "probe: events ", total); kv(1, " (abs ", nabs); kv(1, ", key ", nkey); kv(1, ", syn ", nsyn); ps(1, ")\n");
    ps(1, "probe: type B markers: tracking-id events "); pn(1, ntid); kv(1, ", slot events ", nslot);
    kv(1, "; type A: SYN_MT_REPORT ", nmt); kv(1, "; BTN_TOUCH events ", nbtn); ps(1, "\n");
    kv(1, "probe: panel range x ", xmin); kv(1, "..", xmax); kv(1, "  y ", ymin); kv(1, "..", ymax); ps(1, "\n");
    if (frames) {
        kv(1, "probe: finger down in ", frames); kv(1, " frames; first x=", firstx); kv(1, " y=", firsty);
        kv(1, "; last x=", lastx); kv(1, " y=", lasty); ps(1, "\n");
        kv(1, "probe: x ", minx); kv(1, "..", maxx); kv(1, "  y ", miny); kv(1, "..", maxy); ps(1, "\n");
    } else {
        ps(1, "probe: no finger seen\n");
    }
    ps(1, "RESULT");
    kv(1, " frames=", frames);
    kv(1, " avgx=", frames ? sumx / frames : 0);
    kv(1, " avgy=", frames ? sumy / frames : 0);
    kv(1, " minx=", minx); kv(1, " maxx=", maxx); kv(1, " miny=", miny); kv(1, " maxy=", maxy);
    kv(1, " xmax=", xmax); kv(1, " ymax=", ymax);
    kv(1, " events=", total);
    ps(1, "\n");
    return 0;
}

static int cmd_check(void)
{
    long fd = uinput_create(0, 100, 0, 100);
    if (fd < 0) return 1;
    sleep_ms(300);
    sys_ioctl((int)fd, UI_DEV_DESTROY, 0);
    sys_close((int)fd);
    ps(1, "uinput ok: a virtual touch screen was created and removed\n");
    return 0;
}

static int app_main(int argc, char **argv)
{
    const char *cmd = argc > 1 ? argv[1] : "help";
    const char *dev = "/dev/input/event11";
    const char *sink = 0;
    long secs = 6;
    int invx = 0, invy = 0, verbose = 0, i;

    for (i = 2; i < argc; i++) {
        if (str_eq(argv[i], "-i") && i + 1 < argc) dev = argv[++i];
        else if (str_eq(argv[i], "-t") && i + 1 < argc) { secs = to_num(argv[++i]); if (secs < 1) secs = 1; if (secs > 120) secs = 120; }
        else if (str_eq(argv[i], "-x")) invx = 1;
        else if (str_eq(argv[i], "-y")) invy = 1;
        else if (str_eq(argv[i], "-v")) verbose = 1;
#ifdef TESTBUILD
        else if (str_eq(argv[i], "-o") && i + 1 < argc) sink = argv[++i];
#endif
        else { ps(2, "z380m-touchbridge: unknown option "); ps(2, argv[i]); ps(2, "\n"); return 2; }
    }
    if (str_eq(cmd, "run")) return cmd_run(dev, invx, invy, verbose, sink);
    if (str_eq(cmd, "probe")) return cmd_probe(dev, secs);
    if (str_eq(cmd, "check")) return cmd_check();
    if (str_eq(cmd, "version")) { ps(1, z380m_credit_touchbridge); ps(1, "\n"); return 0; }
    ps(1, z380m_credit_touchbridge); ps(1, "\nusage: z380m-touchbridge run [-i DEV] [-x] [-y] [-v] | probe [-i DEV] [-t SECONDS] | check | version\n");
    return str_eq(cmd, "help") ? 0 : 2;
}

#ifdef TESTBUILD
int main(int argc, char **argv) { return app_main(argc, argv); }
#else
void c_main(long *sp) __attribute__((noreturn, used));
void c_main(long *sp)
{
    int argc = (int)sp[0];
    char **argv = (char **)(sp + 1);
    sys_exit(app_main(argc, argv));
    for (;;) { }
}

__attribute__((naked, noreturn, used)) void _start(void)
{
    __asm__ volatile("mov x0, sp\n\tbl c_main\n\tbrk #0\n");
}
#endif
