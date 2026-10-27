# AstroPi Hardware Inventory

This file records the hardware we have chosen for AstroPi, how it connects, and what still needs testing. **User-reported ownership is not the same as driver or hardware verification.** Update this file as components are tested.

## Core equipment

| Device | Purpose | Status / notes |
| --- | --- | --- |
| Raspberry Pi 4 Model B Rev 1.5 (4 GB RAM) | Runs headless AstroPi, camera acquisition, mount control and browser server | **Verified on `astropi` (2026-10-27):** Raspberry Pi 4 Model B Rev 1.5; Debian GNU/Linux **13.6 (Trixie)**; kernel **`6.18.39+rpt-rpi-v8`**; `free -h`: **3.7 GiB RAM total**, 188 MiB used, 3.5 GiB available; 2.0 GiB swap, unused. The separate 2 GB Pi runs the music streamer. |
| 64 GB USB 3 thumb drive | Intended storage for saved SV705C RAW/FITS exposures and image exports | **Owned and selected for acquisition data**; not connected or tested during 2026-10-27 baseline; confirm filesystem, actual capacity, sustained writes and stable mount path when attached. |
| SVBONY SV705C | Primary USB astronomical camera | **Detected and identified through SDK on AstroPi (2026-10-27):** USB `f266:9a0a` at **5000M**, permissions `0666`; Python SDK enumeration `1`; camera-info returned name, port `USB3.0`, ID `1`. **Full-resolution RAW16 frame successfully acquired and saved (all SDK return codes `0`); sampled pixel statistics checked, visual confirmation pending.** |
| ZWO AM3N | Motorized telescope mount | Owned; **Alt/Az mode exclusively**. Prior Raspberry Pi USB serial communication verified in August 2026 (see details below). Previously listed in this file as AM3; mount reported model `AM3N#` to `:GVP#`. |
| 12 V DC supply/distribution | Power to mount and accessories where appropriate | General power plan agreed; ratings, wiring and fused branches to document |
| 12 V-to-5 V buck converter | Power for Raspberry Pi | Planned / available per owner; validate voltage, current capacity and behaviour under load |
| N100 Linux Mint desktop | Optional development, simulation and browser access | Available; not required as an intermediary between GitHub and Pi |

## SV705C USB detection (2026-10-27, connected hardware)

- **Verified with `lsusb` on `astropi`:** `Bus 002 Device 002: ID f266:9a0a SVBONY SVBONY SV705C`.
- **Verified negotiated link:** `lsusb -t` shows Bus 002, Port 002, device `Vendor Specific Class` at **5000M** (USB 3 SuperSpeed). Bus and device numbers can change on reconnect.
- **Verified permissions:** `/dev/bus/usb/002/002` is `crw-rw-rw-` (`0666`, `root:root`); `arn` can access the node. Vendor rule `90-ckusb.rules` specifies `f266:9a0a` and `MODE="0666"`; installed at `/etc/udev/rules.d/90-ckusb.rules`. Appropriate for this trusted local setup; reconsider if exposed to untrusted local users.
- **Verified SDK dynamic loading:** `ctypes.CDLL('/home/arn/svbony-sdk/SVBCameraSDK/lib/armv8/libSVBCameraSDK.so')` succeeded under normal user `arn`.
- **Verified SDK camera enumeration:** Python `ctypes` call `SVBGetNumOfConnectedCameras()` returned **1** (as normal user `arn`, camera attached, 2026-10-27). This confirmed SDK-level detection, followed by successful camera opening and RAW16 capture described below.
- **Verified camera identity:** `SVBGetCameraInfo(..., index=0)` returned success (`0`), name `SVBONY SV705C`, port `USB3.0`, `DeviceID=4865`, and `CameraID=1`. The SDK's camera index and its returned camera ID are distinct.
- **Verified SDK initialization and sensor capabilities:** A fresh process called `SVBGetNumOfConnectedCameras()` → `1`, `SVBGetCameraInfo(index=0)` → success (`0`, `CameraID=1`), `SVBOpenCamera(1)` → `0`, `SVBGetCameraProperty(1, ...)` → `0`, and `SVBCloseCamera(1)` → `0`. Reported maximum resolution **3856 × 2180** (8,406,080 pixels), **colour sensor**, **maximum bit depth 12**, supported binning **1, 2, 3, 4**, raw **Bayer enum 2**, and supported image-format enum values **0, 4, 5, 10** (`-1` appears to terminate the list; additional zero-filled array slots follow). Decode enum meaning from exact SDK header before using it. The earlier error `2` happened when the property query was attempted before opening the camera; this sequencing issue is now resolved.
- **Power/thermal after connection:** `vcgencmd get_throttled` → `throttled=0x0`; `vcgencmd measure_temp` → **33.6°C**. This is connected/idle, **not a sustained camera-capture load test**.
- **Outstanding tests:** Check actual pixel-value distribution and render a recognizable preview, verify exposure/gain settings and RAW16 byte ordering/value alignment, then retest throttling/power during continuous use.

