Copyright (C) 2026 kaantcp (https://github.com/kaantcp) - GPL-3.0-only (see ../../LICENSE) - part of z380m-alpine

x86 test rigs for the desktop and the installer. They prove script logic only (see docs/TESTING.md).

  make_rig.sh   usage (as root):  bash installer/rig/make_rig.sh <repo copy> <alpine-minirootfs-3.24.2-x86_64.tar.gz>
                builds <repo copy>/rootfs_x86 (desktop rig) and <repo copy>/rootfs_inst_base (installer rig). Deletes nothing;
                it stops if those folders exist. Work on a COPY of the repository, not on your clone.
  mkrepo3.sh    (runs inside rig 2) builds the fake package repository with the real apk-tools: apk mkpkg / mkndx
  inst_outer.sh, inst_inner.sh, paste_outer.sh, paste_inner.sh, show_run.sh
                launchers used by installer/test_install.py and installer/test_paste.py

The Alpine tarball (x86_64, not the aarch64 one that goes to the tablet):
  git clone --branch v3.24 https://github.com/alpinelinux/docker-alpine.git      -> x86_64/alpine-minirootfs-3.24.2-x86_64.tar.gz
  sha256 c5ca053cfe1d85c5b96dff8b9bc57045f7f184a30ffb6b65776409ca90388677, and its sha512 must appear in the repository's
  checksums.sha512 (checked on 19 Oct 2026 against commit 1c744e2 "Update Alpine v3.24 - 3.24.2").

Then, from the repo copy, as root:
  python3 -I scripts/test_gui.py .                                        (99 checks, about 4 minutes)
  python3 -I installer/test_install.py .                                  (48 checks)
  python3 -I installer/mkpaste.py . ./out && python3 -I installer/test_paste.py .      (25 checks)
  gcc -O1 -o out/t_fbfix installer/shim/test_fbfix.c installer/shim/fbfix.c && out/t_fbfix
The suites need unshare, chroot, tar, gcc and python3, and about 200 MB of scratch space. They create their own copies of the
rig folders inside the repo copy and delete only those.
