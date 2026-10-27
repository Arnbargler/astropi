# AstroPi Hardware Inventory

This file records the hardware we have chosen for AstroPi, how it connects, and what still needs testing. **User-reported ownership is not the same as driver or hardware verification.** Update this file as components are tested.

## Core equipment

| Device | Purpose | Status / notes |
| --- | --- | --- |
| Raspberry Pi 4 Model B Rev 1.5 (4 GB RAM) | Runs headless AstroPi, camera acquisition, mount control and browser server | **Verified on `astropi` (2026-10-27):** Raspberry Pi 4 Model B Rev 1.5; Debian GNU/Linux **13.6 (Trixie)**; kernel **`6.18.39+rpt-rpi-v8`**; `free -h`: **3.7 GiB RAM total**, 188 MiB used, 3.5 GiB available; 2.0 GiB swap, unused. The separate 2 GB Pi runs the music streamer. |
| 64 GB USB 3 thumb drive | Intended storage for saved SV705C RAW/FITS exposures and image exports | **User-approved 2026-10-27 reformat successful:** `Flash Drive FIT` at USB 3.0 **5000M**, 59.8 GiB. Old Pi OS image erased; now a single **ext4** GPT partition `sda1` labelled `astropi-data`, filesystem UUID **`25b33cfa-b178-4b86-8a15-d00c8305cca5`**. Confirmed independently with `blkid -p`, `wipefs -n`, and `lsblk` after `udevadm settle`. **Mount configuration and write tests still pending.** Operating-system root is separately on `/dev/mmcblk0`. |
| SVBONY SV705C | Primary USB astronomical camera | **Detected and identified through SDK on AstroPi (2026-10-27):** USB `f266:9a0a` at **5000M**, permissions `0666`; Python SDK enumeration `1`; camera-info returned name, port `USB3.0`, ID `1`. **Full-resolution RAW16 frame successfully acquired and saved (all SDK return codes `0`); sampled pixel statistics checked, visual confirmation pending.** |
| ZWO AM3N | Motorized telescope mount | **Connected to AstroPi, USB/CDC ACM enumerated (2026-10-27):** `03c3:4001`, `/dev/ttyACM0`, stable `/dev/serial/by-id/usb-ZWO_Systems_ZWO_Device_123456-if00`; `arn` in `dialout`. **Live serial queries verified** (`AM3N#`, firmware `1.8.8#`, RA/Dec responses). **User visually confirmed** commanded azimuth movement at 120× sidereal; instantaneous/fail-safe stop, tracking and GoTo remain unverified. Alt/Az mode exclusively; older protocol tests below. |
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

## ZWO AM3N connected hardware — AstroPi retest (2026-10-27)

**Verified from the live `arn@astropi` USB/udev and power outputs:**

- `lsusb` → `03c3:4001 ZWO ZWO Device`; SVBONY SV705C simultaneously present as `f266:9a0a`.
- `lsusb -t` → `cdc_acm` interfaces for the mount at **12M** on USB2 bus; the SV705C still runs at **5000M** on the USB3 bus.
- Serial node: `/dev/ttyACM0`, permissions `crw-rw---- root dialout`. User `arn` is a member of `dialout`; no sudo expected for serial queries.
- Persistent symlink: `/dev/serial/by-id/usb-ZWO_Systems_ZWO_Device_123456-if00 -> ../../ttyACM0`. Prefer this alias in configuration.
- Kernel events at connection: Espressif `303a:1001` USB JTAG/serial debug unit briefly enumerated, disconnected and was replaced by `03c3:4001` ZWO USB CDC ACM within about a second; this may be a normal boot-to-application sequence, but its cause has not been established.
- With camera and mount connected: `vcgencmd get_throttled` → `throttled=0x0`; `vcgencmd measure_temp` → **39.9°C**.
- **Verification boundary:** Linux USB detection, serial-device creation and account permissions confirmed. **Serial request/reply is now verified (see below), but motor movement, physical stop behavior, tracking and coordinate accuracy have not yet been verified**. Prior historical responses are documented below.

### Current AM3N serial communication verified (2026-10-27)

