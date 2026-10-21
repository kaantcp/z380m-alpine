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

const char z380m_credit_term_stub[] = "z380m-alpine by kaantcp - https://github.com/kaantcp";

/* test rig only: stands in for z380term. Starts a shell on the serial line, logs, dies cleanly on SIGTERM. */
#define _GNU_SOURCE
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/wait.h>
#include <unistd.h>

static pid_t child;

static void logmsg(const char *m)
{
    FILE *f = fopen("/tmp/stub.log", "a");
    if (f) { fprintf(f, "%s\n", m); fclose(f); }
}

static void on_term(int s)
{
    (void)s;
    if (child > 0) kill(child, SIGKILL);
    logmsg("z380term stub: SIGTERM, exiting");
    _exit(0);
}

int main(int argc, char **argv)
{
    const char *ser = NULL;
    char *shell[8];
    int i, n = 0, after = 0;
    for (i = 1; i < argc; i++) {
        if (!after && !strcmp(argv[i], "-s") && i + 1 < argc) ser = argv[++i];
        else if (!after && !strcmp(argv[i], "--")) after = 1;
        else if (after && n < 7) shell[n++] = argv[i];
    }
    shell[n] = NULL;
    logmsg("z380term stub: start");
    signal(SIGTERM, on_term);
    child = fork();
    if (child == 0) {
        setsid();
        if (ser) {
            int fd = open(ser, O_RDWR);
            if (fd >= 0) {
                ioctl(fd, TIOCSCTTY, 0);
                dup2(fd, 0); dup2(fd, 1); dup2(fd, 2);
            }
        }
        if (n) execv(shell[0], shell);
        _exit(127);
    }
    waitpid(child, NULL, 0);
    logmsg("z380term stub: shell ended");
    return 0;
}