## First successful SV705C RAW16 capture (2026-10-27)

**Verified on `arn@astropi`, using Python `ctypes` and the native `armv8/libSVBCameraSDK.so` library:**

| Capture step | Observed SDK return code |
| --- | --- |
| `SVBGetCameraInfo` | `0` |
| `SVBOpenCamera` | `0` |
| `SVBGetCameraProperty` | `0` |
| `SVBSetROIFormat(id, 0, 0, 3856, 2180, 1)` | `0` |
| `SVBSetOutputImageType(id, 4)` (RAW16) | `0` |
| `SVBStartVideoCapture` | `0` |
| `SVBGetVideoData` (20-second wait limit) | `0` |
| `SVBStopVideoCapture` | `0` |
| `SVBCloseCamera` | `0` |

- **First saved image:** `/home/arn/sv705c-first-frame.raw16` on the Pi's microSD root filesystem, **16,812,160 bytes** (3856 × 2180 × 2 bytes/pixel). No FITS header or color processing; this is an unprocessed raw pixel buffer. The configured exposure was the camera's existing setting, not explicitly set by the test.
- **SDK headers decode reported enums:** Bayer `2` = **GRBG**; supported formats `0` = RAW8, `4` = RAW16, `5` = Y8, `10` = RGB24. The sensor reports maximum 12-bit depth; RAW16 is a 16-bit output container.
- **Verification boundary:** The SDK reported a successful full-resolution frame transfer and a file was written at exactly the expected size. **A stride-sampled pixel distribution has been checked:** across 8,406,080 16-bit pixels (sampling every 997th), minimum `0`, maximum `288`, average `17.72`, `18` distinct sampled values; first 20 pixel values were mostly `0` with some `16`. Nontrivial values are present but the frame is very dark. Sample values suggest possible 12-bit data left-aligned within RAW16 (multiples of 16); bit alignment **not yet verified**. **Visual image validity, controlled exposure/gain tests, repeated captures, FITS packaging and sustained power have not yet been tested.** Do not claim these are complete.
- **Optical conditions (user reported):** The camera had a lens attached that was zoomed in and substantially out of focus during the first capture. Therefore this frame is **not a useful test of focus or image sharpness**; defocus and an unknown scene/exposure may help explain its low contrast, but do not by themselves verify the intensity or RAW16 alignment. Test a focused, well-lit ordinary subject later (never aim optics toward the Sun).
- **Post-capture power check:** `vcgencmd get_throttled` → `throttled=0x0` (no undervoltage/throttling detected at that time; not proof of stability during a sustained acquisition sequence).
- **Implementation detail:** Successful call sequence was enumerate → get camera info → open → set ROI → set RAW16 → start video capture → get frame → stop → close. The SDK's “video” functions can be used to retrieve individual image frames.

## SVBONY Linux SDK location (reported 2026-10-27)

The SDK distribution is already extracted **on the AstroPi**, separate from the Git repository:

- **SDK root:** `/home/arn/svbony-sdk/SVBCameraSDK/`
- **Original archive:** `/home/arn/svbony-sdk/linux-SVBCameraSDK-v1.13.4.zip` (archive filename indicates SDK **v1.13.4**)
- **Directories/files observed:** `include/`, `lib/`, `demo/`, `readme.txt`, `90-ckusb.rules`
- **Library builds seen:** `lib/armv6/`, `lib/armv7/`, `lib/armv8/`, `lib/x86/`, `lib/x64/`; these include `libSVBCameraSDK.so`, a static `.a` archive, and bundled `libusb-1.0` files.
- **Verified native ARM64 SDK library:** `/home/arn/svbony-sdk/SVBCameraSDK/lib/armv8/libSVBCameraSDK.so`. `file` reports **ELF 64-bit LSB shared object, ARM aarch64**, dynamically linked.
- **Verified dependency resolution:** `ldd` resolves every dependency with **no missing libraries**: `libstdc++.so.6`, `libusb-1.0.so.0`, `libm.so.6`, `libgcc_s.so.1`, `libc.so.6`, `libudev.so.1`, and `libcap.so.2`.
- **USB dependency:** `libusb-1.0.so.0` resolves to the installed system library at `/lib/aarch64-linux-gnu/libusb-1.0.so.0`; the SDK-bundled libusb is not currently necessary for dependency resolution.
- **Status:** ARM64 binary architecture and shared-library dependencies **verified on AstroPi (2026-10-27)**. SDK loading through Python ctypes, USB-node permissions and installed udev rule **verified on AstroPi (2026-10-27)**. SDK enumeration **verified (1 device)**; camera open/close and sensor-property retrieval **verified (success return codes)**. A single SDK RAW16 frame acquisition and expected-sized file write **verified**; image content still requires validation.

