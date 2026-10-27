# AstroPi hardware and verified integration

**Current truth as of 2026-10-27.** This is the **concise operational reference**, not a chronological test diary. “Verified” means directly observed from `arn@astropi` terminal output or inspected images. “Planned” means **not implemented or not tested**. The full 69 KB original probe log remains in [Git history at `f01ae019`](https://github.com/Arnbargler/astropi/blob/f01ae019f9ba840f90b5bb5e566d0fc17dab41b7/HARDWARE.md) for troubleshooting; some statements in that historical snapshot were superseded by later tests.

## Equipment and connections

| Item | Current configuration / evidence |
| --- | --- |
| Host | Raspberry Pi **4 Model B Rev 1.5, 4 GiB**, hostname **`astropi`**, username **`arn`**; Debian **13.6 Trixie**, kernel **`6.18.39+rpt-rpi-v8`**, Python **3.13.5**, ARM64. Boots from **32 GB microSD** (`/dev/mmcblk0`). |
| Network/time | Wi-Fi `wlan0` works, NTP was active and synchronized in tests; **no hardware RTC**. Do not depend on the Pi's local timezone; use trusted **UTC**. Offline time acquisition is **not implemented**. |
| Camera | **SVBONY SV705C**, USB ID **`f266:9a0a`**, USB3 **5000M** on the Pi's blue port, 3856×2180 colour sensor, max sensor depth **12 bits**; SDK Bayer enum 2 = **GRBG**. |
| Mount | **ZWO AM3N**, firmware **`1.8.8`**, USB ID **`03c3:4001`**, CDC ACM USB2 **12M**; Alt/Az **only**. `arn` belongs to `dialout`. |
| Recording | **64 GB** USB3 flash stick, model **Flash Drive FIT**, negotiated **5000M**. One ext4 GPT partition, label `astropi-data`, filesystem UUID **`25b33cfa-b178-4b86-8a15-d00c8305cca5`**, auto-mounted at **`/media/astropi-data`**. |
| Test optics | **Canon EF kit lens at 18 mm** attached to SV705C; this produced recognizable room images. **Not** a final telescope/focal-length specification. |
| Power | Intended field setup: **12 V supply/battery** feeding AM3N and **12→5 V buck** for Pi. Exact buck ratings, wiring/fusing and end-to-end battery endurance **not yet documented/tested**. |
| Other workstation | Linux Mint **N100** for development/browser use and eventual offline/post-capture alignment/stacking/field-rotation correction; **not required for Pi acquisition**. |

Bus/device numbers and `/dev/sda`/ `/dev/ttyACM0` may change after reconnect; use a stable serial alias and the filesystem UUID. Observed USB layout during endurance: SV705C on USB3 bus 2 port 2, stick on USB3 bus 2 port 1, AM3N on USB2 using `cdc_acm`. All three remained enumerated after Pi reboot.

## Camera: SDK and exact integration details

- SVBONY Linux SDK distribution `v1.13.4` is installed **on the Pi, not in this repository**. ARM64 library: **`/home/arn/svbony-sdk/SVBCameraSDK/lib/armv8/libSVBCameraSDK.so`**; headers: `/home/arn/svbony-sdk/SVBCameraSDK/include/`. Load via Python `ctypes.CDLL`; system `libusb-1.0` dependencies resolve.
- Camera USB permission rule: `/etc/udev/rules.d/90-ckusb.rules`, vendor/product `f266:9a0a`, mode `0666` (trusted local environment). Do not commit the vendor binaries.
- **Required demonstrated initialization order:** `SVBGetNumOfConnectedCameras()` → `SVBGetCameraInfo(&info, index=0)` → use `info.CameraID` → `SVBOpenCamera(id)` → configure → `SVBStartVideoCapture(id)` → `SVBGetVideoData(...)` → `SVBStopVideoCapture(id)` → `SVBCloseCamera(id)`. CameraInfo has 32-byte `FriendlyName`, `CameraSN`, `PortType`, then unsigned `DeviceID` and signed `CameraID`; observed CameraID **1**, **do not hard-code it**.
- A test skipping `SVBGetCameraInfo` before `SVBOpenCamera(1)` failed with **SDK error 2**. After proper enumeration/info, open/close succeeded. Treat correct sequence as mandatory even though the precise SDK-internal reason is unproven.
- Verified full resolution call `SVBSetROIFormat(id, 0, 0, 3856, 2180, 1)` and output enum **4 = RAW16**; RAW8 enum 0 also supported. Each full RAW16 buffer is exactly **16,812,160 bytes**. Supported bin modes were reported **1, 2, 3, 4**, but **3 and 4 have not been capture-tested** (published camera specifications may differ). Do not expose modes just because a capability array lists them.
- SDK control **0 = gain**, **1 = exposure in microseconds**. Use `SVBSetControlValue` and read back `SVBGetControlValue`; SDK exposure quantizes slightly. Verified requests/readbacks: 10,000→**10,007 µs**, 50,000→**50,148 µs**, 1,000,000→**1,000,143 µs**; gain 0→0 and 100→100, with auto flag 0.
- Exposure validation: at gain 0, changing ~10 ms→50 ms changed sampled 12-bit mean from **27.35→133.34 (~4.88×)** at similar light levels. Gain validation: at ~50 ms, gain 0→100 increased mean **133.34→440.11 (~3.30×)**; high-gain sample had ~0.05% saturation. These are **functional tests, not calibration standards**.
- RAW16 sampled pixel words were **100% multiples of 16** in dark and illuminated frames, strongly supporting **12-bit data left-aligned by four bits**; right-shift by 4 for preview scaling. Dark frames had **lens cap on**. An illuminated 10 ms frame showed sampled max raw **5,328**, mean **317.22**, ~3.77% zero pixels, no sampled saturation. The original RAW must remain unchanged.
- Colour preview: **GRBG** arrangement; combine each **4×4 Bayer sensor block** into one RGB sample, ~**964×545**, rough percentile-based white balance/stretch, encode PNG. User inspected both grayscale and RGB views; recognizably correct indoor objects and plausible colours. **Not** a full-resolution/photometrically calibrated demosaic, and performance for live preview still needs profiling.
- SDK stream caveat: a test calling stop/start for a *second* capture within the same camera session failed at `SVBGetVideoData` with **error 11 = timeout**. A fresh camera session with one stream start captured the 50 ms frame on its first request. **Root cause not proved.** Prefer maintaining one streaming session; implement bounded timeouts, safe cleanup and reconnect handling rather than assuming every restart will work.
- Paths of actual retained examples: `/media/astropi-data/camera-test-20261027-110857/` (ten full RAW16 frames), `/media/astropi-data/light-test-20261027-111913.raw16` plus grayscale and `-color.png`, `/media/astropi-data/exposure-gain-test/`, and endurance output below. These are on the **Pi USB stick, not in Git**.

### Proven capture/storage endurance

**20-minute test 2026-10-27**, AM3N connected but stationary, one continuous camera session, gain 0, measured exposure 1,000,143 µs, RAW16 at full resolution, a frame retrieval every 2 seconds and an `fsync`/SHA-256-checked file every fifth retrieval:

| Metric | Observed |
| --- | --- |
| Frame retrieval | **600/600** successful; **0 SDK timeouts** |
| Saved files | **120/120**, individually SHA-256 readback verified; **120 distinct digests** |
| Raw payload | **2,017,459,200 bytes (~1.88 GiB)** |
| Pi temperature | **46.7–51.6°C** over twenty 1-minute readings |
| Power flags | `vcgencmd get_throttled` **`0x0`** throughout |
| SDK shutdown | Stop, restore gain/exposure and Close all returned **0** |
| Directory | `/media/astropi-data/endurance-20261027-114529/` |

**One kernel USB3 reset**: `2026-10-27 11:45:29 usb 2-2: reset SuperSpeed USB device number 3 using xhci_hcd`, on the camera's USB port around capture startup. Cause unknown; *no subsequent matching USB/storage errors in the user's filtered log*, no lost frames or timeouts. Monitor for future resets, especially during recording; don't call the kernel log completely clean. This test is representative of low-cadence DSO exposures, **not maximal USB3 throughput or simultaneous mount slewing**.

## AM3N: protocol, current settings and motion evidence

- Preferred path: **`/dev/serial/by-id/usb-ZWO_Systems_ZWO_Device_123456-if00`** (currently points to `/dev/ttyACM0`). `pyserial 3.5`; **9600 8N1**, no flow control, ~2 s serial read timeout, ASCII LX200-like `:` commands, `#` reply terminator for queries.
- Model `:GVP#` → `AM3N#`; firmware `:GV#` → `1.8.8#`. Query `:GU#` reports status flags (third-party protocol interpretation): **`n` not tracking, `N` not slewing, `H` at Home, `Z` Alt/Az**. The remaining `M...` suffix is **not decoded**. **`:GAT#` returned `e7#`**, inconsistent with some third-party tracking examples; **do not rely on it** for tracking status.
- **Owner-selected observing site:** latitude **+45.2933°** (mount `+45*17:36#`), longitude **−75.8571° east-positive** (mount uses **west-positive** `+075*51:26#`). Setter `:St+45*17:36#` for latitude; `:Sg+075*51:26#` for longitude. Both replied **`1`**, verified by `:Gt#`/`:Gg#` readbacks. Owner believes site survives power cycles because the old stored coordinates matched their former home; **nonvolatility not independently power-cycle-tested**. Reapply site on connect.
- **Clock (manually demonstrated):** `:SG+00:00#` sets UTC offset 0; `:SC10/27/26#` date; `:SL13:37:03#` time—each setter acknowledged `1`. `:GG#`, `:GC#`, `:GL#` readbacks matched; clock advanced correctly, and `:GS#` local sidereal time agreed to ~0.5 s with independent calculation at the then-stored longitude. **Example commands contain historical times; use live UTC.** **Automatic startup/reconnect synchronization does NOT exist yet**. Pi lacks RTC, so offline field boot needs trusted time before sky GoTo.
- **Read-only position:** `:GA#` altitude, `:GZ#` azimuth, `:GR#` RA, `:GD#` Dec; **reported** coordinates are not proven pointing accuracy until alignment. `:GS#` sidereal time. No command should be treated as proof of sky alignment.
- **Manual motion verified:** `:Rv120.00#` (~120× sidereal) followed by `:Me#` east caused **visibly observed** azimuth movement; `:Mn#` up caused positive altitude telemetry change. Preset `:R5#` also moved azimuth (2 arcmin in 1 s, 6 arcmin in 3 s). Directional stops e.g. `:Qe#`, `:Qn#`, plus `:Q#` all-stop are accepted.
- **Important stop behaviour:** after high-speed `:Qe#`/`:Qn#` and `:Q#`, each tested axis showed another **1′28″ reported position change** before a later stable reading; it may be deceleration or telemetry latency. Always treat a stop as **requested**, then poll `:GU#` and both axes repeatedly for stationary readings. The normal-operation stop-settling tests passed; **abnormal USB disconnect/process crash/fail-safe stopping have not been tested**.
- **Native Home verified:** sent **`:hC#`** via USB, hand controller disconnected, and observed actual motorized Home sequence. Start altitude **+01°30′50″**, azimuth **013°43′10″**; final **altitude 0°, azimuth 0°** with status **`nNHZM040400990#`** stable across four polls. Owner confirms its **near-zenith, azimuth-wrap route** is the same native route taken via hand controller. **Do not attempt to “fix” this path**. Confirm payload/cable clearance in each physical setup.
- **Park is separate and not tested** (third-party driver uses `:hP#`; firmware 1.8.8 reportedly defaults to horizontal Park). Unpark, tracking commands, sky GoTo and alignment have **not been validated**. Use protocol sources as hypotheses and verify in controlled stages; e.g. [INDI AM-series driver](https://github.com/indilib/indi/blob/master/drivers/telescope/lx200am5.cpp).
- User's physical warning: AM3N's **M12 counterweight-bolt hole can reach internal wiring**. **Never insert an overlong M12 bolt.** Mount/Home movements also require physical clearance and a reachable hardware Cancel/power fallback; software stop is not fail-safe if Pi/USB dies.

## USB flash data drive

- USB3 at **5000M**, ~59.8 GiB. USB stick was an old Pi OS image; the user explicitly approved its erasure. ext4 label **`astropi-data`**, UUID **`25b33cfa-b178-4b86-8a15-d00c8305cca5`**.
- `/etc/fstab`: `UUID=25b33cfa-b178-4b86-8a15-d00c8305cca5 /media/astropi-data ext4 defaults,nofail,x-systemd.device-timeout=10s 0 2`. Mounted `rw`; mount root `arn:arn`. `nofail` permits boot without USB drive.
- Storage benchmark: **512 MiB write at 20.2 MiB/s**, checksum readback **PASS**; measured read **146.5 MiB/s** likely inflated by Linux cache. A **16 MiB file survived reboot** with SHA-256 `OK`; filesystem auto-mounted after reboot; no undervoltage.
- Crucial: **require a mounted filesystem with this UUID** before writing captures. **Never** silently fill `/dev/mmcblk0` if flash drive is absent. Check free space, write via `.partial` → `fsync` → atomic rename, and verify/capture errors.
- Last tested drive occupancy was **2.2 GiB used / 57 GiB available** (4%), after endurance; do not assume this remains current.

## Browser live-preview performance (verified on Pi, 2026-10-27)

At the **50 ms exposure** preset with the new two-thread JPEG preview pipeline, the user observed:

| Preview mode | RAW acquisition | Browser preview | Preview processing |
| --- | ---: | ---: | ---: |
| Debayer On (colour) | **15.8 FPS** | **14.8 FPS** | **62 ms** |
| Debayer Off (grayscale, sampled green sites) | **16.5 FPS** | **16.6 FPS** | **14 ms** |

The prior preview was **2.2 FPS** / **143 ms JPEG processing**, so the new colour path is ~6.7× faster; mono ~7.5× faster. Browser preview FPS is a measured instantaneous/smoothed rate and can briefly exceed RAW FPS; do not interpret that as sustained extra frames. At 50 ms the exposure-only ideal ceiling is 20 FPS, but readout/USB/processing impose overhead. Colour conversion is no longer the primary bottleneck. These numbers are snapshots, not a full benchmarking sweep or verified 30 s behaviour.

## On-Pi one-shot capture file creation (verified 2026-10-27)

The user tested independent recording format toggles and provided a Pi shell listing confirming four completed directories on `/media/astropi-data/captures/`:

| UTC folder prefix | Observed files besides `metadata.json` |
| --- | --- |
| `20261027T212407_904664_f9b41e` | FITS, RAW16, JPG, PNG |
| `20261027T212436_111525_ab0bbd` | FITS only |
| `20261027T212445_542596_1dd89b` | FITS, JPG |
| `20261027T212451_166770_6a75d1` | FITS, RAW16, JPG, PNG |

Thus all four format writers and independent selection combinations produced files through the Pi app on its configured USB recording path. There were no `.partial` paths in the displayed list. **Follow-up Pi verification:** all four directories passed file size and SHA-256 digest comparisons against their `metadata.json` records: 4 + 1 + 2 + 4 = **11/11 files PASS**. This confirms stored bytes match the recorded hashes, not independent FITS pixel correctness, exact mounted UUID at test time or USB-loss behaviour; those remain separately unverified. No exposure sequences yet.

## Five-frame sequence and Bayer fidelity (verified on Pi, 2026-10-27)

User performed the first **real** 5-frame sequence using the newly integrated browser controls. UI reported **5 / 5 frames saved** and **Sequence: Capture saved to USB drive**, listing these five completed capture directories:

- `captures/20261027T214833_403289_c8ea6d`
- `captures/20261027T214834_911017_e0d56e`
- `captures/20261027T214836_114608_a299a1`
- `captures/20261027T214837_324260_50a998`
- `captures/20261027T214838_630750_0b3f85`

This verifies sequence completion, five reported completed frame folders, and Pi USB recording in the tested short run. Per-frame SHA-256 recheck for this **new** five-frame sequence was not supplied; previous 11 one-shot files were validated.

The user also ran the new **read-only FITS/Bayer verifier** on the previously recorded all-four-format capture `20261027T212451_166770_6a75d1`. Exact terminal results:

```text
PASS: 4 saved files match checksums and sizes.
PASS: FITS structure and 12-bit Bayer sample range.
PASS: All FITS pixels match the RAW16 sensor pixels.
```

Hence **all 8,406,080 pixels of that saved FITS matched the paired RAW16** after accounting for the native 12-bit left shift and FITS signed storage offset. This validates one real recorded science-data pair; it does not independently calibrate sensor response, guarantee exact exposure timestamps, establish browser-disconnect endurance, test cancellation under load or prove recovery from lost USB storage.

## Ten-frame completion and cancellation (verified on Pi, 2026-10-27)

Follow-up real-camera / USB sequence tests passed:

| Sequence ID | Browser completion status | Independent manifest enumeration |
| --- | --- | --- |
| `77f0893f415b` | Normal ten-frame run | **10 / 10** folders with frame numbers **1–10**, no gaps |
| `62b28bdbfabd` | **Sequence: Capture sequence cancelled**, **4 / 10 frames saved** | **4 / 10** folders with frame numbers **1–4**, no gaps |

The cancelled run displayed four completed capture directories:

- `captures/20261027T220217_190814_74cd27`
- `captures/20261027T220218_694299_c0327c`
- `captures/20261027T220234_233343_3aafe0`
- `captures/20261027T220240_248883_c39207`

The user's manifest-inspection script reported **`Incomplete folders: 0`**. Cancellation appears to have respected the safe write boundary: four finished frames were retained and the remaining six were not saved. Together with the prior five-frame pass, normal completion and short-run cancellation are now **hardware-verified**. Not independently reverified in this test: per-file SHA-256 for the new sequences, camera exposure timing, browser-disconnection endurance, >10-frame endurance, or deliberate USB-loss recovery. No AM3N mount movement in these camera tests.

## First AM3N application integration (code-tested, hardware retest needed)

**New milestone (2026-10-27):** The app has an explicit operator-only **Connect Mount / Disconnect** UI and its own serial telemetry worker at `astropi/mount/worker.py`. The worker is not started at web-service launch or when any browser reads status. Connect opens ONLY the verified by-id alias at 9600 8N1 (pyserial), checks `:GVP#` returns model AM3N, obtains firmware via `:GV#`, and polls the **read-only** commands `:GU#`, `:GA#`, `:GZ#`, `:GR#`, `:GD#` (status, altitude, azimuth, RA and Dec).

All serial I/O is confined to one thread. Flask exposes cached status to viewers and operator-gated Connect/Disconnect only; it has **NO generic command endpoint** and **NO motion/Home/Park/clock/site/tracking setters**. Invalid serial responses, missing alias and unplug errors close the handle, show error status and clear potentially stale coordinates. Recovery requires an explicit Connect again (no automatic move or reconnect). Flag decoding is conservative: only *confirmed* positions in `:GU#` are interpreted; its undocumented suffix is displayed as raw text. All displayed coordinates are explicitly mount-reported, not sky-aligned or independently measured.

**Important:** This is CI-tested with simulated serial responses only. The new browser serial connection and actual coordinate updates are **not yet verified on Pi hardware**. Older manual protocol probes listed above are real hardware evidence, but not evidence this new application worker works there. No time/site synchronization occurs and offline sky GoTo is still unsafe/not implemented.

## What remains unresolved (not pre-development blockers)

1. **Pi browser status, SV705C preview and 50ms two-thread colour/mono rates are verified.** One-shot recording produced four completed capture directories on Pi USB with different combinations of FITS/RAW16/JPG/PNG. All 11 file sizes and SHA-256 checksums verified against metadata on the Pi; FITS 12-bit Bayer pixel equality against RAW16 verified for one real capture; first five-frame sequence completed and reported five saved directories on Pi USB. Ten-frame completion and four-frame cancellation during a requested ten-frame sequence are Pi-verified, with zero incomplete folders. Endurance beyond ten frames, fault recovery and auto-start remain unverified/unfinished.
2. **Mount:** first verify newly implemented read-only serial worker on the real AM3N. Thereafter sky-pointing alignment, safe manual movement, Alt/Az GoTo, tracking/stop and Park remain unimplemented; offline location/time recovery and abnormal link-failure safety remain untested. Home works but does not establish pointing accuracy.
3. **Camera:** test extended endurance and failure handling, separately verify per-frame saved sequence checksums, long-exposure metadata precision, colour calibration, ROI/binning beyond proven full-frame 1x and fault recovery. Live preview is near camera-limited speed at 50ms.
4. **Physical field deployment:** actual optical tube and 12 V battery/buck wiring, cable clearance on Home/GoTo, safe physical Cancel, offline network and trusted time, sustained battery runtime. The successful test was with connected but **stationary** AM3N.
5. **Service:** one process owns camera SDK; one serialized mount command queue; capture sequences must survive browser disconnect; one operator lease; timestamps/site/UUID validated before scientific recordings.

**Use [REQUIREMENTS.md](REQUIREMENTS.md) for what to build and [DEVELOPMENT.md](DEVELOPMENT.md) for how to begin.** Current facts here supersede historical probe entries; keep detailed diagnosis in Git history rather than turning this file back into a daily console log.