- `python3-serial` / `pyserial` **3.5** is already installed. Python serial port opening and queries worked as user `arn`, no `sudo` required.
- Connected using stable `/dev/serial/by-id/usb-ZWO_Systems_ZWO_Device_123456-if00`, at **9600 baud, 8N1**, `timeout=2`, no XON/XOFF or RTS/CTS flow control.
- Each query returned a `#`-terminated reply, and the port closed normally:

| Read-only command | 2026-10-27 reply |
| --- | --- |
| `:GVP#` (mount model) | `AM3N#` |
| `:GV#` (firmware version) | `1.8.8#` |
| `:GR#` (reported right ascension) | `12:02:59#` |
| `:GD#` (reported declination) | `+44*29:41#` |

- These confirm the mount identity and live serial request/response path with the camera still connected. Coordinates are the mount's **reported** values, **not** verified pointing accuracy or an indication that alignment is complete.

### Current read-only AM3N status replies (2026-10-27)

Both commands executed successfully at 9600 baud from `arn@astropi` using the persistent serial port:

| Command | Observed response | Interpretation and limitations |
| --- | --- | --- |
| `:GU#` | `nNZM000000000#` | Third-party ZWO AM3/AM5 protocol implementation documents `n` = not tracking, `N` = not slewing, `Z` = Alt/Az mode. `M` and numeric suffix not yet decoded; the flag mapping should be checked against this mount's behaviour in subsequent tests. |
| `:GAT#` | `e7#` | Raw response recorded. Third-party protocol documentation expects `0`/`1` for tracking status, **inconsistent** with the observed `e7#`; do **not** decode it or assume its tracking meaning. |

- The responses match the historical August 2026 replies **exactly**.
- Protocol interpretation reference: `https://docs.rs/zwo_mount_control/latest/src/zwo_mount_control/protocol.rs.html` (third-party library; status flag mapping, not itself an AM3N hardware validation).
- **No movement command was issued.** Verify Alt/Az altitude/azimuth and date/time readbacks next, then test safety stop before performing an actual slew.


### Current AM3N pointing and clock query results (2026-10-27)

Using the same working USB serial path and read-only LX200-like commands on `astropi`:

| Command | Description | Observed response |
| --- | --- | --- |
| `:GA#` | Reported altitude | `+00*00:00#` |
| `:GZ#` | Reported azimuth | `000*00:00#` |
| `:GC#` | Mount date | `01/01/00#` |
| `:GL#` | Mount local time | `00:07:12#` |
| `:GG#` | Mount UTC offset | `+00:00#` |

- Altitude and azimuth both read zero, **not proof of actual pointing** before alignment or physical position confirmation.
- Date appears to represent **January 1, 2000** and clock time reads 00:07:12, unlike the current 2026-10-27 date. The mount clock therefore **appears unset/reset**. UTC offset 0 may be a default; do not assume it reflects the observing location.
- Clock, offset, observing coordinates, and alignment should be managed explicitly in AstroPi before performing GoTo or interpreting sky positions. Avoid changing mount time or location until command semantics and intended observing location are confirmed.
- **No motors moved in this test.** Next inspect configured site latitude/longitude (`:Gt#` / `:Gg#`) and consider whether the clock advances. Before any powered movement, verify a safe stop strategy and clear mechanical range.

- **Still untested:** authoritative validation of all status flags, confirmation of when high-speed stopping physically completes, disconnection fail-safe, tracking, park/unpark, homing and GoTo. User has visually confirmed commanded azimuth motion using the variable 120× speed. (Raw status queries do return replies.)

### User-selected AstroPi observing site (2026-10-27)