For implementation, use this verified ARM64 SDK build; do not use the x86 builds. Don't commit vendor SDK binaries to this repository.

## ZWO AM3N serial connection — earlier AstroPi tests (2026-08-31)

The following were recovered from earlier mount-control work on the Raspberry Pi; these are **historical results**, not tests on the disconnected mount during the 2026-10-27 hardware baseline.

| Detail | Earlier observed result |
| --- | --- |
| USB enumeration | ZWO Systems **VID:PID `03c3:4001`**; Linux **CDC ACM** serial device |
| Device path | `/dev/ttyACM0` |
| Persistent device alias | `/dev/serial/by-id/usb-ZWO_Systems_ZWO_Device_123456-if00` (prefer to a changing `ttyACM` number; reconfirm on reconnection) |
| Serial settings | **9600 baud, 8N1, no hardware/software flow control** |
| User permissions | `/dev/ttyACM0` previously `root:dialout`, mode `0660`; user `arn` was in `dialout` |
| Connection routes tested | USB serial replies were obtained from an AM3N connection at the **saddle USB-C** port; subsequent diagnostic replies were obtained using the **head USB-B** port. Recheck the preferred physical control connection when wired up again. |
| Protocol | **LX200-style ASCII commands** ending in `#`, used directly over serial; INDI not required for this interface |

**Actually observed serial replies in earlier tests:**

- `:GR#` → `12:03:12#` (reported RA); `:GD#` → `+44*29:41#` (reported Dec).
- `:GVP#` → `AM3N#` (mount product/model identification).
- `:GV#` → `1.8.8#` (**reported version at the time**; recheck firmware later).
- `:GU#` → `nNZM000000000#` and `:GAT#` → `e7#` (raw replies recorded; their meaning is **not** inferred here).

**Earlier controller design / movement probe (requires renewed validation):**

- Controller commands used/proposed: `:hR#` unpark; speed presets `:R0#`, `:R3#`, `:R6#`, `:R9#`; directions `:Mn#`, `:Ms#`, `:Me#`, `:Mw#`; stops `:Qn#`, `:Qs#`, `:Qe#`, `:Qw#` and `:Q#` (all-stop).
- Previous diagnostics included `:hR#`, `:R6#`, and `:Me#` during a movement test. The precise physical-motion/stop outcomes were not fully recoverable in this review, so **do not mark the entire slew-control or safety behavior verified**.
- A prototype browser/Flask AM3N controller was drafted with press-and-hold movement, speed selection, stop-all, and a timeout watchdog. Existence of code does **not** prove these behaviors are hardware-tested.
- **Still to test:** command acceptance, physical stop response, all speed levels, tracking start/stop, parking, GoTo, and manual two-/multi-star alignment, all in Alt/Az mode.

**Physical caution previously reported by owner:** The mount's M12 counterweight-hole path can extend into internal wiring. **Do not insert an excessively long M12 bolt.** Confirm mounting hardware clearance before use.

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

**Follow-ups:** Test 5V power and `get_throttled` under sustained camera load; verify the planned 64 GB USB 3 recording drive and mount it persistently; visually verify first frame, confirm RAW16 value alignment and check sustained camera power stability. Configure the Pi's time zone to the observing region if desired; astronomy calculations should use synchronized UTC plus explicitly configured observing latitude/longitude, not infer coordinates from time zone. Offline operation needs a way to acquire accurate time after boot (e.g. browser-provided clock or an RTC).

## Configuration still to record

- Telescope and focal length, including any reducer or Barlow (for image scale and field-of-view estimates).
- Reconfirm the historical AM3N USB cable/port connection and stable `/dev/serial/by-id/` alias once the mount is reconnected; map the remaining USB devices.
- Connect and verify 64 GB USB 3 thumb drive; choose filesystem and configure persistent mount by UUID (e.g., `/media/astropi-data`) as FITS/raw capture destination. No formatting or filesystem changes approved yet.
- Power-supply capacity, connector polarity, buck-converter ratings and cable layout.
- Query the SDK-reported version and supported exposure controls, validate RAW16 pixel interpretation and produce a viewable preview; later verify exposure sequences and saving to the USB 3 data drive. Recheck AM3N-reported version (historically `1.8.8#`) and test motion/stop/tracking/GoTo safely.

## Rules

1. Record **owned**, **planned**, **connected**, and **tested** separately; never call something working merely because the specification says it should work.
2. Keep passwords, Wi-Fi passphrases, API tokens and private keys **out of Git**. Store secrets locally in configuration excluded by `.gitignore`.
3. Update this file alongside commits when hardware assumptions or configurations change.
