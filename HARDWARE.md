# AstroPi Hardware Inventory

This file records the hardware we have chosen for AstroPi, how it connects, and what still needs testing. **User-reported ownership is not the same as driver or hardware verification.** Update this file as components are tested.

## Core equipment

| Device | Purpose | Status / notes |
| --- | --- | --- |
| Raspberry Pi | Runs headless AstroPi, camera acquisition, mount control and browser server | Exact model, RAM and OS/kernel for the AstroPi unit: **to confirm** |
| SVBONY SV705C | Primary USB astronomical camera | Owned; planned first camera implementation using SVBONY SDK on Linux |
| SVBONY SC571CC | Optional higher-resolution cooled astronomical camera | Owned; future ToupTek SDK driver, cooling controls required |
| ZWO AM3 | Motorized telescope mount | Owned; **Alt/Az mode exclusively**; serial-control integration planned |
| BrosTrend AC5L (AC650) USB Wi-Fi adapter | External Wi-Fi connection for the Pi | Owned; driver and hotspot operation **not yet tested on AstroPi Pi** |
| 12 V DC supply/distribution | Power to mount and cooled camera where appropriate | General power plan agreed; ratings, wiring and fused branches to document |
| 12 V-to-5 V buck converter | Power for Raspberry Pi | Planned / available per owner; validate voltage, current capacity and behaviour under load |
| N100 Linux Mint desktop | Optional development, simulation and browser access | Available; not required as an intermediary between GitHub and Pi |

## Wi-Fi adapter technical notes

- **BrosTrend AC5L**, not AX5L; manufacturer's information identifies a Realtek RTL8821CU-family adapter.
- Manufacturer's USB ID for AC5L in Wi-Fi mode: `0bda:c811`.
- Linux in-kernel module `rtw88_8821cu` is listed as supported from kernel 6.2 onward. Prefer testing the in-kernel driver before installing a separate DKMS driver.
- Manufacturer lists managed (client) and AP (hotspot) capability, but verify actual AP support and stability on the Pi.
- Intended AstroPi Wi-Fi architecture (join existing network, host its own hotspot, or both): **to decide**.
- Manufacturer sources:
  - https://linux.brostrend.com/supported-distributions/
  - https://linux.brostrend.com/advanced/usb_modeswitch/
  - https://www.brostrend.com/products/ac5l

### Verification commands (run on Pi after plugging in adapter)

```bash
uname -r
lsusb
ip -br link
iw list
```

Record actual kernel version, USB ID, driver in use and supported interface modes once tested. Avoid installing a vendor driver unless the standard kernel driver fails.

## Configuration still to record

- Raspberry Pi model / RAM / OS image and kernel.
- Telescope and focal length, including any reducer or Barlow (needed for plate solving and field-of-view predictions).
- Exact USB and serial port topology; persistent device identification.
- Storage device and destination for FITS/raw captures.
- Power-supply capacity, connector polarity, buck-converter ratings and cable layout.
- Wi-Fi operating mode, tested range, throughput and reconnect behaviour.
- Camera SDK versions, mount firmware version, and successful hardware tests.

## Rules

1. Record **owned**, **planned**, **connected**, and **tested** separately; never call something working merely because the specification says it should work.
2. Keep passwords, Wi-Fi passphrases, API tokens and private keys **out of Git**. Store secrets locally in configuration excluded by `.gitignore`.
3. Update this file alongside commits when hardware assumptions or configurations change.