**User supplied intended observing coordinates** (not inferred from the mount):
- Latitude: **+45.2933°** north → **+45°17′36″** rounded to nearest arcsecond.
- Longitude: **−75.8571°** east-positive (75.8571° west) → mount's **west-positive** setter **+075°51′26″** rounded to nearest arcsecond.
- Corresponding known ZWO AM-series location-setting commands (as implemented in INDI's `LX200AM5::updateLocation`): `:Sg+075*51:26#` for longitude and `:St+45*17:36#` for latitude, with single-byte `1` success acknowledgement, followed by readback `:Gg#`/`:Gt#`. Upstream reference: `https://github.com/indilib/indi/blob/master/drivers/telescope/lx200am5.cpp`.
- **Status (verified on AM3N, 2026-10-27):** Before adjustment, `:Gt#` returned `+45*30:19#` and `:Gg#` returned `+076*05:12#`; sent `:Sg+075*51:26#` → acknowledgment `b'1'`, then `:St+45*17:36#` → acknowledgment `b'1'`. Subsequent readbacks returned **latitude `+45*17:36#` and longitude `+075*51:26#`**, matching the user-selected observing site to whole-arcsecond precision. `:GS#` then returned `11:06:40#`. **Site setting and readback verified; pointing alignment and GoTo not verified.**
- AstroPi application should keep one explicit astronomy convention (east-positive signed decimal longitude), converting only at this ZWO command boundary.

### Current AM3N site coordinates and mount clock vs AstroPi clock (2026-10-27)

Read-only USB serial queries returned:

| Command | Raw response | Interpretation |
| --- | --- | --- |
| `:Gt#` | `+45*30:19#` | Latitude **+45°30′19″** ≈ **45.50528° N** |
| `:Gg#` | `+076*05:12#` | Longitude **+76°05′12″** in mount's Meade **west-positive** convention; ≈ **76.08667° W**, or **−76.08667° east-positive** |
| `:GS#` | `00:09:06#` | Sidereal-time readback; **accuracy is unverified** while mount date/time look reset |

- West-positive convention supported by third-party ZWO AM mount serial driver documentation: `https://pkg.go.dev/github.com/mikefsq/lx200@v0.2.2/am5`. Do not use the raw sign as east-positive when communicating with map/astronomy libraries.
- User-supplied Pi `timedatectl`: **Tue 2026-10-27 09:07:37 EDT**, UTC **13:07:37**, timezone **America/Toronto (EDT, UTC−4)**, `System clock synchronized: yes`, `NTP service: active`, no hardware RTC.
- Earlier mount date/time/zone readback was `01/01/00#`, `00:07:12#`, `+00:00#`, so its clock **was unset/unsynchronized** at that moment despite Pi synchronization. The UTC clock was **subsequently set and read back successfully** on 2026-10-27 (see below); site coordinates were not modified.
- **Do not equate the Pi time zone with mount `:GG#` sign convention without verifying the ZWO protocol.** Also confirm that the stored mount latitude/longitude are the user's intended observing site before assigning them to AstroPi configuration.
- No motor or set commands issued; next test should establish an emergency-stop path and cautious physical motion before GoTo.

### AM3N mount UTC clock configured successfully (2026-10-27)

Using the persistent USB serial port, Python `pyserial` and the Raspberry Pi's NTP-synchronized UTC clock, the user successfully set **UTC offset 0** and current date/time on the mount. This was a clock configuration test only; **no motion or site-coordinate changes** were commanded.

| Operation | Command or query | Observed |
| --- | --- | --- |
| Initial timezone read | `:GG#` | `+00:00#` |
| Initial date read | `:GC#` | `01/01/00#` |
| Initial clock read | `:GL#` | `00:38:30#` |
| Set UTC offset zero | `:SG+00:00#` | acknowledgment `1` |
| Set date | `:SC10/27/26#` | acknowledgment `1` |
| Set time | `:SL13:37:03#` | acknowledgment `1` |
| Final UTC offset | `:GG#` | `+00:00#` |
| Final date | `:GC#` | `10/27/26#` |
| Final time | `:GL#` | `13:37:04#` |
| Time 3 seconds later | `:GL#` | `13:37:07#` |

**Result:** All setters acknowledged success and the readback reflected the intended **2026-10-27 UTC time**, advancing three seconds over the three-second delay. Mount-to-Pi clock synchronization is **verified at the time of test**, but clock retention across mount power cycles and long-term drift **remain untested**. AstroPi should synchronize the mount after connection once system time is trustworthy (NTP or a validated offline clock). Set mount and software time zones consistently; retain explicit observing-site latitude/longitude and verify before GoTo.

### Mount clock, site and sidereal-time consistency checked (2026-10-27)

With the mount clock synchronized in UTC and the previously configured site retained, the user obtained the following **read-only** serial values at essentially the same instant as the Pi's UTC time:

| Query | Response |
| --- | --- |
| `:GC#` | `10/27/26#` |
| `:GL#` | `13:39:59#` |
| `:GS#` | `10:59:22#` |
| `:Gt#` | `+45*30:19#` |
| `:Gg#` | `+076*05:12#` (west-positive) |
| Pi UTC (`datetime.now(timezone.utc)`) | `2026-10-27T13:39:59.365169+00:00` |

- **Independent astronomical cross-check:** For UTC `2026-10-27 13:39:59` and east-positive longitude `−76.0866667°`, a standard Julian-date/GMST calculation gives **local mean sidereal time `10:59:21.56`**. The AM3N returned **`10:59:22`**, agreeing within about **0.44 seconds** (subject to non-simultaneous serial query times, rounding and differences between mean/apparent time).
- **Verified:** Clock readback matches NTP-synced Pi UTC at second resolution, location readback persists, and mount sidereal-time readback agrees with independent astronomy calculations for that configured longitude.
- **Not yet verified:** The configured latitude and longitude correspond to the user's intended observing site, physical mount alignment or pointing accuracy, system time after complete offline boot, persistence across mount power cycles, and GoTo correctness. Verify intended site coordinates before alignment/GoTo.

### Stop-all communication probe (2026-10-27)

- `arn@astropi` opened `/dev/serial/by-id/usb-ZWO_Systems_ZWO_Device_123456-if00` at 9600 baud, transmitted `:Q#`, paused 0.3 s, then queried status and position; serial port closed normally.
- Subsequent replies: `:GU#` → `nNZM000000000#`; `:GA#` → `+00*00:00#`; `:GZ#` → `000*00:00#`.
- **Verified:** stop command bytes can be sent without impairing serial communication, and subsequent queries work.
- **NOT verified:** stop acknowledgment (none expected for this command), any actual motor stop, fail-safe stop on a disconnected USB link, or physical-motion safety. Do not mark emergency stop operational until tested with actual motion.
- Protocol cross-check: ZWO AM-series third-party implementations describe `:Q#` as stop-all, direction starts `:Me#`/`:Mw#`/`:Mn#`/`:Ms#` with per-axis stops, and numbered rates `:R0#`–`:R9#`. Before using motion, ensure clearances and access to the mount's physical cancel control.

### First commanded AM3N azimuth motion — preliminary success (2026-10-27)

The user ran a Python serial test at 9600 baud on the stable ZWO device alias, with mount clearance and the camera connected:

1. Before motion: `:GU#` → `nNZM000000000#`, `:GA#` → `+00*00:00#`, `:GZ#` → `000*00:00#`.
2. Transmitted rate preset `:R5#`, waited 0.2 seconds, then `:Me#` (east/azimuth direction) for 1.0 second.
3. In a Python `finally` block, transmitted directional stop `:Qe#` followed by all-stop `:Q#`.
4. After 0.3 seconds: `:GU#` → `nNZM000000500#`, `:GA#` → `+00*00:00#`, `:GZ#` → `000*02:00#`; script finished without error.

**Interpretation:** Mount-reported azimuth increased by **0°02′00″ (2 arcminutes, ≈0.0333°)**; mount-reported altitude was unchanged. The user said the mount *may* have moved physically, but by a tiny amount. The `N` status flag is consistent with not slewing during post-stop polling; the suffix `500` is **not decoded**. This supports a successful movement command and stop sequence at the telemetry level, **but does not independently prove physical movement or a fail-safe stop**. A subsequent six-sample stationary readback showed the exact same position and status each time (see below). Independently test physical stopping in a controlled manner before any automated GoTo.

### AM3N post-stop stationary monitoring (2026-10-27)

- Following the initial `:R5#` / `:Me#` one-second movement and `:Qe#` + `:Q#` stop commands, the user ran a separate **read-only** Python polling test of `:GU#` and `:GZ#` six times at 2-second intervals.
- **All six** status responses were identical: `nNZM000000500#`.
- **All six** azimuth responses were identical: `000*02:00#` (reported azimuth drift **0 arcminutes** across the test).
- **Conclusion:** Post-stop **position stability is verified by mount telemetry** over roughly 12 seconds. The poll contained no movement commands. This supports successful commanded stopping but does not substitute for independent visual confirmation or verify fail-safe stopping on a process crash or USB failure.
- **Next cautiously proposed test:** 3-second motion at the same `:R5#` preset with direction-specific and all-stop commands in a `finally` block, and physical cancel immediately available; confirm physical motion and post-stop stability.

### Second commanded AM3N azimuth motion — three-second rate-5 test (2026-10-27)

User executed a 3-second eastward `:Me#` motion after sending rate preset `:R5#`, with `:Qe#` and `:Q#` stop commands in a Python `finally` clause. Telemetry:

| Readback | Mount reported |
| --- | --- |
| Before azimuth | `000*02:00#` |
| After azimuth | `000*08:00#` |
| After status | `nNZM000000500#` |
| Three seconds later azimuth | `000*08:00#` |
| Three seconds later status | `nNZM000000500#` |

- **Reported change: +6 arcminutes in 3 seconds**, consistent with the preceding +2 arcminutes in 1 second at the same preset. Post-stop azimuth/status remained constant in the separate 3-second follow-up observation.
- This provides repeatable telemetry evidence for start/stop timing and mount motion; user subsequently **visually confirmed** real mount rotation in the 120× sidereal test recorded below. Continue to use physical clearances and backup cancel control.
- The mount's clock was still reported as unset earlier; no GoTo or alignment has been issued.

### First visually verified AM3N movement — 120× sidereal (2026-10-27)

The user reported that rate preset `:R7#` still produced barely perceptible movement, then ran the `:Rv120.00#` variable-speed setup and `:Me#` eastward command for 10 seconds **multiple times**, stopping with `:Qe#` and `:Q#` in a Python `finally` block each run. **User visually confirmed real motor-driven motion**; the last run's specific terminal output was:

| Observation | Response |
| --- | --- |
| Before motion `:GZ#` | `008*41:38#` |
| Directly after 10-second motion and stop commands `:GZ#` | `013*41:42#` |
| Immediately after stop `:GU#` | `nZM130000803#` |
| Three seconds after stop `:GZ#` | `013*43:10#` |
| Three seconds after stop `:GU#` | `nNZM000000800#` |

- **During the commanded 10-second motion:** reported azimuth increased **5°00′04″** (approximately **0.5°/s**). This matches 120× approximate sidereal angular rate (15 arcseconds/second × 120 = 0.5°/second).
- **After stop commands:** mount-reported azimuth increased **another 1′28″** by the three-second follow-up; immediate `:GU#` lacked the `N` flag, while the later response restored it. This is **consistent with non-instantaneous stopping/deceleration or telemetry latency**, but the mechanism and precise stop time are **not verified**. The status suffixes `803` and `800` are not decoded.
- **Important distinction:** User **visually observed the mount move**, unlike the preceding subtle low-speed tests. However **no independent observation has established the exact instant at which physical motion stops**, and no fail-safe under USB disconnection/software crash has been tested.
- **Engineering requirement for AstroPi:** Treat sending `:Q#` as a **stop request**, not immediate proof of halt; poll status and repeated altitude/azimuth samples to confirm stability before claiming stopped or allowing new movements. Implement deadman limits and provide independent physical cancel/power access.
- No tracking, park, two-star alignment or GoTo behavior has been validated yet. The mount clock was previously found uninitialized.

### Repeat high-speed post-stop stationary polling (2026-10-27)

Following the visually confirmed east/azimuth movement at variable `120×` speed and the initial `1′28″` post-stop change, the user performed an additional **five consecutive read-only position/status samples** (one-second intervals). All five were identical:

- `:GZ#` → `013*43:10#`
- `:GU#` → `nNZM000000800#`

**Conclusion:** The mount's reported azimuth was stable (zero change across five polls) and the status consistently indicated no active slew. Combined with the user's visual movement confirmation, this **passes the initial azimuth manual-motion and normal stop-settling probes**. The exact deceleration duration and physical emergency stop during software/USB failure remain **unverified**. The altitude-axis test subsequently changed the mount-reported altitude at the same 120× rate (see below).

### First commanded altitude-axis movement (2026-10-27)

The user ran a cautious 3-second north/up test at variable rate **120× sidereal** using `:Rv120.00#` and `:Mn#`, followed by directional stop `:Qn#` and stop-all `:Q#` within a Python `finally` block.

| Measurement | Raw mount reply |
| --- | --- |
| Before altitude `:GA#` | `+00*00:00#` |
| Before azimuth `:GZ#` | `013*43:10#` |
| Immediately after stop altitude | `+01*29:22#` |
| Immediately after stop azimuth | `013*43:10#` |
| Immediately after stop status | `nZM001300883#` |
| Three seconds later altitude | `+01*30:50#` |
| Three seconds later status | `nNZM000000880#` |

**Interpretation:** Reported altitude increased **1°30′50″** total while azimuth was unchanged. The command-period change to the initial post-stop query was **1°29′22″**; another **1′28″** accrued before the three-second-later query, exactly the same post-stop positional difference seen in the azimuth 120× test. This supports commanded altitude-axis movement and repeatable **non-instantaneous stopping/settling**; do not assume a stop command instantaneously ends motion. The `N` status flag appears only in the settled sample; remaining suffix is not decoded. **Independent visual confirmation of altitude motion was not explicitly reported.** Subsequent five-sample position polling verified both axes stationary (see below). Physical stop under fault conditions, tracking and GoTo remain untested.

**Next:** Perform a no-motion, five-sample `:GA#`/`:GZ#`/`:GU#` polling check; then move to configuration of mount time/site and alignment once command semantics are verified.

### Both-axes stationary verification following movement (2026-10-27)

After the 3-second 120× north/up movement and subsequent stop/settling, the user executed **five read-only** serial sampling rounds (one-second intervals) of `:GA#`, `:GZ#` and `:GU#` via the persistent ZWO serial path. Every round returned:

- **Altitude:** `+01*30:50#`
- **Azimuth:** `013*43:10#`
- **Status:** `nNZM000000880#`

**Result:** No reported motion on either axis across the samples and a stable non-slewing status after stopping. Alongside prior successful and visually confirmed azimuth motion and the altitude telemetry changes, **initial normal-operation motion and stop-settling tests are complete on both axes**. The user's visual confirmation applied explicitly to the azimuth high-speed test; visual confirmation of altitude motion was not separately stated.

**Important boundary:** Stop was not instantaneous in the 120× tests: each axis showed **1′28″** of additional reported travel between the immediate post-stop and three-second-later samples. Exact stop timing, behaviour after abnormal software failure/USB disconnection, and tracking / GoTo / alignment remain unverified. Future mount controller must treat `:Q#` as a request to stop, poll status and both axes for stability, and provide operator physical cancel/power fallback.

### AM3N baseline readback before Home command (2026-10-27)

**Clarification from user:** The hand controller was **not connected**, and the user **only ran the read-only Python script**; they did **not** initiate Home. Therefore the unchanged coordinates are expected and the test should **not** be classified as a failed or attempted Home operation.

| Read-only command | Response |
| --- | --- |
| `:GU#` | `nNZM000000880#` |
| `:GA#` | `+01*30:50#` |
| `:GZ#` | `013*43:10#` |
| `:GR#` | `21:52:17#` |
| `:GD#` | `+44*35:00#` |

**At that time Home control remained untested**, but the user subsequently ran a successful USB-controlled `:hC#` Home operation (see below). INDI's ZWO AM mount driver uses `:hC#` for Home, distinct from `:hP#` for Park; firmware **1.8.8** has a distinct horizontal default Park posture. The AM-series hand controller is optional for normal USB control but is a useful independent physical Cancel fallback during an autonomous slew.


### First verified ZWO AM3N autonomous Go Home from AstroPi (2026-10-27)

**Successful actual motion over USB serial** with firmware **1.8.8**, in **Alt/Az** mode and with the hand controller **disconnected**. The user had substantial physical clearance and explicitly observed the test completing. The Python test sent **`:hC#`** directly on the stable serial port, then polled `:GU#`, `:GA#` and `:GZ#` approximately every two seconds, with a 90-second timeout and `:Q#` fallback if it did not detect completion.

| Moment | Altitude | Azimuth | Status |
| --- | --- | --- | --- |
| Before Home command | `+01*30:50#` | `013*43:10#` | — |
| First observed poll | `+09*19:25#` | `005*52:02#` | `nZM010100994#` |
| On ascent (example) | `+82*26:55#` | `358*07:37#` | `nZM800100994#` |
| Near zenith | `+88*20:29#` | `180*58:30#` | `nZM8b8900992#` |
| On descent (example) | `+79*36:52#` | `002*52:37#` | `nZM808900992#` |
| First Home reading | `-00*00:00#` | `000*00:00#` | `nNHZM040400990#` |
| Four consecutive stable readings | `-00*00:00#` | `000*00:00#` | `nNHZM040400990#` |
| Final status queried | `-00*00:00#` | `000*00:00#` | `nNHZM040400990#` |

- **Verified:** The Home command `:hC#` initiated a motorized return sequence without the hand controller; the reported position reached 0° altitude and 0° azimuth, and the program detected four consistent home-position/status samples before exiting successfully. Third-party ZWO driver documentation confirms `H` in `:GU#` = at home, `N` = no longer slewing, `Z` = Alt/Az. Reference: `https://pkg.go.dev/github.com/mikefsq/lx200@v0.2.2/am5`.
- **User clarification on Home trajectory:** The owner confirms the AM3N has **always** followed this characteristic near-zenith path when commanded Home by its **hand controller**, not just via AstroPi USB. Therefore this trajectory is **expected for this unit**, and is not evidence of incorrect USB commands or an AstroPi homing fault. The reported ~180° azimuth jump near zenith may reflect a coordinate discontinuity; it is not proof of physically instantaneous rotation. **Normal does not automatically mean collision-free** with every telescope, accessory, and cable arrangement: confirm clearances and cable slack under the intended real-world setup. AstroPi should use the mount's native Home command rather than inventing its own path.
- **Physical safety caveat:** The user explicitly **did not plug in the hand controller** for this test. USB software timeout/stop cannot guarantee safety during a lost link or process failure. Recommend an independent reachable cancel/power mechanism before running unattended or higher-risk motion.
- **Next checks:** A short read-only follow-up to reconfirm Home and stable axes; only afterward investigate alignment and GoTo. Clock/location were synchronized and site corrected beforehand; Home does **not** itself establish sky-pointing accuracy or alignment.

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

## 64 GB acquisition USB stick — first connection (2026-10-27)

User hot-plugged the intended flash storage drive while both camera and AM3N remained connected. `lsblk` reported **`sda` 59.8 GiB, USB, Flash Drive FIT**, with two old Raspberry Pi OS-style volumes: `sda1` 512 MiB `vfat` `bootfs`, `sda2` 59.2 GiB `ext4` `rootfs`. Neither volume mounted; **the active OS is on `mmcblk0`**, with `mmcblk0p2` mounted at `/` and `mmcblk0p1` at `/boot/firmware`. Its partition UUIDs differ from those on the flash stick.

`lsusb -t` simultaneously reported **USB 3 mass storage at 5000M**, SV705C vendor device at **5000M**, and ZWO AM3N CDC ACM at **12M** USB 2. USB **link negotiation** verified, but measured file write speed, integrity, bus stability under load, and persistent mount **not yet verified**.

**Do not destroy the pre-existing partitions without explicit confirmation** that the stick's old OS image/data may be erased. If approved, create one clean ext4 acquisition volume and identify/mount it by UUID; record its replacement UUID and measured performance. Always reconfirm the device name before any destructive command: `/dev/sda` is observed now, not guaranteed forever.

### USB acquisition stick: dedicated ext4 filesystem confirmed (2026-10-27)

User explicitly approved **erasing the old Raspberry Pi OS image** on the removable `Flash Drive FIT` storage device. After repartitioning to one GPT Linux partition and formatting ext4, the first `lsblk` response showed the new `sda1` partition but no filesystem metadata; a later `udevadm settle`, `blkid -p`, `wipefs -n`, and `lsblk` verification confirmed:

- Device at time of test: **`/dev/sda1`**, 59.8 GiB; original `/dev/mmcblk0` root OS untouched.
- Filesystem: **ext4**, version 1.0, 4 KiB blocks, label **`astropi-data`**.
- **Filesystem UUID:** `25b33cfa-b178-4b86-8a15-d00c8305cca5`.
- GPT partition UUID: `91e60011-2543-48e3-9ecb-b4f151f8b565`.
- Verified ext4 signature using `wipefs -n /dev/sda1` and `blkid -p /dev/sda1`.
- **Status:** Format and metadata identification verified, **not mounted yet**. Next intended step is automatic mount at `/media/astropi-data` using the UUID and fstab `nofail`, followed by actual mount and sustained write/read verification. The application must refuse disk recording when this mount is missing; do not fall back to the microSD.

## Pre-development integrated hardware acceptance checklist (planned 2026-10-27)

The core camera and mount interfaces have passed their **individual** smoke tests. Before substantial application coding, test the complete field configuration in the following order. Statuses below distinguish **known**, **planned**, and **not yet verified**.

| Priority | Test | Evidence for acceptance | Status |
| --- | --- | --- | --- |
| P0 | 64 GB USB 3 acquisition drive | Identify correct USB device and filesystem **before any formatting**, inspect capacity/UUID, mount persistently by UUID, perform non-destructive write/read integrity and sustained throughput test, verify clean unmount/remount and reboot persistence | **Not yet tested** |
| P0 | Camera capture to target storage | Verify explicit manual gain/exposure control, multiple consecutive RAW16 frames, nontrivial image statistics, preview of ordinary scene, proper frame format/12-bit alignment, and checksums/file sizes on the new drive | **One RAW16 frame saved to SD**; further work pending |
| P0 | Realistic whole-system load & power | SV705C + AM3N + USB3 recording drive (+ intended Wi-Fi if needed) active together; monitor `vcgencmd get_throttled`, supply/buck ratings and voltage under load, `dmesg` USB disconnects/resets, `journalctl` and temperatures for ~20–30 minutes | **Single camera frame and mount tests verified, combined sustained test pending** |
| P1 | Offline startup / time / network | Reboot on real field power without Internet; verify local browser accessibility, Wi-Fi/AP behaviour, reliable clock acquisition or clock fallback, mount clock synchronization, stable devices and writable data path | **NTP synchronized while online; offline untested, no hardware RTC** |
| P1 | Mount with actual optical payload | Confirm cables, camera/OTA clearance and power branches during native Home path (including near zenith); confirm external physical stop/power access and usable normal-stop/deadman behaviour | **Home and normal stops tested with existing configuration; full field cable/safety layout pending** |
| P2 | Repeatability and recovery | Restart services, remove/reconnect devices **only while capture/motors are safely idle**, validate camera rediscovery, serial port by-id, readable files and predictable failure handling; reboot/power cycle time/location retention | **Not yet systematically tested** |

**Technical notes:**
- Raspberry Pi 4 documentation gives **1.2 A total downstream USB power budget** (shared across all ports), not 1.2 A per port. A powered USB hub is an option **only if actual tests show a power issue**. Source: `https://www.raspberrypi.com/documentation/computers/raspberry-pi.html`.
- USB 3 cabling can degrade nearby 2.4 GHz reception; try a properly positioned dongle/5 GHz when testing actual field-network configuration.
- SV705C SDK property readback reported supported bin values 1, 2, 3, 4, whereas the public SV705C specification explicitly lists 1× and 2×. Treat bin 3 and 4 as **unverified** until acquiring frames; do not assume that an advertised SDK field guarantees physical support. Product source: `https://www.svbony.com/products/sv705c-color-planetary-camera-imx585`.
- Current success is a single saved RAW16 full-frame file from a dark, severely defocused optical setup. A file with correct size is not sufficient proof of correct debayering, pixel alignment, proper exposures or write reliability.
- **Not a pre-coding blocker:** actual sky alignment, target GoTo accuracy, sustained sidereal/AltAz tracking, refined focusing and browser UI. They should be tested iteratively as the related modules are implemented, before real observing sessions.
- Do not purchase additional hardware (RTC, powered hub, new storage) until the relevant acceptance test establishes a real need.

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
