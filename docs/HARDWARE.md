# The tablet: what is known about the hardware and the installed system

Copyright (C) 2026 [kaantcp](https://github.com/kaantcp) · GPL-3.0-only · part of [z380m-alpine](../README.md)

Labels: **V** = verified on the tablet (a log in [evidence/](../evidence) or my own check on the tablet), **A** = assumed, **A(rig)** = only seen in the x86 test rig. `evidence/NN` names the log. Facts that rest on my own check only, with no log, are marked "report".

## The device

| Item | Fact |
|---|---|
| Model | ASUS ZenPad 8.0, Z380M, P00A (as stated by me). |
| SoC | MediaTek MT8163, HW code `0x8163`, four CPUs (V: `ksoftirqd/0` to `ksoftirqd/3` in `ps`, evidence/03). |
| RAM | 1953 MB (V: `free -m`, evidence/03). |
| Storage | eMMC, user area `0x3ab400000` bytes = 14.7 GiB; `boot1`, `boot2` and RPMB areas 4 MiB each (V, evidence/01). 26 GPT partitions, full table in [GUIDE.md, Appendix A](GUIDE.md#appendix-a-the-partition-table-of-the-tested-tablet). |
| Flash access | mtkclient in BROM mode with the Kamakiri exploit and the legacy download agent `MTK_DA_V5.bin`. Security flags: SBC enabled, SLA disabled, DAA disabled (V, evidence/01). I used mtkclient 2.1.3 with a local patch of `dalegacy_lib.py` ("manual preloader"; report). Speed: read 0.49 MB/s, write 7.0 to 8.2 MB/s (V, evidence/01 and 02). Every command needs a new BROM entry (V). |
| Kernel | The stock ASUS kernel, `Linux 3.18.35 #1 SMP PREEMPT Thu Aug 9 12:33:25 CST 2018 aarch64`, copied byte for byte (7,472,341 bytes) into my boot image (V, evidence/03 and 05). No devtmpfs (V: `devtmpfs=NO` in the ramdisk log, evidence/03; the ramdisk uses `mdev`). Virtual terminals: no log in this repository settles whether the kernel has them. The installer's own check for one (`/dev/tty0` or `vtmaster` in `/proc/tty/drivers`) passed on the tablet, and desktop starter version 2 also contains a stand-in for kernels without them (`-sharevts`, `/dev/tty1` linked to `/dev/null`); which of the two paths the tablet takes is **A**. ext4, tmpfs, devpts, configfs, debugfs, fusectl and selinuxfs exist (V, evidence/03). |
| Kernel command line | `console=tty0 console=ttyMT0,921600n1 earlycon=uart8250,mmio32,0x11002000 root=/dev/ram vmalloc=496M androidboot.hardware=mt8163 bootopt=64S3,32N2,64N2 build_version=3 proj_id=0 hw_id=3 pcb_id=696 printk.disable_uart=1 ... androidboot.mode=main ... lk.ro.config.versatility=US lk.ro.config.CID=ASUS lk.ro.config.idcode=6A lk.atd.fuse.ready=TRUE` (V, evidence/03; the serial number fields are replaced there). It comes from the LK boot loader and is not changed by my boot image (V, evidence/05: only the ramdisk size and the header SHA1 differ from the stock header). |
| Display | `/dev/fb0` is `mtkfb`: 800x1280, 32 bits per pixel, stride 3200, virtual size 800x3840; `fbset` reports `rgba 8/0,8/8,8/16,8/24` (V, evidence/03). |
| Colours | On the panel, red and blue come out exchanged relative to the offsets the driver reports (seen on the screen, report). `z380term` therefore swaps them by default (`-n` switches that off). After Xorg's first screen update the swap is no longer needed (**A**: the display's pixel format changes; it works on my tablet, so the text console skips its swap once `/run/z380m-fb-panned` exists). |
| Backlight | `/sys/class/backlight` is empty; `/sys/class/leds/lcd-backlight` exists (V, evidence/03). `z380m-bright` writes that LED's `brightness` file (**A(rig)**: the file layout and maximum on the real tablet were not checked). |
| Input | `event0` ACCDET, `event1` mtk-kpd, `event2` HALL_SENSOR, `event3` hwmdata, `event4` m_batch_input, `event5` m_alsps_input, `event6` m_acc_input, `event7` m_mag_input, `event8` m_step_c_input, `event9` m_shk_input, `event10` m_fdn_input, **`event11` elan-touchscreen** (V, evidence/03; numbers can change, the desktop finds the touch panel by its name). |
| Keys | `mtk-kpd` has `KEY_VOLUMEDOWN`, `KEY_VOLUMEUP` and `KEY_POWER` (V, decoded from the bitmap in evidence/03). |
| Touch panel | Multitouch type B only: `ABS_MT_SLOT`, `ABS_MT_TOUCH_MAJOR`, `ABS_MT_POSITION_X`, `ABS_MT_POSITION_Y`, `ABS_MT_TRACKING_ID` and `ABS_PRESSURE`. No `ABS_X`, no `ABS_Y`, no `BTN_TOUCH`, `PROP=0` (V, decoded from evidence/03). The touch bridge falls back to the ranges X 0 to 1472 and Y 0 to 2368, the values reported for this panel (the log they came from is not in this repository). |
| USB | Android gadget (`android_usb`) with the function directories `f_accessory f_acm f_audio_source f_eem f_ffs f_gser f_hid f_mass_storage f_mbim f_midi f_mtp f_ptp f_rndis` (V, evidence/03). `acm` = `0e8d:2007` (serial); `rndis,acm` = `0e8d:2008` works: the PC sees `rndis_host` and `/dev/ttyACM0`; the tablet side is `rndis0`, 192.168.7.2/24 (V, evidence/03 and 04). |
| Network | **No `wlan0`.** The kernel lists `lo`, `ifb0`, `ifb1`, `tunl0`, `sit0` and `ip6tnl0` only; kernel threads `cfg80211` and `btif_rxd` exist (V, evidence/03). The Wi-Fi/Bluetooth chip is not identified. That it is a MediaTek combo chip that needs vendor firmware and a loader that are not on the tablet is **A**. |
| Other | `rtc0`; power supplies `ac battery pack_ac pack_bat usb wireless`; Mali GPU kernel threads (V, evidence/03). Whether DRM/KMS exists was not probed (**A**). |

## The boot chain

```
BROM (in the chip) -> preloader (eMMC boot1) -> LK -> `boot` partition (Android boot image v0, page size 2048, 512-byte MTK wrappers)
   kernel  7,472,341 bytes, byte-identical to the stock one                        (V, evidence/05)
   ramdisk 1,277,693 bytes (gzip newc cpio): static BusyBox 1.36.1, z380term, /init v3
/init:  tmpfs /dev + mdev -s
        USB gadget "acm" (0e8d:2007, product Z380M-Alpine, serial z380m0001)        (V, evidence/03)
        5 s rescue window ("tap VOL+/VOL- or touch the screen within 5s for RESCUE") (V as text; the rescue path itself was never tested)
        finds partition `system` as mmcblk0p25 (at 7.44 s), mounts it as ext4 on /newroot
        checks the marker /etc/z380m-release (first line z380m-alpine)               (V, evidence/03)
        smoke test of Alpine's BusyBox, writable check, mount --move sys dev proc, switch_root -> /sbin/init
Alpine: BusyBox init + OpenRC  (sysinit -> boot -> default, done at 19.9 s)           (V, evidence/03)
        /etc/z380m/console.sh respawned by init: z380term = text console on /dev/fb0 + USB serial
Desktop (optional, section 9 of the guide): z380m-gui = Xorg (fbdev) + JWM + touch bridge
```

The ramdisk also writes a text log into `expdb` on every boot (only if that partition's geometry equals the GPT numbers; up to 1,000,000 bytes). It never writes any other partition (`src/build_boot_v3.py`, the comment above `savelog` and the function itself).

## The installed system

Built by `src/build_alpine_rootfs.py` (V, evidence/03 and 05):

- Alpine Linux 3.24.2, aarch64, apk-tools 3.0.8, BusyBox init plus OpenRC (no systemd), hostname `z380m`.
- A 512 MiB ext4 image, label `z380m-alpine`, with only the features a Linux 3.18 kernel can mount: `has_journal extent huge_file flex_bg uninit_bg dir_nlink extra_isize` plus `sparse_super large_file filetype resize_inode dir_index ext_attr`. No `metadata_csum`, `64bit` or `orphan_file`. The builder checks this against an allow-list. At first boot: 487.6M size, 38.9M used, 433.3M available.
- `/etc/fstab` has one line, `/dev/part_system / ext4 rw,noatime 0 0`. `/etc/apk/repositories` points to `http://dl-cdn.alpinelinux.org/alpine/v3.24/main` and `.../community` (plain http, pinned to v3.24). `/etc/resolv.conf` is static (1.1.1.1 and 9.9.9.9).
- 83 packages at build time: `openrc busybox-openrc busybox-mdev-openrc mdev-conf busybox-suid e2fsprogs e2fsprogs-extra iproute2 wpa_supplicant iw openssh ca-certificates tzdata` and `nano htop bash curl strace evtest alpine-conf wireless-tools` with their dependencies. `sshd` is installed but not enabled. No Python, no compiler and no X at build time.
- The root account has a locked password. The serial console is a root shell without a login (V, evidence/03 and 05).
- Logs on the tablet: `/var/log/z380m-ramdisk.log`, `z380m-boot.log`, `z380m-openrc.log`, `z380m-console.log`, `z380m-usb.log`, and after the desktop install `z380m-gui.log` and `Xorg.0.log`.
- The desktop packages (`xorg-server xf86-video-fbdev xf86-input-evdev xkbcomp xkeyboard-config xsetroot xset xrdb setxkbmap font-dejavu font-misc-misc font-cursor-misc xterm jwm`, plus `svkbd`, `matchbox-keyboard`, `xinput` and `tcc` when available) are installed as the virtual package `.z380m-gui` and removed by `sh /root/gui-uninstall.sh`.

## Known leftovers (V unless marked)

1. **`/tmp` is on the root ext4, not a tmpfs.** `stat -c '%d %n' / /tmp` printed the same device number for both (evidence/04). The cause is in the builder source: the boot script's check `mounted /tmp || mount -t tmpfs ...` is fooled by a stale `tmpfs /tmp` line that `/proc/mounts` still lists after `switch_root` (evidence/03 shows that line). BusyBox's `df -h /` therefore prints the root filesystem as `tmpfs ... /tmp`. A possible fix (**A**, not done): compare `stat -c %d` of `/` and `/tmp`.
2. Some texts on the tablet are out of date: the `z380m-usb` help says `rndis-acm` was "never tried" (it works), the message of the day says "Network: none yet", `/etc/network/interfaces` has a `usb0` stanza although the interface is `rndis0`, and `z380m-usb` adds no default route (the guide does it by hand).
3. Harmless boot noise (V that it appears, **A** that it is harmless): `modprobe: can't change directory to '/lib/modules'` (the kernel has no modules directory), `sysctl: error: 'kernel.unprivileged_bpf_disabled' is an unknown key`, `mknod: /dev/null: File exists`, `mdev: can't create ''`, clock-skew warnings and `ifup` register dumps mentioning `syscall 434` (`pidfd_open` does not exist in 3.18; the userland falls back).
4. The clock starts from the image build time or the last shutdown time (`swclock`) and is wrong; there is no network time (V, evidence/03).
5. Not tested on the tablet (**A**): `reboot` and `poweroff` inside Alpine, the rescue window catching a key or a touch, online `resize2fs` on this kernel, whether the USB network survives a reboot, and a second boot of Alpine with the desktop installed.
6. Anything you install on the tablet lives only in its ext4. Re-flashing `system_alpine.ext4` erases it. To make something permanent, add it to the package lists in `build_alpine_rootfs.py` and rebuild.
