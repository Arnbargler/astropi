# AstroPi Hardware Inventory

This file records the hardware we have chosen for AstroPi, how it connects, and what still needs testing. **User-reported ownership is not the same as driver or hardware verification.** Update this file as components are tested.

## Core equipment

| Device | Purpose | Status / notes |
| --- | --- | --- |
| Raspberry Pi 4 Model B Rev 1.5 (4 GB RAM) | Runs headless AstroPi, camera acquisition, mount control and browser server | **Verified on `astropi` (2026-10-27):** Raspberry Pi 4 Model B Rev 1.5; Debian GNU/Linux **13.6 (Trixie)**; kernel **`6.18.39+rpt-rpi-v8`**; `free -h`: **3.7 GiB RAM total**, 188 MiB used, 3.5 GiB available; 2.0 GiB swap, unused. The separate 2 GB Pi runs the music streamer. |
| SVBONY SV705C | Primary USB astronomical camera | Owned; planned first camera implementation using SVBONY SDK on Linux |
| ZWO AM3 | Motorized telescope mount | Owned; **Alt/Az mode exclusively**; serial-control integration planned |
| 12 V DC supply/distribution | Power to mount and accessories where appropriate | General power plan agreed; ratings, wiring and fused branches to document |
| 12 V-to-5 V buck converter | Power for Raspberry Pi | Planned / available per owner; validate voltage, current capacity and behaviour under load |
| N100 Linux Mint desktop | Optional development, simulation and browser access | Available; not required as an intermediary between GitHub and Pi |

## Configuration still to record

- Telescope and focal length, including any reducer or Barlow (for image scale and field-of-view estimates).
- Exact USB and serial port topology; persistent device identification.
- Storage device and destination for FITS/raw captures.
- Power-supply capacity, connector polarity, buck-converter ratings and cable layout.
- Camera SDK versions, mount firmware version, and successful hardware tests.

## Rules

1. Record **owned**, **planned**, **connected**, and **tested** separately; never call something working merely because the specification says it should work.
2. Keep passwords, Wi-Fi passphrases, API tokens and private keys **out of Git**. Store secrets locally in configuration excluded by `.gitignore`.
3. Update this file alongside commits when hardware assumptions or configurations change.
