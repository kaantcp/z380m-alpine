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

const char z380m_credit_xorg_stub[] = "z380m-alpine by kaantcp - https://github.com/kaantcp";

/* test rig only: stands in for Xorg. Creates the X0 unix socket, logs its arguments, exits on SIGTERM.
   If /tmp/xorg-fail exists it exits at once with status 1 (a server that cannot start). */
#define _GNU_SOURCE
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

static void logmsg(const char *m)
{
    FILE *f = fopen("/tmp/stub.log", "a");
    if (f) { fprintf(f, "%s\n", m); fclose(f); }
}

static void on_term(int s)
{
    (void)s;
    logmsg("Xorg stub: SIGTERM, exiting");
    unlink("/tmp/.X11-unix/X0");
    _exit(0);
}

int main(int argc, char **argv)
{
    char line[1024] = "Xorg stub: start";
    int i;
    for (i = 1; i < argc; i++) { strncat(line, " ", sizeof line - strlen(line) - 1); strncat(line, argv[i], sizeof line - strlen(line) - 1); }
    logmsg(line);
    {
        char env[600];
        const char *pre = getenv("LD_PRELOAD");
        snprintf(env, sizeof env, "Xorg stub: env LD_PRELOAD=[%s]", pre ? pre : "(unset)");
        logmsg(env);
    }
    if (access("/tmp/xorg-fail", F_OK) == 0) { logmsg("Xorg stub: failing on purpose"); return 1; }
    signal(SIGTERM, on_term);
    mkdir("/tmp/.X11-unix", 01777);
    int s = socket(AF_UNIX, SOCK_STREAM, 0);
    struct sockaddr_un a;
    memset(&a, 0, sizeof a);
    a.sun_family = AF_UNIX;
    strcpy(a.sun_path, "/tmp/.X11-unix/X0");
    unlink(a.sun_path);
    if (bind(s, (struct sockaddr *)&a, sizeof a) != 0) { logmsg("Xorg stub: bind failed"); return 2; }
    listen(s, 1);
    for (;;) pause();
}
