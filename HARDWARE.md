# AstroPi Hardware Inventory

This file records the hardware we have chosen for AstroPi, how it connects, and what still needs testing. **User-reported ownership is not the same as driver or hardware verification.** Update this file as components are tested.

## Core equipment

| Device | Purpose | Status / notes |
| --- | --- | --- |
| Raspberry Pi 4 Model B Rev 1.5 (4 GB RAM) | Runs headless AstroPi, camera acquisition, mount control and browser server | **Verified on `astropi` (2026-10-27):** Raspberry Pi 4 Model B Rev 1.5; Debian GNU/Linux **13.6 (Trixie)**; kernel **`6.18.39+rpt-rpi-v8`**; `free -h`: **3.7 GiB RAM total**, 188 MiB used, 3.5 GiB available; 2.0 GiB swap, unused. The separate 2 GB Pi runs the music streamer. |
| 64 GB USB 3 thumb drive | Intended storage for saved SV705C RAW/FITS exposures and image exports | **Owned and selected for acquisition data**; not connected or tested during 2026-10-27 baseline; confirm filesystem, actual capacity, sustained writes and stable mount path when attached. |
| SVBONY SV705C | Primary USB astronomical camera | Owned; planned first camera implementation using SVBONY SDK on Linux |
| ZWO AM3 | Motorized telescope mount | Owned; **Alt/Az mode exclusively**; serial-control integration planned |
| 12 V DC supply/distribution | Power to mount and accessories where appropriate | General power plan agreed; ratings, wiring and fused branches to document |
| 12 V-to-5 V buck converter | Power for Raspberry Pi | Planned / available per owner; validate voltage, current capacity and behaviour under load |
| N100 Linux Mint desktop | Optional development, simulation and browser access | Available; not required as an intermediary between GitHub and Pi |

## SVBONY Linux SDK location (reported 2026-10-27)

The SDK distribution is already extracted **on the AstroPi**, separate from the Git repository:

- **SDK root:** `/home/arn/svbony-sdk/SVBCameraSDK/`
- **Original archive:** `/home/arn/svbony-sdk/linux-SVBCameraSDK-v1.13.4.zip` (archive filename indicates SDK **v1.13.4**)
- **Directories/files observed:** `include/`, `lib/`, `demo/`, `readme.txt`, `90-ckusb.rules`
- **Library builds seen:** `lib/armv6/`, `lib/armv7/`, `lib/armv8/`, `lib/x86/`, `lib/x64/`; these include `libSVBCameraSDK.so`, a static `.a` archive, and bundled `libusb-1.0` files.
- **Likely native ARM64 library:** `/home/arn/svbony-sdk/SVBCameraSDK/lib/armv8/libSVBCameraSDK.so` (for host `aarch64`). **Architecture must still be checked with `file`;** directory naming alone does not verify the ELF build.
- **Likely bundled USB library:** `/home/arn/svbony-sdk/SVBCameraSDK/lib/armv8/libusb-1.0.so.0` (assess actual shared-library dependencies before choosing system versus bundled libusb).
- **Status:** Paths and file listing supplied from `arn@astropi`; actual ELF architecture, dependency loading, udev-rule installation, and SV705C detection/capture **not yet verified**.

For implementation, use the confirmed ARM64 SDK library once validated; do not use the x86 builds. Don't commit vendor SDK binaries to this repository.

## Verified running-system baseline (2026-10-27)

Measurements below are from **`arn@astropi`**, not the separate N100 desktop. These are idle-state measurements; camera and mount were **not connected**.

| Check | Observed value |
| --- | --- |
| Power / throttling | `vcgencmd get_throttled` → `throttled=0x0` (no undervoltage or throttling reported since boot) |
| CPU temperature | `vcgencmd measure_temp` → **34.0°C** |
| SD card | `mmcblk0` **29 GiB**, ~32 GB marketed capacity; 512 MiB firmware boot partition plus 28.5 GiB ext4 root partition |
| Filesystem space | Root filesystem **28 GiB total, 5.6 GiB used, 22 GiB available** (21% used); recording destination not yet chosen |
| USB | 5 Gbit/s USB 3 root hub present with **no USB 3 devices connected**; VIA Labs USB 2 hub detected (480 Mbit/s); no SV705C observed in scan |
| Network | `wlan0` up; `eth0` down, no carrier |
| Clock | NTP active and synchronized; **Europe/London (GMT)** time zone as of test; RTC unavailable (`n/a`) |
| Runtime | **Python 3.13.5**, `aarch64` |
| Swap | `zram0` 2 GiB swap; earlier `free -h` reported no swap usage |

**Follow-ups:** Test 5V power and `get_throttled` under sustained camera load; verify the planned 64 GB USB 3 recording drive and mount it persistently; verify the SV705C enumerates on a USB 3 port. Configure the Pi's time zone to the observing region if desired; astronomy calculations should use synchronized UTC plus explicitly configured observing latitude/longitude, not infer coordinates from time zone. Offline operation needs a way to acquire accurate time after boot (e.g. browser-provided clock or an RTC).

## Configuration still to record

- Telescope and focal length, including any reducer or Barlow (for image scale and field-of-view estimates).
- Exact USB and serial port topology; persistent device identification.
- Connect and verify 64 GB USB 3 thumb drive; choose filesystem and configure persistent mount by UUID (e.g., `/media/astropi-data`) as FITS/raw capture destination. No formatting or filesystem changes approved yet.
- Power-supply capacity, connector polarity, buck-converter ratings and cable layout.
- Confirm the extracted SDK's actual library version and ARM64 compatibility; validate udev rules, library dependencies and a successful SV705C capture. Record AM3 firmware version and hardware tests.

## Rules

1. Record **owned**, **planned**, **connected**, and **tested** separately; never call something working merely because the specification says it should work.
2. Keep passwords, Wi-Fi passphrases, API tokens and private keys **out of Git**. Store secrets locally in configuration excluded by `.gitignore`.
3. Update this file alongside commits when hardware assumptions or configurations change.
